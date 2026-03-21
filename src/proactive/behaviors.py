"""Built-in proactive behaviors — morning briefing, follow-up tracker, idle nudge."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List, Optional, Sequence
from zoneinfo import ZoneInfo

from .state import ProactiveStateStore
from .triggers import Priority, ProactiveTrigger

logger = logging.getLogger(__name__)


@dataclass
class BehaviorConfig:
    briefing_hour: int = 8
    briefing_enabled: bool = True
    timezone: str = "UTC"
    idle_nudge_minutes: int = 120
    # Personality — used by the briefing to shape tone and attribution
    tone: str = "professional"
    ea_name: str = "Assistant"
    language: str = "en"
    # Legacy field — IdleNudgeBehavior migrated to minutes in V2; kept
    # so pre-V2 tests that construct BehaviorConfig(idle_days=...) still
    # parse. Not read by any behavior.
    idle_days: int = 7


# Extra briefing sources are async callables (customer_id → text | None).
# Each source is wrapped in try/except — a dead specialist domain must
# not kill the whole briefing.
BriefingSource = Callable[[str], Awaitable[Optional[str]]]

# Greeting by tone. Keys align with the PersonalitySettings.tone Literal
# in src/api/schemas.py. Anything unmapped falls back to professional.
_GREETING = {
    "professional": "Good morning. Here is your briefing.",
    "friendly": "Good morning! Here's what's on today:",
    "concise": "Briefing:",
    "detailed": "Good morning. Here is your full briefing for today.",
}


class MorningBriefingBehavior:
    def __init__(
        self,
        state_store: ProactiveStateStore,
        *,
        clock: Optional[Callable[[], datetime]] = None,
        extra_sources: Sequence[BriefingSource] = (),
    ) -> None:
        self._state = state_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._extra_sources = extra_sources

    async def check(
        self, customer_id: str, config: BehaviorConfig,
    ) -> Optional[ProactiveTrigger]:
        if not config.briefing_enabled:
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

        # Gather sections. Each source either contributes a text section
        # or is skipped. No section → no briefing.
        sections: list[str] = []

        follow_ups = await self._state.list_follow_ups(customer_id)
        if follow_ups:
            lines = [f"You have {len(follow_ups)} pending follow-up(s)."]
            lines.extend(f"  - {fu.get('commitment', 'unknown')}" for fu in follow_ups)
            sections.append("\n".join(lines))

        for source in self._extra_sources:
            try:
                section = await source(customer_id)
            except Exception:
                logger.exception(
                    "Briefing source %s failed for customer=%s; skipping",
                    getattr(source, "__name__", repr(source)), customer_id,
                )
                continue
            if section:
                sections.append(section)

        if not sections:
            return None

        greeting = _GREETING.get(config.tone, _GREETING["professional"])
        body = "\n".join(sections)
        message = f"{greeting}\n{body}"
        # Sign with the EA's configured name — but skip the placeholder,
        # it reads as generic rather than personal.
        if config.ea_name and config.ea_name != "Assistant":
            message += f"\n— {config.ea_name}"

        return ProactiveTrigger(
            domain="ea",
            trigger_type="morning_briefing",
            priority=Priority.MEDIUM,
            title="Morning Briefing",
            payload={"follow_ups": follow_ups, "language": config.language},
            suggested_message=message,
            cooldown_key="ea:morning_briefing",
        )


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
        # Zero disables the nudge entirely (dashboard semantics).
        if config.idle_nudge_minutes <= 0:
            return None

        now = self._clock()

        last_interaction = await self._state.get_last_interaction_time(customer_id)
        if last_interaction is None:
            return None

        idle_delta = now - last_interaction
        threshold = timedelta(minutes=config.idle_nudge_minutes)
        if idle_delta < threshold:
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
        cooldown_window = config.idle_nudge_minutes * 60
        await self._state.record_cooldown(customer_id, cooldown_key, window_seconds=cooldown_window)

        idle_minutes = int(idle_delta.total_seconds() // 60)
        # Human-readable phrasing switches at the day boundary.
        if idle_minutes >= 1440:
            span = f"{idle_minutes // 1440} day(s)"
        else:
            span = f"{idle_minutes} minute(s)"

        return ProactiveTrigger(
            domain="ea",
            trigger_type="idle_nudge",
            priority=Priority.LOW,
            title="Idle check-in",
            payload={"idle_minutes": idle_minutes, "pending_count": len(follow_ups)},
            suggested_message=f"Hi! It's been {span} since we last spoke. You have {len(follow_ups)} pending item(s) — want to catch up?",
            cooldown_key=cooldown_key,
        )


class DomainEventBehavior:
    """Drain the domain-event queue and convert each event to a trigger.

    Specialists stage events synchronously at detection time (finance
    anomaly during expense processing, schedule conflict during event
    creation). This behavior is the bridge to the noise gate: events sit
    in Redis until the next heartbeat tick, then get the same
    threshold/quiet-hours/cap treatment as every other trigger.
    """

    def __init__(self, state_store: ProactiveStateStore) -> None:
        self._state = state_store

    async def check(self, customer_id: str) -> List[ProactiveTrigger]:
        events = await self._state.drain_domain_events(customer_id)
        triggers: list[ProactiveTrigger] = []
        for event in events:
            etype = event.get("type")
            if not etype:
                logger.warning(
                    "Domain event without type for customer=%s: %r; dropping",
                    customer_id, event,
                )
                continue
            converter = _EVENT_CONVERTERS.get(etype, _convert_unknown)
            triggers.append(converter(event))
        return triggers


def _convert_finance_anomaly(event: dict) -> ProactiveTrigger:
    amount = event.get("amount", 0)
    baseline = event.get("baseline")
    category = event.get("category", "")
    msg = f"Heads up: a ${amount:g} expense"
    if category:
        msg += f" ({category})"
    msg += " looks unusual"
    if baseline:
        msg += f" — about {amount/baseline:.1f}× your typical spend"
    msg += ". Want me to look into it?"
    # Cooldown keyed on amount+category so the same anomaly doesn't
    # re-fire if the event somehow gets re-staged, but a different
    # anomaly on the same day still gets through.
    return ProactiveTrigger(
        domain="finance",
        trigger_type="finance_anomaly",
        priority=Priority.HIGH,
        title="Unusual expense",
        payload=event,
        suggested_message=msg,
        cooldown_key=f"finance_anomaly:{amount:g}:{category}",
    )


def _convert_schedule_conflict(event: dict) -> ProactiveTrigger:
    new_event = event.get("new_event", {})
    conflicts = event.get("conflicts_with", [])
    new_title = new_event.get("title", "a new event")
    conflict_titles = ", ".join(
        c.get("title", "an existing event") for c in conflicts
    ) or "an existing event"
    msg = (
        f"Calendar conflict: '{new_title}' overlaps with {conflict_titles}. "
        f"Want me to reschedule one of them?"
    )
    return ProactiveTrigger(
        domain="scheduling",
        trigger_type="schedule_conflict",
        priority=Priority.HIGH,
        title="Calendar conflict",
        payload=event,
        suggested_message=msg,
        cooldown_key=f"schedule_conflict:{new_event.get('start', new_title)}",
    )


def _convert_unknown(event: dict) -> ProactiveTrigger:
    etype = event.get("type", "unknown")
    return ProactiveTrigger(
        domain="ea",
        trigger_type=etype,
        priority=Priority.MEDIUM,
        title=f"Notice: {etype}",
        payload=event,
        suggested_message=f"Something came up in {etype}: {event}",
        cooldown_key=None,
    )


_EVENT_CONVERTERS: dict[str, Callable[[dict], ProactiveTrigger]] = {
    "finance_anomaly": _convert_finance_anomaly,
    "schedule_conflict": _convert_schedule_conflict,
}
