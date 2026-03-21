"""Per-customer settings loader for the proactive system.

Reads the same ``settings:{customer_id}`` Redis key that the dashboard
writes (see ``src/api/routes/settings.py``) and projects it onto the
proactive system's own config dataclasses. The dashboard model is the
source of truth for schema and defaults — this module just reshapes it.

Caching: plain in-process dict keyed by customer_id with a monotonic
TTL. The heartbeat ticks every 5 minutes; a 3-minute TTL means at most
one Redis read per customer per tick, and settings changes propagate
within two ticks. No pub/sub, no invalidation RPC — TTL expiry is fine
per the V2 spec.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

from src.api.schemas import Settings

from .behaviors import BehaviorConfig
from .gate import NoiseConfig
from .triggers import Priority

logger = logging.getLogger(__name__)

_REDIS_KEY = "settings:{customer_id}"


def _parse_hour(hhmm: str, fallback: int) -> int:
    """Extract the hour from an ``HH:MM`` string. Gate operates at hour
    granularity, so minutes are dropped."""
    try:
        return int(hhmm.split(":", 1)[0])
    except (ValueError, AttributeError, IndexError):
        return fallback


class CustomerSettingsLoader:

    def __init__(
        self,
        redis_client,
        *,
        ttl_seconds: int = 180,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._r = redis_client
        self._ttl = ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # customer_id → (Settings, expires_at_epoch_seconds)
        self._cache: Dict[str, Tuple[Settings, float]] = {}

    async def _load(self, customer_id: str) -> Settings:
        now_ts = self._clock().timestamp()
        cached = self._cache.get(customer_id)
        if cached is not None and cached[1] > now_ts:
            return cached[0]

        settings = await self._fetch(customer_id)
        self._cache[customer_id] = (settings, now_ts + self._ttl)
        return settings

    async def _fetch(self, customer_id: str) -> Settings:
        raw = await self._r.get(_REDIS_KEY.format(customer_id=customer_id))
        if raw is None:
            return Settings()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return Settings.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "Malformed settings for customer=%s (%s); using defaults",
                customer_id, e,
            )
            return Settings()

    # --- Projections --------------------------------------------------------

    async def noise_config_for(self, customer_id: str) -> NoiseConfig:
        s = await self._load(customer_id)
        # Quiet hours are the inverse of working hours: quiet starts when
        # work ends, quiet ends when work starts. The gate already handles
        # the midnight wrap (quiet_start > quiet_end).
        return NoiseConfig(
            priority_threshold=Priority[s.proactive.priority_threshold],
            daily_cap=s.proactive.daily_cap,
            quiet_start=_parse_hour(s.working_hours.end, fallback=18),
            quiet_end=_parse_hour(s.working_hours.start, fallback=9),
            timezone=s.working_hours.timezone,
        )

    async def behavior_config_for(self, customer_id: str) -> BehaviorConfig:
        s = await self._load(customer_id)
        return BehaviorConfig(
            briefing_hour=_parse_hour(s.briefing.time, fallback=8),
            briefing_enabled=s.briefing.enabled,
            timezone=s.working_hours.timezone,
            idle_nudge_minutes=s.proactive.idle_nudge_minutes,
            tone=s.personality.tone,
            ea_name=s.personality.name,
            language=s.personality.language,
        )
