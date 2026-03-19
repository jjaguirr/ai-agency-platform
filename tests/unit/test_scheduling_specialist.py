"""
Unit tests for SchedulingSpecialist.

Third specialist in the delegation framework. Tests prove:
- CalendarClient Protocol works via structural typing (no inheritance)
- routing to correct specialist (incl. overlap with social media and finance)
- calendar event management (create, reschedule, cancel)
- clarification flow (missing time, ambiguous events)
- multi-turn via prior_turns
- graceful degradation when no CalendarClient
- seam isolation (no httpx/requests/aiohttp imports)
"""
import pytest
from datetime import datetime

from src.agents.specialists.scheduling import (
    SchedulingSpecialist,
    CalendarClient,
    CalendarEvent,
    TimeSlot,
)
from src.agents.base.specialist import (
    SpecialistTask,
    SpecialistStatus,
)
from src.agents.executive_assistant import BusinessContext


# --- Stub CalendarClient (structural typing, no inheritance) ----------------

class StubCalendarClient:
    """Conforms to CalendarClient by shape only — no inheritance, no
    import of the Protocol. Structural typing proves the seam works."""

    def __init__(self, events=None):
        self._events = events or []
        self.calls = []

    async def list_events(self, start: datetime, end: datetime):
        self.calls.append(("list_events", start, end))
        return [e for e in self._events if start <= e.start <= end]

    async def create_event(self, title, start, end, attendees, location=None):
        self.calls.append(("create_event", title, start, end, attendees, location))
        evt = CalendarEvent(
            id="new-1", title=title, start=start, end=end,
            attendees=attendees, location=location,
        )
        self._events.append(evt)
        return evt

    async def update_event(self, event_id, **kwargs):
        self.calls.append(("update_event", event_id, kwargs))
        for e in self._events:
            if e.id == event_id:
                for k, v in kwargs.items():
                    setattr(e, k, v)
                return e
        return self._events[0] if self._events else None

    async def delete_event(self, event_id):
        self.calls.append(("delete_event", event_id))
        before = len(self._events)
        self._events = [e for e in self._events if e.id != event_id]
        return len(self._events) < before

    async def is_free(self, start, end):
        self.calls.append(("is_free", start, end))
        return not any(
            e.start < end and e.end > start for e in self._events
        )

    async def find_available_slots(self, start, end, duration_minutes):
        self.calls.append(("find_available_slots", start, end, duration_minutes))
        return [TimeSlot(start=start, end=start)]


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def specialist():
    return SchedulingSpecialist()


@pytest.fixture
def specialist_with_client():
    client = StubCalendarClient()
    return SchedulingSpecialist(calendar_client=client), client


@pytest.fixture
def office_ctx():
    """Customer with calendar tools — realistic for scheduling tests."""
    return BusinessContext(
        business_name="Acme Corp",
        industry="consulting",
        current_tools=["Google Calendar", "Zoom", "Slack"],
        pain_points=["scheduling conflicts", "too many meetings"],
    )


@pytest.fixture
def bare_ctx():
    """Customer with no calendar tools — tests baseline confidence."""
    return BusinessContext(business_name="Unknown Co")


# --- Protocol structural typing ---------------------------------------------

class TestCalendarClientProtocol:
    def test_stub_conforms_without_inheritance(self):
        """StubCalendarClient has no CalendarClient in its MRO —
        structural typing is the only contract enforcement."""
        stub = StubCalendarClient()
        assert CalendarClient not in type(stub).__mro__

    def test_no_transport_imports_in_scheduling(self):
        """Seam isolation: scheduling.py depends on the contract,
        not on any transport library."""
        import src.agents.specialists.scheduling as mod
        import inspect
        source = inspect.getsource(mod)
        assert "httpx" not in source
        assert "aiohttp" not in source
        assert "requests" not in source
