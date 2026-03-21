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

    async def peek_pending_notifications(
        self, customer_id: str,
    ) -> List[Dict[str, Any]]:
        """Read pending notifications without consuming them."""
        key = _key(customer_id, "notifications")
        raw_items = await self._r.lrange(key, 0, -1)
        return [
            json.loads(item.decode() if isinstance(item, bytes) else item)
            for item in raw_items
        ]

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
