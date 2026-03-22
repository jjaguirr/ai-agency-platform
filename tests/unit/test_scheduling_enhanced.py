"""
Tests for scheduling specialist enhancements: preference learning.

- Learned default duration from past meetings
- Preferred hours influence slot ordering
- Buffer awareness warns on tight transitions
- Conflict details surfaced in create response
- All enhancements degrade gracefully without interaction_context
"""
import pytest
import fakeredis.aioredis
from datetime import datetime, timedelta
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

from src.agents.base.specialist import SpecialistTask, SpecialistStatus
from src.agents.context import InteractionContext, CalendarSnapshot, CustomerPreferences
from src.agents.executive_assistant import BusinessContext
from src.agents.specialists.scheduling import (
    SchedulingSpecialist,
    CalendarEvent,
    TimeSlot,
)
from src.proactive.state import ProactiveStateStore


# --- Fixtures ---------------------------------------------------------------

CUSTOMER_ID = "cust_sched_test"
FIXED_NOW = datetime(2026, 3, 21, 9, 0, 0)


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def ctx():
    return BusinessContext(
        business_name="Sparkle & Shine",
        industry="jewelry",
        current_tools=["Google Calendar"],
    )


class FakeCalendar:
    """In-memory calendar that returns predictable results."""

    def __init__(self, events: Optional[List[CalendarEvent]] = None):
        self._events = list(events or [])
        self._created: List[CalendarEvent] = []
        self._next_id = 100

    async def list_events(self, start: datetime, end: datetime) -> List[CalendarEvent]:
        return [e for e in self._events if e.start < end and e.end > start]

    async def create_event(
        self, title: str, start: datetime, end: datetime,
        attendees: List[str], location: Optional[str] = None,
    ) -> CalendarEvent:
        evt = CalendarEvent(
            id=f"evt_{self._next_id}",
            title=title, start=start, end=end,
            attendees=tuple(attendees), location=location,
        )
        self._next_id += 1
        self._events.append(evt)
        self._created.append(evt)
        return evt

    async def update_event(self, event_id, **kw):
        pass

    async def delete_event(self, event_id):
        pass

    async def is_free(self, start: datetime, end: datetime) -> bool:
        overlaps = [e for e in self._events if e.start < end and e.end > start]
        return len(overlaps) == 0

    async def find_slots(
        self, duration: timedelta, window_start: datetime, window_end: datetime,
    ) -> List[TimeSlot]:
        # Simple implementation: return slots at 9am, 10am, 14am, 15pm, 16pm
        slots = []
        for h in [9, 10, 14, 15, 16]:
            s = window_start.replace(hour=h, minute=0, second=0)
            e = s + duration
            if s >= window_start and e <= window_end:
                busy = any(ev.start < e and ev.end > s for ev in self._events)
                if not busy:
                    slots.append(TimeSlot(start=s, end=e))
        return slots


def _task(description, ctx, *, interaction_context=None, memories=None):
    return SpecialistTask(
        description=description,
        customer_id=CUSTOMER_ID,
        business_context=ctx,
        domain_memories=memories or [],
        interaction_context=interaction_context,
    )


# --- ProactiveStateStore: scheduling preference methods ---------------------

class TestSchedulingPreferenceStorage:
    @pytest.mark.asyncio
    async def test_record_and_get_preferred_duration(self, store):
        """Record several durations, get back the most common one."""
        for _ in range(3):
            await store.record_scheduling_preference(CUSTOMER_ID, 30, 10)
        await store.record_scheduling_preference(CUSTOMER_ID, 60, 14)

        result = await store.get_preferred_duration(CUSTOMER_ID)
        assert result == 30  # mode: 30 appears 3x vs 60 1x

    @pytest.mark.asyncio
    async def test_preferred_duration_none_when_empty(self, store):
        result = await store.get_preferred_duration(CUSTOMER_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_preferred_hours(self, store):
        """Hours ranked by frequency."""
        for _ in range(3):
            await store.record_scheduling_preference(CUSTOMER_ID, 30, 10)
        for _ in range(5):
            await store.record_scheduling_preference(CUSTOMER_ID, 30, 14)
        await store.record_scheduling_preference(CUSTOMER_ID, 30, 9)

        hours = await store.get_preferred_hours(CUSTOMER_ID)
        assert hours[0] == 14  # most frequent first
        assert 10 in hours
        assert 9 in hours

    @pytest.mark.asyncio
    async def test_preferred_hours_empty(self, store):
        hours = await store.get_preferred_hours(CUSTOMER_ID)
        assert hours == []

    @pytest.mark.asyncio
    async def test_set_and_get_buffer_minutes(self, store):
        await store.set_buffer_minutes(CUSTOMER_ID, 15)
        result = await store.get_buffer_minutes(CUSTOMER_ID)
        assert result == 15

    @pytest.mark.asyncio
    async def test_buffer_minutes_default(self, store):
        result = await store.get_buffer_minutes(CUSTOMER_ID)
        assert result == 0  # default: no buffer


# --- Create: learned duration -----------------------------------------------

class TestLearnedDuration:
    @pytest.mark.asyncio
    async def test_uses_learned_duration_when_no_explicit(self, store, ctx):
        """When user doesn't say duration and we have learned data, use it."""
        # Build preference: most meetings are 30m
        for _ in range(4):
            await store.record_scheduling_preference(CUSTOMER_ID, 30, 10)

        ic = InteractionContext(
            customer_preferences=CustomerPreferences(
                preferred_meeting_duration=30,
            ),
        )

        cal = FakeCalendar()
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW, proactive_state=store,
        )
        task = _task("schedule a meeting with John at 2pm", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        created = cal._created[0]
        duration_min = (created.end - created.start).total_seconds() / 60
        assert duration_min == 30

    @pytest.mark.asyncio
    async def test_falls_back_to_60m_without_context(self, ctx):
        """No interaction_context → 60m default."""
        cal = FakeCalendar()
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW,
        )
        task = _task("schedule a meeting with John at 2pm", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        created = cal._created[0]
        duration_min = (created.end - created.start).total_seconds() / 60
        assert duration_min == 60

    @pytest.mark.asyncio
    async def test_explicit_duration_overrides_learned(self, store, ctx):
        """'for 45 minutes' always wins over learned preference."""
        for _ in range(4):
            await store.record_scheduling_preference(CUSTOMER_ID, 30, 10)

        ic = InteractionContext(
            customer_preferences=CustomerPreferences(
                preferred_meeting_duration=30,
            ),
        )

        cal = FakeCalendar()
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW, proactive_state=store,
        )
        task = _task(
            "schedule a meeting with John at 2pm for 45 minutes",
            ctx, interaction_context=ic,
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        created = cal._created[0]
        duration_min = (created.end - created.start).total_seconds() / 60
        assert duration_min == 45


# --- Create: records preference after booking --------------------------------

class TestPreferenceRecording:
    @pytest.mark.asyncio
    async def test_records_duration_and_hour_after_create(self, store, ctx):
        """After a successful create, the duration and hour are recorded."""
        cal = FakeCalendar()
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW, proactive_state=store,
        )
        task = _task("schedule a meeting with John at 2pm for 30 minutes", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED

        # Verify preferences were recorded
        pref_dur = await store.get_preferred_duration(CUSTOMER_ID)
        # Only 1 sample — should still return it
        assert pref_dur == 30

        hours = await store.get_preferred_hours(CUSTOMER_ID)
        assert 14 in hours  # 2pm = hour 14


# --- Create: buffer warning -------------------------------------------------

class TestBufferWarning:
    @pytest.mark.asyncio
    async def test_warns_on_tight_transition(self, store, ctx):
        """When next event starts within buffer_minutes, summary warns."""
        await store.set_buffer_minutes(CUSTOMER_ID, 15)

        # Existing event at 3pm
        existing = CalendarEvent(
            id="evt_1", title="Team Standup",
            start=FIXED_NOW.replace(hour=15, minute=0),
            end=FIXED_NOW.replace(hour=15, minute=30),
        )
        cal = FakeCalendar(events=[existing])

        ic = InteractionContext(
            customer_preferences=CustomerPreferences(buffer_minutes=15),
            calendar_snapshot=CalendarSnapshot(
                events_next_24h=[{
                    "title": "Team Standup",
                    "start": existing.start.isoformat(),
                    "end": existing.end.isoformat(),
                }],
            ),
        )

        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW, proactive_state=store,
        )
        # Book at 2pm for 60m → ends at 3pm, which is exactly when Team Standup starts
        task = _task("schedule a meeting with John at 2pm", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        summary_lower = result.summary_for_ea.lower()
        assert "tight" in summary_lower or "buffer" in summary_lower or "back-to-back" in summary_lower

    @pytest.mark.asyncio
    async def test_no_buffer_warning_with_space(self, store, ctx):
        """Plenty of time before next event → no warning."""
        await store.set_buffer_minutes(CUSTOMER_ID, 15)

        # Existing event at 5pm — plenty of gap after 2pm meeting
        existing = CalendarEvent(
            id="evt_1", title="Team Standup",
            start=FIXED_NOW.replace(hour=17, minute=0),
            end=FIXED_NOW.replace(hour=17, minute=30),
        )
        cal = FakeCalendar(events=[existing])

        ic = InteractionContext(
            customer_preferences=CustomerPreferences(buffer_minutes=15),
            calendar_snapshot=CalendarSnapshot(
                events_next_24h=[{
                    "title": "Team Standup",
                    "start": existing.start.isoformat(),
                    "end": existing.end.isoformat(),
                }],
            ),
        )

        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW, proactive_state=store,
        )
        task = _task("schedule a meeting with John at 2pm", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        summary_lower = result.summary_for_ea.lower()
        assert "tight" not in summary_lower and "buffer" not in summary_lower and "back-to-back" not in summary_lower


# --- Slot find: preferred hours ranking -------------------------------------

class TestSlotPreferredHours:
    @pytest.mark.asyncio
    async def test_slots_sorted_by_preferred_hours(self, store, ctx):
        """When preferred hours available, slots near those hours come first."""
        # Prefer 2pm (14h) meetings
        for _ in range(5):
            await store.record_scheduling_preference(CUSTOMER_ID, 30, 14)

        ic = InteractionContext(
            customer_preferences=CustomerPreferences(
                preferred_hours=[14, 15],
            ),
        )

        cal = FakeCalendar()  # will return slots at 9, 10, 14, 15, 16
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW, proactive_state=store,
        )
        task = _task("find me 30 minutes this week", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        slots = result.payload["slots"]
        assert len(slots) > 0
        # First slot should be at 14:00 (preferred) rather than 9:00
        first_start = slots[0]["start"]
        assert "T14:00" in first_start

    @pytest.mark.asyncio
    async def test_slot_order_unchanged_without_preferences(self, ctx):
        """No preferences → original order (earliest first)."""
        cal = FakeCalendar()
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW,
        )
        task = _task("find me 30 minutes this week", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        slots = result.payload["slots"]
        if len(slots) >= 2:
            # Should be in chronological order (9am first)
            assert slots[0]["start"] <= slots[1]["start"]


# --- Graceful degradation ---------------------------------------------------

class TestSchedulingGracefulDegradation:
    @pytest.mark.asyncio
    async def test_create_works_without_proactive_store(self, ctx):
        """No proactive_state → no preference recording, no crash."""
        cal = FakeCalendar()
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW,
        )
        task = _task("schedule a meeting with John at 2pm", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert len(cal._created) == 1

    @pytest.mark.asyncio
    async def test_create_works_without_interaction_context(self, store, ctx):
        """proactive_state present but no interaction_context → still works."""
        cal = FakeCalendar()
        specialist = SchedulingSpecialist(
            calendar=cal, clock=lambda: FIXED_NOW, proactive_state=store,
        )
        task = _task("schedule a meeting with John at 2pm", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        duration_min = (cal._created[0].end - cal._created[0].start).total_seconds() / 60
        assert duration_min == 60  # default
