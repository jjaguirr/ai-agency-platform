"""
Redis-backed operational state for the proactive system.

Key layout (all under proactive:{customer_id}:*):
  :cooldown:{key}       → ISO timestamp of last fire for that cooldown key
  :daily:{YYYY-MM-DD}   → integer count of non-urgent messages sent that day
  :last_briefing        → ISO timestamp of last morning-briefing send
  :last_interaction     → ISO timestamp of last inbound customer message
  :last_nudge           → ISO timestamp of last idle-nudge send
  :followups            → JSON list of Commitment dicts
  :notifications        → JSON list of pending ProactiveTrigger dicts (pull queue)
  :phone                → last-seen E.164 for outbound WhatsApp routing

Everything is plain strings or JSON — no pickle, no version-fragile
formats. The store survives process restarts by virtue of being Redis;
there's no in-process cache to invalidate.

Design note: the daily-count key carries a 48h TTL. That's a cleanup
convenience, not a correctness mechanism — the date is in the key, so a
stale counter for a past day is simply never read. The TTL just stops
keys accumulating forever on low-traffic tenants.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional

from .followups import Commitment
from .triggers import ProactiveTrigger


Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class ProactiveStateStore:
    """All Redis interaction for the proactive subsystem.

    Takes an async Redis client (redis.asyncio or fakeredis.aioredis with
    decode_responses=True) and an injectable clock. The clock is only used
    for defaulting timestamps on write; reads are always explicit.
    """

    _PREFIX = "proactive"

    def __init__(self, *, redis: Any, clock: Clock = _default_clock):
        self._r = redis
        self._clock = clock

    # --- Key helpers -------------------------------------------------------

    def _k(self, customer_id: str, *parts: str) -> str:
        return ":".join([self._PREFIX, customer_id, *parts])

    # --- Cooldown ----------------------------------------------------------

    async def get_cooldown(self, customer_id: str, key: str) -> Optional[datetime]:
        v = await self._r.get(self._k(customer_id, "cooldown", key))
        return datetime.fromisoformat(v) if v else None

    async def set_cooldown(self, customer_id: str, key: str, at: datetime) -> None:
        await self._r.set(self._k(customer_id, "cooldown", key), at.isoformat())

    # --- Daily counter -----------------------------------------------------

    async def get_daily_count(self, customer_id: str, date_str: str) -> int:
        v = await self._r.get(self._k(customer_id, "daily", date_str))
        return int(v) if v else 0

    async def incr_daily_count(self, customer_id: str, date_str: str) -> None:
        key = self._k(customer_id, "daily", date_str)
        # INCR creates at 0 if absent. 48h TTL for housekeeping — see
        # module docstring for why this isn't load-bearing.
        await self._r.incr(key)
        await self._r.expire(key, 48 * 3600)

    # --- Timestamps --------------------------------------------------------
    # All three share the same store/get shape; kept explicit rather than
    # metaprogrammed because the call sites read more clearly with real
    # method names and the wire format is obvious on inspection.

    async def _get_ts(self, customer_id: str, field: str) -> Optional[datetime]:
        v = await self._r.get(self._k(customer_id, field))
        return datetime.fromisoformat(v) if v else None

    async def _set_ts(self, customer_id: str, field: str,
                      at: Optional[datetime]) -> None:
        k = self._k(customer_id, field)
        if at is None:
            # Explicit reset — tests use this to re-arm the briefing check
            # without flushing all customer state. DEL is idempotent.
            await self._r.delete(k)
        else:
            await self._r.set(k, at.isoformat())

    async def get_last_briefing(self, customer_id: str) -> Optional[datetime]:
        return await self._get_ts(customer_id, "last_briefing")

    async def set_last_briefing(self, customer_id: str,
                                at: Optional[datetime]) -> None:
        await self._set_ts(customer_id, "last_briefing", at)

    async def get_last_interaction(self, customer_id: str) -> Optional[datetime]:
        return await self._get_ts(customer_id, "last_interaction")

    async def set_last_interaction(self, customer_id: str,
                                   at: Optional[datetime]) -> None:
        await self._set_ts(customer_id, "last_interaction", at)

    async def get_last_nudge(self, customer_id: str) -> Optional[datetime]:
        return await self._get_ts(customer_id, "last_nudge")

    async def set_last_nudge(self, customer_id: str,
                             at: Optional[datetime]) -> None:
        await self._set_ts(customer_id, "last_nudge", at)

    # --- Followups ---------------------------------------------------------
    # Stored as a single JSON array under one key. Followup counts per
    # customer are tiny (tens, not thousands) — the simplicity of one
    # atomic read/write outweighs the cost of re-serialising the whole
    # list on each mutation.

    async def list_followups(self, customer_id: str) -> List[Commitment]:
        raw = await self._r.get(self._k(customer_id, "followups"))
        if not raw:
            return []
        return [Commitment.from_dict(d) for d in json.loads(raw)]

    async def add_followup(self, customer_id: str, c: Commitment) -> None:
        existing = await self.list_followups(customer_id)
        # Dedupe by id — identical commitments collapse.
        if any(e.id == c.id for e in existing):
            return
        existing.append(c)
        await self._r.set(
            self._k(customer_id, "followups"),
            json.dumps([e.to_dict() for e in existing]),
        )

    async def remove_followup(self, customer_id: str, commitment_id: str) -> None:
        existing = await self.list_followups(customer_id)
        remaining = [e for e in existing if e.id != commitment_id]
        await self._r.set(
            self._k(customer_id, "followups"),
            json.dumps([e.to_dict() for e in remaining]),
        )

    # --- Notifications queue ----------------------------------------------
    # Pull-model inbox. enqueue appends, drain returns-and-clears. Ordering
    # (priority DESC then created_at ASC) is applied at drain time — the
    # writer shouldn't have to know the delivery contract.

    async def enqueue_notification(self, customer_id: str,
                                   t: ProactiveTrigger) -> None:
        key = self._k(customer_id, "notifications")
        raw = await self._r.get(key)
        items = json.loads(raw) if raw else []
        items.append(t.to_dict())
        await self._r.set(key, json.dumps(items))

    async def drain_notifications(self, customer_id: str) -> List[ProactiveTrigger]:
        key = self._k(customer_id, "notifications")
        raw = await self._r.get(key)
        if not raw:
            return []
        await self._r.delete(key)
        triggers = [ProactiveTrigger.from_dict(d) for d in json.loads(raw)]
        triggers.sort(key=ProactiveTrigger.sort_key)
        return triggers

    # --- Phone -------------------------------------------------------------

    async def get_phone(self, customer_id: str) -> Optional[str]:
        return await self._r.get(self._k(customer_id, "phone"))

    async def set_phone(self, customer_id: str, e164: str) -> None:
        await self._r.set(self._k(customer_id, "phone"), e164)
