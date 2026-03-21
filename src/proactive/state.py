"""Redis-backed proactive state store.

Keys use the pattern ``proactive:{customer_id}:{subkey}`` and are
independent of the conversation persistence layer.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _key(customer_id: str, *parts: str) -> str:
    return ":".join(["proactive", customer_id, *parts])


class ProactiveStateStore:
    def __init__(self, redis_client) -> None:
        self._r = redis_client

    # -- Cooldowns -----------------------------------------------------------

    async def record_cooldown(
        self, customer_id: str, cooldown_key: str, window_seconds: int = 86400
    ) -> None:
        key = _key(customer_id, "cooldown", cooldown_key)
        await self._r.set(key, "1", ex=window_seconds)

    async def is_cooling_down(self, customer_id: str, cooldown_key: str) -> bool:
        key = _key(customer_id, "cooldown", cooldown_key)
        return await self._r.exists(key) > 0

    # -- Last briefing time --------------------------------------------------

    async def get_last_briefing_time(self, customer_id: str) -> Optional[datetime]:
        key = _key(customer_id, "last_briefing")
        val = await self._r.get(key)
        if val is None:
            return None
        return datetime.fromisoformat(val.decode() if isinstance(val, bytes) else val)

    async def set_last_briefing_time(self, customer_id: str, t: datetime) -> None:
        key = _key(customer_id, "last_briefing")
        await self._r.set(key, t.isoformat())

    # -- Last interaction time -----------------------------------------------

    async def get_last_interaction_time(self, customer_id: str) -> Optional[datetime]:
        key = _key(customer_id, "last_interaction")
        val = await self._r.get(key)
        if val is None:
            return None
        return datetime.fromisoformat(val.decode() if isinstance(val, bytes) else val)

    async def update_last_interaction_time(self, customer_id: str) -> None:
        key = _key(customer_id, "last_interaction")
        await self._r.set(key, datetime.now(timezone.utc).isoformat())

    # -- Follow-ups ----------------------------------------------------------

    async def list_follow_ups(self, customer_id: str) -> List[Dict[str, Any]]:
        key = _key(customer_id, "follow_ups")
        raw = await self._r.lrange(key, 0, -1)
        return [json.loads(item.decode() if isinstance(item, bytes) else item) for item in raw]

    async def add_follow_up(self, customer_id: str, follow_up: Dict[str, Any]) -> None:
        key = _key(customer_id, "follow_ups")
        await self._r.rpush(key, json.dumps(follow_up))

    async def remove_follow_up(self, customer_id: str, follow_up_id: str) -> None:
        key = _key(customer_id, "follow_ups")
        items = await self._r.lrange(key, 0, -1)
        for item in items:
            decoded = item.decode() if isinstance(item, bytes) else item
            parsed = json.loads(decoded)
            if parsed.get("id") == follow_up_id:
                await self._r.lrem(key, 1, item)
                break

    # -- Daily message count -------------------------------------------------

    async def get_daily_count(self, customer_id: str) -> int:
        key = _key(customer_id, "daily_count", date.today().isoformat())
        val = await self._r.get(key)
        return int(val) if val else 0

    async def increment_daily_count(self, customer_id: str) -> int:
        key = _key(customer_id, "daily_count", date.today().isoformat())
        count = await self._r.incr(key)
        # Expire at end of day — generous 48h TTL covers timezone variance
        await self._r.expire(key, 172800)
        return count

    # -- Pending notifications (pull-based for API clients) ------------------

    async def add_pending_notification(
        self, customer_id: str, notification: Dict[str, Any]
    ) -> None:
        key = _key(customer_id, "notifications")
        await self._r.rpush(key, json.dumps(notification))

    async def pop_pending_notifications(
        self, customer_id: str,
    ) -> List[Dict[str, Any]]:
        key = _key(customer_id, "notifications")
        pipe = self._r.pipeline()
        pipe.lrange(key, 0, -1)
        pipe.delete(key)
        results = await pipe.execute()
        raw_items = results[0]
        return [
            json.loads(item.decode() if isinstance(item, bytes) else item)
            for item in raw_items
        ]

    # -- Transaction tracking (for finance anomaly detection) ----------------

    _TXN_CAP = 100
    _TXN_TTL = 7776000  # 90 days

    async def record_transaction(
        self, customer_id: str, amount: float, category: str,
    ) -> None:
        key = _key(customer_id, "transactions")
        entry = json.dumps({
            "amount": amount,
            "category": category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        pipe = self._r.pipeline()
        pipe.rpush(key, entry)
        pipe.ltrim(key, -self._TXN_CAP, -1)
        pipe.expire(key, self._TXN_TTL)
        await pipe.execute()

    async def get_transaction_stats(self, customer_id: str) -> Dict[str, Any]:
        key = _key(customer_id, "transactions")
        raw = await self._r.lrange(key, 0, -1)
        if not raw:
            return {"count": 0, "total": 0.0, "average": 0.0}
        amounts = []
        for item in raw:
            decoded = item.decode() if isinstance(item, bytes) else item
            amounts.append(json.loads(decoded)["amount"])
        total = sum(amounts)
        return {"count": len(amounts), "total": total, "average": total / len(amounts)}

    async def get_latest_transaction(self, customer_id: str) -> Optional[Dict[str, Any]]:
        key = _key(customer_id, "transactions")
        raw = await self._r.lindex(key, -1)
        if raw is None:
            return None
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        return json.loads(decoded)

    # -- Notification lifecycle (persistent, with status) --------------------

    _NOTIF_TTL = 604800  # 7 days

    async def add_notification(
        self, customer_id: str, notification: Dict[str, Any],
    ) -> str:
        notif_id = f"notif_{uuid.uuid4().hex[:12]}"
        data = {**notification, "id": notif_id, "status": "pending", "snooze_until": ""}
        key = _key(customer_id, "notif", notif_id)
        idx_key = _key(customer_id, "notification_ids")
        pipe = self._r.pipeline()
        pipe.hset(key, mapping=data)
        pipe.expire(key, self._NOTIF_TTL)
        pipe.sadd(idx_key, notif_id)
        pipe.expire(idx_key, self._NOTIF_TTL)
        await pipe.execute()
        return notif_id

    async def get_notification(
        self, customer_id: str, notif_id: str,
    ) -> Optional[Dict[str, Any]]:
        key = _key(customer_id, "notif", notif_id)
        data = await self._r.hgetall(key)
        if not data:
            return None
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in data.items()
        }

    async def list_notifications(
        self, customer_id: str, *, now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        idx_key = _key(customer_id, "notification_ids")
        ids = await self._r.smembers(idx_key)
        result: list[Dict[str, Any]] = []
        for raw_id in ids:
            notif_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
            notif = await self.get_notification(customer_id, notif_id)
            if notif is None:
                continue
            status = notif.get("status", "pending")
            if status in ("read", "dismissed"):
                continue
            if status == "snoozed":
                snooze_until = notif.get("snooze_until", "")
                if snooze_until:
                    try:
                        if datetime.fromisoformat(snooze_until) > now:
                            continue
                    except (ValueError, TypeError):
                        pass
            result.append(notif)
        return result

    async def mark_notification_read(
        self, customer_id: str, notif_id: str,
    ) -> bool:
        key = _key(customer_id, "notif", notif_id)
        if not await self._r.exists(key):
            return False
        await self._r.hset(key, "status", "read")
        return True

    async def snooze_notification(
        self, customer_id: str, notif_id: str, until: datetime,
    ) -> bool:
        key = _key(customer_id, "notif", notif_id)
        if not await self._r.exists(key):
            return False
        pipe = self._r.pipeline()
        pipe.hset(key, mapping={"status": "snoozed", "snooze_until": until.isoformat()})
        await pipe.execute()
        return True

    async def dismiss_notification(
        self, customer_id: str, notif_id: str,
    ) -> bool:
        key = _key(customer_id, "notif", notif_id)
        if not await self._r.exists(key):
            return False
        await self._r.hset(key, "status", "dismissed")
        return True
