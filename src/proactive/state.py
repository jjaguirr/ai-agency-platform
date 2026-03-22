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
    # Hash storage: {notif_id → json}. Each record carries its own status
    # so GET can be non-destructive and the customer explicitly marks
    # read/snoozed/dismissed.

    async def add_pending_notification(
        self, customer_id: str, notification: Dict[str, Any]
    ) -> str:
        key = _key(customer_id, "notifications")
        notif = dict(notification)
        # Dispatcher previously used id(trigger) — useless across processes.
        # Generate here if the caller didn't supply one.
        notif_id = notif.get("id") or f"notif_{uuid.uuid4().hex[:12]}"
        notif["id"] = notif_id
        notif.setdefault("status", "pending")
        await self._r.hset(key, notif_id, json.dumps(notif))
        return notif_id

    async def list_pending_notifications(
        self, customer_id: str, *, now: datetime,
    ) -> List[Dict[str, Any]]:
        key = _key(customer_id, "notifications")
        raw = await self._r.hgetall(key)
        out: list[dict] = []
        for v in raw.values():
            decoded = v.decode() if isinstance(v, bytes) else v
            n = json.loads(decoded)
            status = n.get("status", "pending")
            if status == "pending":
                out.append(n)
            elif status == "snoozed":
                until_raw = n.get("snooze_until")
                if until_raw and datetime.fromisoformat(until_raw) <= now:
                    out.append(n)
        return out

    async def mark_notification_read(
        self, customer_id: str, notification_id: str,
    ) -> bool:
        return await self._set_status(customer_id, notification_id, "read")

    async def snooze_notification(
        self, customer_id: str, notification_id: str, until: datetime,
    ) -> bool:
        return await self._set_status(
            customer_id, notification_id, "snoozed",
            snooze_until=until.isoformat(),
        )

    async def dismiss_notification(
        self, customer_id: str, notification_id: str,
    ) -> bool:
        key = _key(customer_id, "notifications")
        deleted = await self._r.hdel(key, notification_id)
        return deleted > 0

    async def _set_status(
        self, customer_id: str, notification_id: str, status: str, **extra: str,
    ) -> bool:
        key = _key(customer_id, "notifications")
        raw = await self._r.hget(key, notification_id)
        if raw is None:
            return False
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        n = json.loads(decoded)
        n["status"] = status
        n.update(extra)
        await self._r.hset(key, notification_id, json.dumps(n))
        return True

    # -- Domain events (specialist → heartbeat staging) ----------------------
    # Specialists detect anomalies/conflicts synchronously during task
    # execution but notifications must route through the noise gate on
    # the next heartbeat tick. This queue is the hand-off.

    async def add_domain_event(
        self, customer_id: str, event: Dict[str, Any],
    ) -> None:
        key = _key(customer_id, "domain_events")
        await self._r.rpush(key, json.dumps(event))

    async def drain_domain_events(
        self, customer_id: str,
    ) -> List[Dict[str, Any]]:
        key = _key(customer_id, "domain_events")
        pipe = self._r.pipeline()
        pipe.lrange(key, 0, -1)
        pipe.delete(key)
        results = await pipe.execute()
        raw_items = results[0]
        return [
            json.loads(item.decode() if isinstance(item, bytes) else item)
            for item in raw_items
        ]

    # -- Transaction baseline (finance anomaly detection) --------------------
    # Running count+sum in a hash. No decay — good enough for "is this
    # 2× my normal spend." Float sum stored as string because HINCRBYFLOAT
    # in fakeredis returns inconsistently typed results; plain get/set
    # keeps behaviour predictable across real/fake Redis.

    _TX_MIN_SAMPLES = 3

    async def record_transaction(self, customer_id: str, amount: float) -> None:
        key = _key(customer_id, "tx_stats")
        pipe = self._r.pipeline()
        pipe.hincrby(key, "count", 1)
        pipe.hincrbyfloat(key, "sum", amount)
        await pipe.execute()

    async def get_transaction_baseline(self, customer_id: str) -> Optional[float]:
        key = _key(customer_id, "tx_stats")
        raw = await self._r.hgetall(key)
        if not raw:
            return None
        # Normalise bytes→str across real/fake Redis
        stats = {
            (k.decode() if isinstance(k, bytes) else k):
            (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }
        count = int(stats.get("count", 0))
        if count < self._TX_MIN_SAMPLES:
            return None
        total = float(stats.get("sum", 0.0))
        return total / count

    # -- Workflow execution tracking (n8n failure detection) -----------------
    # One string per workflow: the most-recent execution ID we've already
    # processed. WorkflowFailureBehavior walks newest-first executions
    # until it hits this ID; anything newer is new-to-us.

    async def get_last_seen_execution(
        self, customer_id: str, workflow_id: str,
    ) -> Optional[str]:
        key = _key(customer_id, "wf_last_exec", workflow_id)
        val = await self._r.get(key)
        if val is None:
            return None
        return val.decode() if isinstance(val, bytes) else val

    async def set_last_seen_execution(
        self, customer_id: str, workflow_id: str, execution_id: str,
    ) -> None:
        key = _key(customer_id, "wf_last_exec", workflow_id)
        await self._r.set(key, execution_id)

    # -- Budget tracking (finance pattern awareness) -------------------------

    async def set_budget(
        self, customer_id: str, category: str, limit: float,
    ) -> None:
        key = _key(customer_id, "budget", category)
        await self._r.set(key, str(limit))

    async def get_budget(
        self, customer_id: str, category: str,
    ) -> Optional[float]:
        key = _key(customer_id, "budget", category)
        val = await self._r.get(key)
        if val is None:
            return None
        raw = val.decode() if isinstance(val, bytes) else val
        return float(raw)

    async def get_all_budgets(self, customer_id: str) -> Dict[str, float]:
        # Scan for budget keys. Pattern: proactive:{cid}:budget:*
        prefix = _key(customer_id, "budget", "")
        budgets: Dict[str, float] = {}
        cursor = 0
        while True:
            cursor, keys = await self._r.scan(cursor, match=f"{prefix}*", count=50)
            for k in keys:
                raw_key = k.decode() if isinstance(k, bytes) else k
                category = raw_key.split(":")[-1]
                val = await self._r.get(k)
                if val is not None:
                    raw_val = val.decode() if isinstance(val, bytes) else val
                    budgets[category] = float(raw_val)
            if cursor == 0:
                break
        return budgets

    # -- Scheduling preference learning ----------------------------------------
    # Durations stored as a capped list (most recent 50). Hours stored in a
    # sorted set keyed by score (frequency). Buffer is a plain string.

    _SCHED_MAX_SAMPLES = 50

    async def record_scheduling_preference(
        self, customer_id: str, duration_minutes: int, hour: int,
    ) -> None:
        dur_key = _key(customer_id, "sched", "durations")
        hour_key = _key(customer_id, "sched", "preferred_hours")
        pipe = self._r.pipeline()
        pipe.rpush(dur_key, str(duration_minutes))
        pipe.ltrim(dur_key, -self._SCHED_MAX_SAMPLES, -1)
        pipe.zincrby(hour_key, 1, str(hour))
        await pipe.execute()

    async def get_preferred_duration(self, customer_id: str) -> Optional[int]:
        key = _key(customer_id, "sched", "durations")
        raw = await self._r.lrange(key, 0, -1)
        if not raw:
            return None
        durations = [
            int(v.decode() if isinstance(v, bytes) else v) for v in raw
        ]
        # Return mode (most common duration)
        from collections import Counter
        counts = Counter(durations)
        return counts.most_common(1)[0][0]

    async def get_preferred_hours(self, customer_id: str) -> List[int]:
        key = _key(customer_id, "sched", "preferred_hours")
        # ZREVRANGE returns highest-score first
        raw = await self._r.zrevrange(key, 0, -1)
        return [int(v.decode() if isinstance(v, bytes) else v) for v in raw]

    async def set_buffer_minutes(self, customer_id: str, minutes: int) -> None:
        key = _key(customer_id, "sched", "buffer_minutes")
        await self._r.set(key, str(minutes))

    async def get_buffer_minutes(self, customer_id: str) -> int:
        key = _key(customer_id, "sched", "buffer_minutes")
        val = await self._r.get(key)
        if val is None:
            return 0
        return int(val.decode() if isinstance(val, bytes) else val)
