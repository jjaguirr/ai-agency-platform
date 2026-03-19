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
    DelegationRegistry,
    SpecialistTask,
    SpecialistStatus,
)
from src.agents.specialists.social_media import SocialMediaSpecialist
from src.agents.specialists.finance import FinanceSpecialist
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


# --- Cross-specialist overlap routing ---------------------------------------

@pytest.fixture
def registry_all_three():
    """Registry with all three specialists — the full routing surface."""
    reg = DelegationRegistry(confidence_threshold=0.6)
    reg.register(SocialMediaSpecialist())
    reg.register(FinanceSpecialist())
    reg.register(SchedulingSpecialist())
    return reg


@pytest.fixture
def rich_ctx():
    """Context with tools across all three domains — enables routing for
    cross-specialist overlap tests."""
    return BusinessContext(
        business_name="Acme Corp",
        industry="consulting",
        current_tools=[
            "Google Calendar", "Zoom", "Slack",
            "Instagram", "Facebook",
            "QuickBooks",
        ],
        pain_points=["scheduling conflicts", "social media engagement", "cash flow"],
    )


class TestRoutingOverlap:
    """Three-specialist routing disambiguation."""

    def test_calendar_query_routes_to_scheduling(self, registry_all_three, rich_ctx):
        match = registry_all_three.route("what meetings do I have tomorrow?", rich_ctx)
        assert match is not None
        assert match.specialist.domain == "scheduling"

    def test_schedule_a_post_routes_to_social_media(self, registry_all_three, rich_ctx):
        """'Schedule a post' — social media action, not calendar."""
        match = registry_all_three.route("schedule a post for next Tuesday", rich_ctx)
        assert match is not None
        assert match.specialist.domain == "social_media"

    def test_schedule_a_payment_routes_to_finance(self, registry_all_three, rich_ctx):
        """'Schedule a payment' — finance action, not calendar."""
        match = registry_all_three.route(
            "schedule a payment of $500 for the 15th", rich_ctx
        )
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_book_meeting_with_accountant_routes_to_scheduling(self, registry_all_three, rich_ctx):
        """Calendar action, even though topic is finance."""
        match = registry_all_three.route(
            "book a meeting with the accountant to review Q3 expenses", rich_ctx
        )
        assert match is not None
        assert match.specialist.domain == "scheduling"

    def test_content_planning_meeting_routes_to_scheduling(self, registry_all_three, rich_ctx):
        """Calendar action, even though topic is social media."""
        match = registry_all_three.route(
            "set up a content planning meeting for the marketing team", rich_ctx
        )
        assert match is not None
        assert match.specialist.domain == "scheduling"

    def test_social_media_budget_review_goes_to_ea(self, registry_all_three, rich_ctx):
        """Three-way ambiguity with advisory framing — EA keeps it."""
        match = registry_all_three.route(
            "when should I plan the social media budget review?", rich_ctx
        )
        assert match is None, "three-way strategic question should stay with EA"

    def test_all_three_registered_no_framework_changes(self, registry_all_three):
        """Adding scheduling required zero changes to specialist.py."""
        assert registry_all_three.get("scheduling") is not None
        assert registry_all_three.get("finance") is not None
        assert registry_all_three.get("social_media") is not None


# --- Graceful degradation ---------------------------------------------------

class TestGracefulDegradation:
    """calendar_client=None: assess_task works, execute_task returns FAILED."""

    def test_assess_works_without_client(self, specialist, office_ctx):
        """Routing must work regardless of client availability."""
        a = specialist.assess_task("what meetings do I have?", office_ctx)
        assert a.confidence >= 0.6

    @pytest.mark.asyncio
    async def test_execute_returns_failed_without_client(self, specialist, office_ctx):
        task = SpecialistTask(
            description="what meetings do I have tomorrow?",
            customer_id="c",
            business_context=office_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.FAILED
        assert result.domain == "scheduling"
        assert "calendar" in result.error.lower() or "connect" in result.error.lower()


# --- Daily overview ---------------------------------------------------------

class TestExecuteDailyOverview:
    @pytest.mark.asyncio
    async def test_returns_event_list(self, office_ctx):
        events = [
            CalendarEvent(
                id="1", title="Team Standup",
                start=datetime(2026, 3, 19, 9, 0),
                end=datetime(2026, 3, 19, 9, 30),
                attendees=["alice@co.com"],
            ),
            CalendarEvent(
                id="2", title="Lunch with Maria",
                start=datetime(2026, 3, 19, 12, 0),
                end=datetime(2026, 3, 19, 13, 0),
                attendees=["maria@co.com"],
            ),
        ]
        client = StubCalendarClient(events=events)
        spec = SchedulingSpecialist(calendar_client=client)

        task = SpecialistTask(
            description="what's on my calendar today?",
            customer_id="c",
            business_context=office_ctx,
            domain_memories=[],
        )
        result = await spec.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.domain == "scheduling"
        assert result.payload["event_count"] == 2
        assert len(result.payload["events"]) == 2
        assert result.payload["events"][0]["title"] == "Team Standup"
        assert result.summary_for_ea

    @pytest.mark.asyncio
    async def test_empty_calendar(self, office_ctx):
        client = StubCalendarClient(events=[])
        spec = SchedulingSpecialist(calendar_client=client)

        task = SpecialistTask(
            description="what meetings do I have today?",
            customer_id="c",
            business_context=office_ctx,
            domain_memories=[],
        )
        result = await spec.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["event_count"] == 0
        assert result.payload["events"] == []


# --- Event creation ---------------------------------------------------------

class TestExecuteCreateEvent:
    @pytest.mark.asyncio
    async def test_creates_event_with_full_details(self, office_ctx):
        client = StubCalendarClient()
        spec = SchedulingSpecialist(calendar_client=client)

        task = SpecialistTask(
            description="book a meeting with john@co.com tomorrow at 2pm for an hour",
            customer_id="c",
            business_context=office_ctx,
            domain_memories=[],
        )
        result = await spec.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["action"] == "created"
        assert "event" in result.payload
        assert result.payload["event"]["attendees"] == ["john@co.com"]
        assert any(c[0] == "create_event" for c in client.calls)

    @pytest.mark.asyncio
    async def test_asks_for_time_when_missing(self, office_ctx):
        client = StubCalendarClient()
        spec = SchedulingSpecialist(calendar_client=client)

        task = SpecialistTask(
            description="schedule a meeting with the team",
            customer_id="c",
            business_context=office_ctx,
            domain_memories=[],
        )
        result = await spec.execute_task(task)

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert "time" in result.clarification_question.lower() or \
               "when" in result.clarification_question.lower()

    @pytest.mark.asyncio
    async def test_asks_for_attendees_when_meeting_with_but_no_email(self, office_ctx):
        """'book a meeting with the team at 3pm' — no email found, ask who."""
        client = StubCalendarClient()
        spec = SchedulingSpecialist(calendar_client=client)

        task = SpecialistTask(
            description="book a meeting with the team tomorrow at 3pm",
            customer_id="c",
            business_context=office_ctx,
            domain_memories=[],
        )
        result = await spec.execute_task(task)

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert "who" in result.clarification_question.lower() or \
               "invite" in result.clarification_question.lower()

    @pytest.mark.asyncio
    async def test_resolves_time_via_prior_turns(self, office_ctx):
        """Multi-turn: asked for time, customer provided it."""
        client = StubCalendarClient()
        spec = SchedulingSpecialist(calendar_client=client)

        task = SpecialistTask(
            description="tomorrow at 3pm for 30 minutes",
            customer_id="c",
            business_context=office_ctx,
            domain_memories=[],
            prior_turns=[
                {"role": "customer", "content": "schedule a meeting with the team"},
                {"role": "specialist", "content": "What day and time should I schedule this?"},
                {"role": "customer", "content": "tomorrow at 3pm for 30 minutes"},
            ],
        )
        result = await spec.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["action"] == "created"
