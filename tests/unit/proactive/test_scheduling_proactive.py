"""Tests for scheduling conflict proactive trigger."""
import pytest
from datetime import datetime, timedelta, timezone

from src.agents.specialists.scheduling import SchedulingSpecialist, CalendarEvent
from src.proactive.triggers import Priority


_NOW = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)


class StubCalendar:
    """In-memory CalendarClient for testing."""

    def __init__(self, events=None):
        self._events = events or []

    async def list_events(self, start, end):
        return [e for e in self._events if e.start < end and e.end > start]

    async def create_event(self, title, start, end, attendees=None, location=None):
        return CalendarEvent(id="new_1", title=title, start=start, end=end)

    async def update_event(self, event_id, **kwargs):
        pass

    async def delete_event(self, event_id):
        pass

    async def is_free(self, start, end):
        return not any(e.start < end and e.end > start for e in self._events)

    async def find_slots(self, duration, window_start, window_end):
        return []


def _event(id, title, start_hour, end_hour, day_offset=0):
    base = _NOW.replace(hour=0, minute=0, second=0) + timedelta(days=day_offset)
    return CalendarEvent(
        id=id, title=title,
        start=base.replace(hour=start_hour),
        end=base.replace(hour=end_hour),
    )


class TestSchedulingConflictDetection:
    async def test_no_conflicts_returns_none(self):
        cal = StubCalendar(events=[
            _event("e1", "Standup", 9, 10),
            _event("e2", "Lunch", 12, 13),
        ])
        specialist = SchedulingSpecialist(calendar=cal, clock=lambda: _NOW)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check("cust_1", BusinessContext())
        assert result is None

    async def test_overlapping_events_triggers(self):
        cal = StubCalendar(events=[
            _event("e1", "Team standup", 10, 11),
            _event("e2", "Client call", 10, 11, day_offset=0),  # overlap
        ])
        specialist = SchedulingSpecialist(calendar=cal, clock=lambda: _NOW)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check("cust_1", BusinessContext())
        assert result is not None
        assert result.trigger_type == "scheduling_conflict"
        assert result.priority == Priority.HIGH
        assert result.domain == "scheduling"

    async def test_conflict_payload_includes_event_details(self):
        cal = StubCalendar(events=[
            _event("e1", "Meeting A", 14, 15),
            _event("e2", "Meeting B", 14, 16),
        ])
        specialist = SchedulingSpecialist(calendar=cal, clock=lambda: _NOW)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check("cust_1", BusinessContext())
        assert result is not None
        assert "events" in result.payload
        assert len(result.payload["events"]) == 2

    async def test_no_calendar_returns_none(self):
        specialist = SchedulingSpecialist(calendar=None, clock=lambda: _NOW)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check("cust_1", BusinessContext())
        assert result is None

    async def test_only_checks_next_24_hours(self):
        # Conflict is 2 days away — should not trigger
        cal = StubCalendar(events=[
            _event("e1", "Meeting A", 10, 11, day_offset=2),
            _event("e2", "Meeting B", 10, 11, day_offset=2),
        ])
        specialist = SchedulingSpecialist(calendar=cal, clock=lambda: _NOW)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check("cust_1", BusinessContext())
        assert result is None

    async def test_partial_overlap_triggers(self):
        cal = StubCalendar(events=[
            _event("e1", "Meeting A", 10, 12),
            _event("e2", "Meeting B", 11, 13),  # overlaps 11-12
        ])
        specialist = SchedulingSpecialist(calendar=cal, clock=lambda: _NOW)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check("cust_1", BusinessContext())
        assert result is not None

    async def test_cooldown_key_is_stable(self):
        """Same pair of events produces the same cooldown key."""
        cal = StubCalendar(events=[
            _event("e1", "A", 10, 11),
            _event("e2", "B", 10, 11),
        ])
        specialist = SchedulingSpecialist(calendar=cal, clock=lambda: _NOW)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check("cust_1", BusinessContext())
        assert result is not None
        assert result.cooldown_key is not None
        assert "e1" in result.cooldown_key or "e2" in result.cooldown_key
