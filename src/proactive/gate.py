"""Noise control gate — filters proactive triggers before delivery.

Check order: cooldown → priority threshold → quiet hours → daily cap.
URGENT bypasses quiet hours and daily cap but not cooldown.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .state import ProactiveStateStore
from .triggers import Priority, ProactiveTrigger

logger = logging.getLogger(__name__)


@dataclass
class NoiseConfig:
    cooldown_window: int = 86400  # 24h
    priority_threshold: Priority = Priority.MEDIUM
    quiet_start: int = 22  # hour, customer local
    quiet_end: int = 7     # hour, customer local
    daily_cap: int = 5
    timezone: str = "UTC"


@dataclass
class GateDecision:
    allowed: bool
    reason: str


class NoiseGate:
    def __init__(self, state_store: ProactiveStateStore) -> None:
        self._state = state_store

    async def evaluate(
        self,
        customer_id: str,
        trigger: ProactiveTrigger,
        config: NoiseConfig,
        *,
        now: Optional[datetime] = None,
    ) -> GateDecision:
        now = now or datetime.now(timezone.utc)

        # 1. Cooldown — even URGENT respects cooldown
        if trigger.cooldown_key:
            if await self._state.is_cooling_down(customer_id, trigger.cooldown_key):
                return GateDecision(allowed=False, reason=f"cooldown:{trigger.cooldown_key}")

        # 2. Priority threshold
        if trigger.priority < config.priority_threshold:
            return GateDecision(allowed=False, reason="below_threshold")

        # 3. Quiet hours — URGENT overrides
        if trigger.priority < Priority.URGENT:
            if self._in_quiet_hours(now, config):
                return GateDecision(allowed=False, reason="quiet_hours")

        # 4. Daily cap — URGENT exempt
        if trigger.priority < Priority.URGENT:
            count = await self._state.get_daily_count(customer_id)
            if count >= config.daily_cap:
                return GateDecision(allowed=False, reason="daily_cap")

        return GateDecision(allowed=True, reason="delivered")

    @staticmethod
    def _in_quiet_hours(now: datetime, config: NoiseConfig) -> bool:
        tz = ZoneInfo(config.timezone)
        local_hour = now.astimezone(tz).hour
        start, end = config.quiet_start, config.quiet_end
        if start > end:
            # Wraps midnight: e.g. 22:00 – 07:00
            return local_hour >= start or local_hour < end
        else:
            return start <= local_hour < end
