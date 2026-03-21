"""Per-customer settings cache — reads settings:{customer_id} from Redis.

Converts dashboard-stored Settings into NoiseConfig + BehaviorConfig with
short TTL in-memory caching to avoid hitting Redis every heartbeat tick.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from ..api.schemas import Settings
from .behaviors import BehaviorConfig
from .gate import NoiseConfig
from .triggers import Priority

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "settings:{customer_id}"


@dataclass
class PersonalityConfig:
    tone: str = "professional"
    language: str = "en"
    name: str = "Assistant"


@dataclass
class CustomerConfig:
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    briefing_enabled: bool = True
    connected_services: Dict[str, bool] = field(default_factory=lambda: {"calendar": False, "n8n": False})
    anomaly_threshold: float = 2.0
    monthly_budget: Optional[float] = None


def _parse_hour(time_str: str) -> int:
    """Parse HH:MM string and return the hour component."""
    try:
        return int(time_str.split(":")[0])
    except (ValueError, IndexError):
        return 0


def _build_config(settings: Settings) -> CustomerConfig:
    tz = settings.working_hours.timezone
    quiet_start = _parse_hour(settings.working_hours.end)
    quiet_end = _parse_hour(settings.working_hours.start)

    idle_days = max(1, settings.proactive.idle_nudge_minutes // 1440)

    noise = NoiseConfig(
        priority_threshold=Priority[settings.proactive.priority_threshold],
        daily_cap=settings.proactive.daily_cap,
        timezone=tz,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
    )

    behavior = BehaviorConfig(
        briefing_hour=_parse_hour(settings.briefing.time),
        timezone=tz,
        idle_days=idle_days,
    )

    personality = PersonalityConfig(
        tone=settings.personality.tone,
        language=settings.personality.language,
        name=settings.personality.name,
    )

    connected = {
        "calendar": settings.connected_services.calendar,
        "n8n": settings.connected_services.n8n,
    }

    anomaly_threshold = getattr(settings.proactive, "anomaly_threshold", 2.0)
    monthly_budget = getattr(settings.proactive, "monthly_budget", None)

    return CustomerConfig(
        noise=noise,
        behavior=behavior,
        personality=personality,
        briefing_enabled=settings.briefing.enabled,
        connected_services=connected,
        anomaly_threshold=anomaly_threshold,
        monthly_budget=monthly_budget,
    )


@dataclass
class _CacheEntry:
    config: CustomerConfig
    fetched_at: float  # monotonic-ish timestamp


class CustomerSettingsCache:
    def __init__(
        self,
        redis_client,
        *,
        ttl_seconds: int = 120,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._r = redis_client
        self._ttl = ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: Dict[str, _CacheEntry] = {}

    async def get(self, customer_id: str) -> CustomerConfig:
        now = self._clock().timestamp()
        entry = self._cache.get(customer_id)
        if entry is not None and (now - entry.fetched_at) < self._ttl:
            return entry.config

        config = await self._fetch(customer_id)
        self._cache[customer_id] = _CacheEntry(config=config, fetched_at=now)
        return config

    def invalidate(self, customer_id: str) -> None:
        self._cache.pop(customer_id, None)

    async def _fetch(self, customer_id: str) -> CustomerConfig:
        key = _SETTINGS_KEY.format(customer_id=customer_id)
        try:
            raw = await self._r.get(key)
            if raw is None:
                return CustomerConfig()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            settings = Settings.model_validate(json.loads(raw))
            return _build_config(settings)
        except Exception:
            logger.warning(
                "Failed to load settings for customer=%s, using defaults",
                customer_id, exc_info=True,
            )
            return CustomerConfig()
