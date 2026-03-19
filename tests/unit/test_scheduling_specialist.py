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


# --- Assessment: operational scheduling tasks (delegate) --------------------

class TestAssessOperational:
    """Concrete calendar tasks -> delegate."""

    @pytest.mark.parametrize("msg", [
        "what meetings do I have tomorrow?",
        "what's on my calendar today?",
        "book a meeting with John at 2pm tomorrow",
        "cancel the meeting with Acme",
        "reschedule my 3pm to 4pm",
        "what's my schedule for Monday?",
    ])
    def test_confident_and_not_strategic(self, specialist, office_ctx, msg):
        a = specialist.assess_task(msg, office_ctx)
        assert a.confidence >= 0.6, f"expected confident on: {msg!r}, got {a.confidence:.2f}"
        assert not a.is_strategic, f"expected operational on: {msg!r}"


# --- Assessment: lexical floor (no context boost) ---------------------------

class TestAssessLexicalFloor:
    """Routing must work for a customer with no calendar tools."""

    @pytest.mark.parametrize("msg", [
        "what's on my calendar today?",
        "my meetings tomorrow",
        "book a meeting with Maria",
        "cancel the meeting with Acme",
        "reschedule my appointment",
    ])
    def test_unambiguous_phrases_route_without_context(self, specialist, bare_ctx, msg):
        a = specialist.assess_task(msg, bare_ctx)
        assert a.confidence >= 0.6, (
            f"{msg!r} scored {a.confidence:.2f} with zero context — "
            "unambiguous scheduling phrases should route on their own"
        )
        assert not a.is_strategic


# --- Assessment: strategic scheduling tasks (EA keeps) ----------------------

class TestAssessStrategic:
    """In-domain but advisory — EA keeps it."""

    @pytest.mark.parametrize("msg", [
        "should I block off more focus time?",
        "is it worth having a daily standup?",
        "how many meetings should I have per week?",
    ])
    def test_in_domain_but_strategic(self, specialist, office_ctx, msg):
        a = specialist.assess_task(msg, office_ctx)
        assert a.confidence >= 0.4, f"expected domain recognition on: {msg!r}"
        assert a.is_strategic, f"expected strategic flag on: {msg!r}"


# --- Assessment: out of domain ----------------------------------------------

class TestAssessOutOfDomain:
    @pytest.mark.parametrize("msg", [
        "how's my Instagram engagement this week?",
        "track $500 spent on Facebook ads",
        "what's my cash flow looking like?",
        "can you draft a contract?",
        "schedule a post for next Tuesday",
        "schedule a payment of $500 for the 15th",
    ])
    def test_low_confidence(self, specialist, office_ctx, msg):
        a = specialist.assess_task(msg, office_ctx)
        assert a.confidence < 0.5, f"expected low confidence on: {msg!r}, got {a.confidence:.2f}"


# --- Assessment: context-aware ----------------------------------------------

class TestAssessContextAware:
    def test_calendar_tools_boost_confidence(self, specialist):
        msg = "am I free tomorrow afternoon?"
        no_tools = BusinessContext(business_name="X")
        with_tools = BusinessContext(
            business_name="X",
            current_tools=["Google Calendar"],
        )
        assert specialist.assess_task(msg, with_tools).confidence > \
               specialist.assess_task(msg, no_tools).confidence

    def test_scheduling_pain_points_boost_confidence(self, specialist):
        msg = "am I free tomorrow afternoon?"
        no_pain = BusinessContext(business_name="X")
        with_pain = BusinessContext(
            business_name="X",
            pain_points=["scheduling conflicts"],
        )
        assert specialist.assess_task(msg, with_pain).confidence > \
               specialist.assess_task(msg, no_pain).confidence

    def test_confidence_capped_at_point_nine(self, specialist, office_ctx):
        a = specialist.assess_task(
            "reschedule my calendar meeting appointment for my schedule",
            office_ctx,
        )
        assert a.confidence == 0.9
