"""
Unit tests for SchedulingSpecialist preference learning.

The specialist already creates events; these tests cover the preference
layer: learned default duration, preferred time slots, buffer respect,
and conflict surfacing in the response (not just the proactive channel).

Preference state lives in ProactiveStateStore (Redis); stubbed via
fakeredis. Calendar I/O stubbed by shape-conforming double.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import fakeredis.aioredis

from src.agents.specialists.scheduling import (
    SchedulingSpecialist,
    CalendarEvent,
    TimeSlot,
)
from src.agents.base.specialist import SpecialistTask, SpecialistStatus
from src.agents.executive_assistant import BusinessContext
from src.proactive.state import ProactiveStateStore


# Thursday 2026-03-19, 10:00. "tomorrow" = Friday 2026-03-20.
_NOW = datetime(2026, 3, 19, 10, 0)


def _clock():
    return _NOW


# --- Calendar double --------------------------------------------------------

class StubCalendar:
    def __init__(self, events=None):
        self._events = list(events or [])
        self._next_id = 1000
        self.created = []

    async def list_events(self, start, end):
        return [e for e in self._events if e.start < end and e.end > start]

    async def create_event(self, title, start, end, attendees, location=None):
        evt = CalendarEvent(
            id=f"evt_{self._next_id}", title=title,
            start=start, end=end, attendees=tuple(attendees),
            location=location,
        )
        self._next_id += 1
        self._events.append(evt)
        self.created.append(evt)
        return evt

    async def update_event(self, event_id, **kw):
        raise NotImplementedError

    async def delete_event(self, event_id):
        raise NotImplementedError

    async def is_free(self, start, end):
        return not any(
            e.start < end and e.end > start for e in self._events
        )

    async def find_slots(self, duration, window_start, window_end):
        return [TimeSlot(window_start, window_start + duration)]


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(redis):
    return ProactiveStateStore(redis)


@pytest.fixture
def ctx():
    return BusinessContext(
        business_name="Acme Co",
        current_tools=["Google Calendar"],
    )


def _task(desc, *, customer_id="c1", ctx=None):
    return SpecialistTask(
        description=desc,
        customer_id=customer_id,
        business_context=ctx or BusinessContext(business_name="Acme Co"),
        domain_memories=[],
    )


# --- Default duration learning ----------------------------------------------

class TestDefaultDuration:
    @pytest.mark.asyncio
    async def test_duration_recorded_on_create(self, store, ctx):
        cal = StubCalendar()
        spec = SchedulingSpecialist(
            calendar=cal, clock=_clock, proactive_state=store,
        )
        await spec.execute_task(_task(
            "schedule a meeting tomorrow at 3pm for 45 minutes", ctx=ctx,
        ))

        prefs = await store.get_scheduling_prefs("c1")
        assert prefs is not None
        assert 45 in prefs.get("durations", [])

    @pytest.mark.asyncio
    async def test_learned_duration_applied_when_unspecified(
        self, store, ctx
    ):
        """After three 30m meetings, an unspecified-duration request
        defaults to 30m rather than the hardcoded 60m."""
        for _ in range(3):
            await store.record_meeting_booked("c1", duration_min=30, hour=14)

        cal = StubCalendar()
        spec = SchedulingSpecialist(
            calendar=cal, clock=_clock, proactive_state=store,
        )
        result = await spec.execute_task(_task(
            "schedule a meeting tomorrow at 2pm", ctx=ctx,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        # Event should be 30m, not the 60m hardcoded default.
        evt = cal.created[-1]
        assert (evt.end - evt.start) == timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_no_prefs_uses_hardcoded_default(self, store, ctx):
        cal = StubCalendar()
        spec = SchedulingSpecialist(
            calendar=cal, clock=_clock, proactive_state=store,
        )
        await spec.execute_task(_task(
            "schedule a meeting tomorrow at 2pm", ctx=ctx,
        ))
        evt = cal.created[-1]
        assert (evt.end - evt.start) == timedelta(minutes=60)


# --- Preferred-time suggestions ---------------------------------------------

class TestPreferredTimes:
    @pytest.mark.asyncio
    async def test_preferred_hour_tracked(self, store):
        await store.record_meeting_booked("c1", duration_min=30, hour=14)
        await store.record_meeting_booked("c1", duration_min=30, hour=14)
        await store.record_meeting_booked("c1", duration_min=60, hour=10)

        prefs = await store.get_scheduling_prefs("c1")
        # 14:00 is the modal hour.
        assert prefs["preferred_hour"] == 14

    @pytest.mark.asyncio
    async def test_slot_find_uses_preferred_duration(self, store, ctx):
        """'Find me a slot this week' with no duration uses the learned
        preference, not the 30m default in _handle_slot_find."""
        for _ in range(3):
            await store.record_meeting_booked("c1", duration_min=45, hour=14)

        cal = StubCalendar()
        spec = SchedulingSpecialist(
            calendar=cal, clock=_clock, proactive_state=store,
        )
        result = await spec.execute_task(_task(
            "find me a slot this week", ctx=ctx,
        ))

        assert result.payload["duration_minutes"] == 45


# --- Conflict surfacing in response -----------------------------------------

class TestConflictSurfacing:
    @pytest.mark.asyncio
    async def test_conflict_mentioned_in_summary(self, store, ctx):
        """Booking over an existing event should surface the conflict
        in summary_for_ea, not silently stage it to proactive."""
        existing = CalendarEvent(
            id="evt_1", title="Design review",
            start=datetime(2026, 3, 20, 15, 0),
            end=datetime(2026, 3, 20, 15, 30),
        )
        cal = StubCalendar(events=[existing])
        spec = SchedulingSpecialist(
            calendar=cal, clock=_clock, proactive_state=store,
        )
        result = await spec.execute_task(_task(
            "schedule a meeting tomorrow at 3pm for 30 minutes", ctx=ctx,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        text = result.summary_for_ea.lower()
        # The conflicting event's title must be named — a generic
        # "there's a conflict" isn't actionable.
        assert "design review" in text
        assert "overlap" in text

    @pytest.mark.asyncio
    async def test_no_conflict_no_mention(self, store, ctx):
        cal = StubCalendar()
        spec = SchedulingSpecialist(
            calendar=cal, clock=_clock, proactive_state=store,
        )
        result = await spec.execute_task(_task(
            "schedule a meeting tomorrow at 3pm for 30 minutes", ctx=ctx,
        ))
        text = result.summary_for_ea.lower()
        assert "conflict" not in text
        assert "overlap" not in text


# --- Tenant isolation -------------------------------------------------------

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_prefs_isolated_per_customer(self, store):
        for _ in range(3):
            await store.record_meeting_booked("c1", duration_min=30, hour=9)
        for _ in range(3):
            await store.record_meeting_booked("c2", duration_min=60, hour=15)

        p1 = await store.get_scheduling_prefs("c1")
        p2 = await store.get_scheduling_prefs("c2")

        assert p1["preferred_duration"] == 30
        assert p2["preferred_duration"] == 60
        assert p1["preferred_hour"] == 9
        assert p2["preferred_hour"] == 15
