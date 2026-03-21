"""Redis-backed proactive state store.

Keys use the pattern ``proactive:{customer_id}:{subkey}`` and are
independent of the conversation persistence layer.
"""
from __future__ import annotations

import json
import logging
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
