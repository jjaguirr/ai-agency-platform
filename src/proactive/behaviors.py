"""Built-in proactive behaviors — morning briefing, follow-up tracker, idle nudge.

Each behavior implements ``check(customer_id, config, **kwargs)`` and returns
``None`` or one-or-more ``ProactiveTrigger`` instances. The heartbeat daemon
calls them once per tick per customer.

Morning briefing supports personality-aware formatting via ``_format_briefing``
(professional / friendly / concise tones) and can be disabled per customer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable, List, Optional
from zoneinfo import ZoneInfo

from .state import ProactiveStateStore
from .triggers import Priority, ProactiveTrigger

if TYPE_CHECKING:
    from .settings_cache import PersonalityConfig

logger = logging.getLogger(__name__)


@dataclass
class BehaviorConfig:
    briefing_hour: int = 8
    timezone: str = "UTC"
    idle_days: int = 7


class MorningBriefingBehavior:
    def __init__(
        self,
        state_store: ProactiveStateStore,
        *,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._state = state_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def check(
        self,
        customer_id: str,
        config: BehaviorConfig,
        *,
        personality: Optional[PersonalityConfig] = None,
        briefing_enabled: bool = True,
    ) -> Optional[ProactiveTrigger]:
        if not briefing_enabled:
            return None

        now = self._clock()
        tz = ZoneInfo(config.timezone)
        local_now = now.astimezone(tz)

        # Not yet briefing hour
        if local_now.hour < config.briefing_hour:
            return None

        # Already sent today?
        last = await self._state.get_last_briefing_time(customer_id)
        if last is not None:
            last_local = last.astimezone(tz)
            if last_local.date() == local_now.date():
                return None

        # Gather data
        follow_ups = await self._state.list_follow_ups(customer_id)

        # Skip if nothing to report
        if not follow_ups:
            return None

        # Build briefing
        parts = []
        if follow_ups:
            parts.append(f"You have {len(follow_ups)} pending follow-up(s).")
            for fu in follow_ups:
                parts.append(f"  - {fu.get('commitment', 'unknown')}")

        message = _format_briefing(parts, personality)

        return ProactiveTrigger(
            domain="ea",
            trigger_type="morning_briefing",
            priority=Priority.MEDIUM,
            title="Morning Briefing",
            payload={"follow_ups": follow_ups},
            suggested_message=message,
            cooldown_key="ea:morning_briefing",
        )


def _format_briefing(
    parts: list[str],
    personality: Optional[PersonalityConfig] = None,
) -> str:
    """Build briefing message adapted to personality settings."""
    if personality is None:
        return "Good morning! Here's your briefing for today.\n" + "\n".join(parts)

    tone = personality.tone
    name = personality.name
    body = "\n".join(parts)

    if tone == "concise":
        return f"Briefing for {name}:\n{body}" if name != "Assistant" else f"Briefing:\n{body}"
    elif tone == "friendly":
        greeting = f"Hey {name}!" if name != "Assistant" else "Hey there!"
        return f"{greeting} Here's what's on your plate today.\n{body}"
    else:
        # professional / detailed / default
        greeting = f"Good morning, {name}!" if name != "Assistant" else "Good morning!"
        return f"{greeting} Here's your briefing for today.\n{body}"


class FollowUpTrackerBehavior:
    REMINDER_WINDOW = timedelta(hours=24)

    def __init__(
        self,
        state_store: ProactiveStateStore,
        *,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._state = state_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def check(self, customer_id: str) -> List[ProactiveTrigger]:
        now = self._clock()
        follow_ups = await self._state.list_follow_ups(customer_id)
        triggers: list[ProactiveTrigger] = []

        for fu in follow_ups:
            deadline_str = fu.get("deadline")
            if not deadline_str:
                continue
            try:
                deadline = datetime.fromisoformat(deadline_str)
            except (ValueError, TypeError):
                continue

            time_until = deadline - now
            overdue = time_until < timedelta(0)
            within_window = timedelta(0) <= time_until <= self.REMINDER_WINDOW

            if overdue:
                commitment = fu.get("commitment", "an item")
                triggers.append(ProactiveTrigger(
                    domain="ea",
                    trigger_type="follow_up",
                    priority=Priority.HIGH,
                    title=f"Overdue: {commitment}",
                    payload=fu,
                    suggested_message=f"Reminder: You committed to '{commitment}' — it's now overdue.",
                    cooldown_key=f"follow_up:{fu.get('id', 'unknown')}",
                ))
            elif within_window:
                commitment = fu.get("commitment", "an item")
                triggers.append(ProactiveTrigger(
                    domain="ea",
                    trigger_type="follow_up",
                    priority=Priority.MEDIUM,
                    title=f"Due soon: {commitment}",
                    payload=fu,
                    suggested_message=f"Reminder: You said you'd '{commitment}' — the deadline is approaching.",
                    cooldown_key=f"follow_up:{fu.get('id', 'unknown')}",
                ))

        return triggers


class IdleNudgeBehavior:
    def __init__(
        self,
        state_store: ProactiveStateStore,
        *,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._state = state_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def check(
        self, customer_id: str, config: BehaviorConfig,
    ) -> Optional[ProactiveTrigger]:
        now = self._clock()

        last_interaction = await self._state.get_last_interaction_time(customer_id)
        if last_interaction is None:
            return None

        idle_delta = now - last_interaction
        if idle_delta < timedelta(days=config.idle_days):
            return None

        # Check pending items exist
        follow_ups = await self._state.list_follow_ups(customer_id)
        if not follow_ups:
            return None

        # Check not already nudged this idle period
        cooldown_key = "ea:idle_nudge"
        if await self._state.is_cooling_down(customer_id, cooldown_key):
            return None

        # Record cooldown so we don't nudge again until new interaction
        cooldown_window = config.idle_days * 86400
        await self._state.record_cooldown(customer_id, cooldown_key, window_seconds=cooldown_window)

        return ProactiveTrigger(
            domain="ea",
            trigger_type="idle_nudge",
            priority=Priority.LOW,
            title="Idle check-in",
            payload={"idle_days": idle_delta.days, "pending_count": len(follow_ups)},
            suggested_message=f"Hi! It's been {idle_delta.days} days since we last spoke. You have {len(follow_ups)} pending item(s) — want to catch up?",
            cooldown_key=cooldown_key,
        )
