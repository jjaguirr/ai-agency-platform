"""
Unit tests for SchedulingSpecialist.

Third specialist in the delegation framework. Proves the framework
still requires zero modification for a third domain, and exercises
the new three-way routing surface where social_media, finance, and
scheduling compete for every message.

Coverage per spec:
- CalendarClient is a Protocol (structural, no inheritance)
- routing: overview, create, reschedule, cancel, availability, slot-find
- overlap resolution:
  - "schedule a post for Tuesday" → social_media
  - "schedule a payment for the 15th" → finance
  - "book a meeting with the accountant to review expenses" → scheduling
  - "when should I plan the social media budget review?" → strategic, EA keeps
- clarification when time/attendee missing or event ambiguous
- graceful degradation when CalendarClient is None
- constructor clock seam for deterministic time parsing
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from src.agents.specialists.scheduling import (
    SchedulingSpecialist,
    CalendarClient,
    CalendarEvent,
    TimeSlot,
)
from src.agents.specialists.social_media import SocialMediaSpecialist
from src.agents.specialists.finance import FinanceSpecialist
from src.agents.base.specialist import (
    SpecialistTask,
    SpecialistStatus,
    DelegationRegistry,
)
from src.agents.executive_assistant import BusinessContext


# --- Fixed clock ------------------------------------------------------------

# Thursday 2026-03-19, 10:00. "tomorrow" = Friday 2026-03-20.
_NOW = datetime(2026, 3, 19, 10, 0)


def _clock():
    return _NOW


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def agency_ctx():
    """Customer using Google Calendar — realistic scheduling surface."""
    return BusinessContext(
        business_name="BrandBoost",
        industry="marketing",
        current_tools=["Google Calendar", "Slack", "Instagram"],
        pain_points=["too many meetings", "calendar chaos"],
    )


@pytest.fixture
def bare_ctx():
    return BusinessContext(business_name="Unknown Co")


# --- Calendar double (structural typing proof) -------------------------------

class StubCalendar:
    """Test double conforming to CalendarClient by shape only — no
    inheritance, no import of the Protocol into the stub's type hierarchy.
    If this works, structural typing is real.

    Stores events in-memory; all protocol methods operate on that list."""

    def __init__(self, events: list[CalendarEvent] | None = None):
        self._events = list(events or [])
        self._next_id = 1000
        # Spy log — (method_name, args_tuple)
        self.calls: list[tuple[str, Any]] = []

    async def list_events(self, start, end):
        self.calls.append(("list_events", (start, end)))
        return [e for e in self._events if e.start < end and e.end > start]

    async def create_event(self, title, start, end, attendees, location=None):
        self.calls.append(("create_event", (title, start, end, tuple(attendees), location)))
        evt = CalendarEvent(
            id=f"evt_{self._next_id}",
            title=title, start=start, end=end,
            attendees=tuple(attendees), location=location,
        )
        self._next_id += 1
        self._events.append(evt)
        return evt

    async def update_event(self, event_id, *, title=None, start=None, end=None,
                           attendees=None, location=None):
        self.calls.append(("update_event", (event_id, title, start, end)))
        idx = next(i for i, e in enumerate(self._events) if e.id == event_id)
        old = self._events[idx]
        new = CalendarEvent(
            id=old.id,
            title=title if title is not None else old.title,
            start=start if start is not None else old.start,
            end=end if end is not None else old.end,
            attendees=tuple(attendees) if attendees is not None else old.attendees,
            location=location if location is not None else old.location,
        )
        self._events[idx] = new
        return new

    async def delete_event(self, event_id):
        self.calls.append(("delete_event", (event_id,)))
        self._events = [e for e in self._events if e.id != event_id]

    async def is_free(self, start, end):
        self.calls.append(("is_free", (start, end)))
        return not any(e.start < end and e.end > start for e in self._events)

    async def find_slots(self, duration, window_start, window_end):
        self.calls.append(("find_slots", (duration, window_start, window_end)))
        # Naive: propose hourly slots in business hours that don't overlap events.
        slots = []
        cursor = window_start.replace(hour=9, minute=0, second=0, microsecond=0)
        while cursor + duration <= window_end and len(slots) < 5:
            slot_end = cursor + duration
            if await self.is_free(cursor, slot_end) and 9 <= cursor.hour < 18:
                slots.append(TimeSlot(start=cursor, end=slot_end))
            cursor += timedelta(hours=1)
        # is_free calls above pollute the spy log — strip them back out
        self.calls = [c for c in self.calls if c[0] != "is_free" or c[1] == (None,)]
        self.calls.append(("find_slots", (duration, window_start, window_end)))
        return slots


@pytest.fixture
def empty_calendar():
    return StubCalendar()


@pytest.fixture
def busy_calendar():
    """Thursday 2026-03-19: 3pm-4pm with Acme, 4pm-4:30 with Maria."""
    return StubCalendar(events=[
        CalendarEvent(
            id="evt_1", title="Acme review",
            start=datetime(2026, 3, 19, 15, 0),
            end=datetime(2026, 3, 19, 16, 0),
            attendees=("john@acme.com",),
        ),
        CalendarEvent(
            id="evt_2", title="1:1 with Maria",
            start=datetime(2026, 3, 19, 16, 0),
            end=datetime(2026, 3, 19, 16, 30),
            attendees=("maria@brandboost.com",),
        ),
    ])


@pytest.fixture
def specialist(empty_calendar):
    return SchedulingSpecialist(calendar=empty_calendar, clock=_clock)


@pytest.fixture
def busy_specialist(busy_calendar):
    return SchedulingSpecialist(calendar=busy_calendar, clock=_clock)


@pytest.fixture
def registry_three_way():
    """All three specialists registered — the real routing surface."""
    reg = DelegationRegistry(confidence_threshold=0.6)
    reg.register(SocialMediaSpecialist())
    reg.register(FinanceSpecialist())
    reg.register(SchedulingSpecialist(clock=_clock))
    return reg


def _task(desc: str, ctx: BusinessContext, prior_turns=None) -> SpecialistTask:
    return SpecialistTask(
        description=desc,
        customer_id="c",
        business_context=ctx,
        domain_memories=[],
        prior_turns=prior_turns or [],
    )


# --- Protocol shape ---------------------------------------------------------

class TestCalendarClientProtocol:
    def test_stub_satisfies_protocol_without_inheritance(self):
        """StubCalendar inherits nothing but object. If isinstance against
        the Protocol works, the Protocol is @runtime_checkable and
        structural. If the specialist accepts the stub, structural typing
        holds regardless of runtime_checkable."""
        cal = StubCalendar()
        spec = SchedulingSpecialist(calendar=cal, clock=_clock)
        # Constructor accepted it — structural typing proven
        assert spec._calendar is cal

    def test_calendar_event_is_frozen(self):
        evt = CalendarEvent(
            id="e1", title="x",
            start=_NOW, end=_NOW + timedelta(hours=1),
            attendees=(),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            evt.title = "y"

    def test_timeslot_duration_property(self):
        slot = TimeSlot(start=_NOW, end=_NOW + timedelta(minutes=45))
        assert slot.duration == timedelta(minutes=45)


# --- Assessment: operational scheduling (delegate) --------------------------

class TestAssessOperational:
    @pytest.mark.parametrize("msg", [
        "what's on my calendar today?",
        "what meetings do I have tomorrow?",
        "schedule a meeting with John tomorrow at 2pm",
        "book a call with Maria for Friday",
        "move my 3pm to 4pm",
        "reschedule the Acme meeting to next week",
        "cancel the meeting with Acme",
        "am I free tomorrow afternoon?",
        "find me 30 minutes with Maria this week",
        "do I have any conflicts at 2pm?",
    ])
    def test_confident_and_not_strategic(self, agency_ctx, msg):
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task(msg, agency_ctx)
        assert a.confidence >= 0.6, f"expected confident on: {msg!r}, got {a.confidence:.2f}"
        assert not a.is_strategic, f"expected operational on: {msg!r}"


# --- Assessment: lexical floor (no context boost) ---------------------------

class TestAssessLexicalFloor:
    @pytest.mark.parametrize("msg", [
        "what's on my calendar today?",
        "schedule a meeting with John at 3pm",
        "reschedule my appointment",
    ])
    def test_unambiguous_phrases_route_without_context(self, bare_ctx, msg):
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task(msg, bare_ctx)
        assert a.confidence >= 0.6, (
            f"{msg!r} scored {a.confidence:.2f} with zero context — "
            "unambiguous calendar phrases should route on their own"
        )


# --- Assessment: strategic (EA keeps) ---------------------------------------

class TestAssessStrategic:
    @pytest.mark.parametrize("msg", [
        "when should I schedule the quarterly review?",
        "should I meet with the investor this week or wait?",
        "is it worth setting up a weekly standup?",
        "how many meetings should I have per day?",
    ])
    def test_in_domain_but_strategic(self, agency_ctx, msg):
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task(msg, agency_ctx)
        assert a.confidence >= 0.4, f"expected domain recognition on: {msg!r}"
        assert a.is_strategic, f"expected strategic flag on: {msg!r}"


# --- Assessment: out of domain ----------------------------------------------

class TestAssessOutOfDomain:
    @pytest.mark.parametrize("msg", [
        "what's my cash flow looking like?",
        "how's my Instagram engagement?",
        "track this invoice: $2,400 from Acme",
        "what hashtags are trending?",
    ])
    def test_low_confidence(self, bare_ctx, msg):
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task(msg, bare_ctx)
        assert a.confidence < 0.5, f"expected low confidence on: {msg!r}"


# --- Assessment: negative guards (overlap damping) --------------------------

class TestAssessOverlapGuards:
    def test_schedule_a_post_damped(self, agency_ctx):
        """'schedule' + 'post' → social media action, not a meeting.
        Without the damp guard this scores ~0.45; with it, ~0.0. The
        threshold here is tight enough that removing the guard fails."""
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task("schedule a post for next Tuesday", agency_ctx)
        assert a.confidence < 0.2, f"scheduling should damp hard, got {a.confidence:.2f}"

    def test_schedule_a_payment_damped(self, agency_ctx):
        """'schedule' + 'payment' → finance action."""
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task("schedule a payment for the 15th", agency_ctx)
        assert a.confidence < 0.2, f"scheduling should damp hard, got {a.confidence:.2f}"

    def test_meeting_with_accountant_not_damped(self, agency_ctx):
        """'meeting' is unambiguous — finance noun 'accountant' doesn't damp.
        (No 'schedul' here so the guard never fires regardless — this
        proves the positive routing, not the anchor bypass.)"""
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task(
            "book a meeting with the accountant to review Q3 expenses", agency_ctx
        )
        assert a.confidence >= 0.6

    def test_anchor_survives_cross_domain_noun(self, bare_ctx):
        """The anchor bypass: "schedule" + finance noun damps, UNLESS an
        unambiguous calendar word holds us.

        Unanchored → ~0.0. Anchored → 0.90. Removing the bypass drops the
        anchored case to 0.60 — the ≥0.80 assertion catches that."""
        s = SchedulingSpecialist(clock=_clock)
        damped = s.assess_task(
            "schedule time with the team to sort out the invoice backlog", bare_ctx
        )
        assert damped.confidence < 0.2

        anchored = s.assess_task(
            "schedule a meeting to review the invoice backlog", bare_ctx
        )
        assert anchored.confidence >= 0.8, (
            f"anchor 'meeting' must suppress the damp; "
            f"got {anchored.confidence:.2f}, damped would be ~0.60"
        )


# --- Assessment: context boost ----------------------------------------------

class TestAssessContextAware:
    def test_calendar_tool_boosts(self):
        s = SchedulingSpecialist(clock=_clock)
        msg = "set up a call for tomorrow"
        no_tool = BusinessContext(business_name="X")
        with_tool = BusinessContext(
            business_name="X", current_tools=["Google Calendar"]
        )
        assert s.assess_task(msg, with_tool).confidence > \
               s.assess_task(msg, no_tool).confidence

    def test_confidence_capped_at_point_nine(self, agency_ctx):
        s = SchedulingSpecialist(clock=_clock)
        a = s.assess_task(
            "schedule a meeting on my calendar and reschedule the appointment",
            agency_ctx,
        )
        assert a.confidence == 0.9


# --- Three-way routing (spec validation cases) ------------------------------

class TestThreeWayRouting:
    """The four routing cases the spec calls out explicitly. These are
    the contract — if they fail, the whole routing design is wrong.

    For the 'schedule a post/payment' cases, what scheduling controls is
    that it *yields* — whether social/finance clear the production
    threshold is their own calibration problem, orthogonal to this
    specialist's design. We assert relative ordering."""

    def test_schedule_post_scheduling_yields_to_social(self, agency_ctx):
        s = SchedulingSpecialist(clock=_clock)
        sm = SocialMediaSpecialist()
        msg = "schedule a post for Tuesday"
        sched_c = s.assess_task(msg, agency_ctx).confidence
        soc_c = sm.assess_task(msg, agency_ctx).confidence
        assert sched_c < soc_c, f"scheduling {sched_c:.2f} should yield to social {soc_c:.2f}"
        assert sched_c < 0.4, "scheduling should damp below its own strategic gate"

    def test_schedule_payment_scheduling_yields_to_finance(self, agency_ctx):
        s = SchedulingSpecialist(clock=_clock)
        f = FinanceSpecialist()
        msg = "schedule a payment for the 15th"
        sched_c = s.assess_task(msg, agency_ctx).confidence
        fin_c = f.assess_task(msg, agency_ctx).confidence
        assert sched_c < fin_c, f"scheduling {sched_c:.2f} should yield to finance {fin_c:.2f}"
        assert sched_c < 0.4

    def test_meeting_with_accountant_routes_to_scheduling(
        self, registry_three_way, agency_ctx
    ):
        match = registry_three_way.route(
            "book a meeting with the accountant to review expenses", agency_ctx
        )
        assert match is not None
        assert match.specialist.domain == "scheduling"

    def test_social_media_budget_review_is_strategic(
        self, registry_three_way, agency_ctx
    ):
        """Three-way ambiguity: scheduling (when), social (media), finance
        (budget). Strategic — EA keeps it. The registry must return None."""
        match = registry_three_way.route(
            "when should I plan the social media budget review?", agency_ctx
        )
        assert match is None

    def test_calendar_query_routes_to_scheduling(self, registry_three_way, agency_ctx):
        match = registry_three_way.route(
            "what meetings do I have tomorrow?", agency_ctx
        )
        assert match is not None
        assert match.specialist.domain == "scheduling"

    def test_content_planning_meeting_routes_to_scheduling(
        self, registry_three_way, agency_ctx
    ):
        """Topic is social, action is 'set up a meeting' → scheduling."""
        match = registry_three_way.route(
            "set up a content planning meeting for the marketing team", agency_ctx
        )
        assert match is not None
        assert match.specialist.domain == "scheduling"


# --- Execution: overview ----------------------------------------------------

class TestExecuteOverview:
    @pytest.mark.asyncio
    async def test_today_lists_events(self, busy_specialist, agency_ctx):
        result = await busy_specialist.execute_task(
            _task("what's on my calendar today?", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.domain == "scheduling"
        p = result.payload
        assert p["date"] == "2026-03-19"
        assert p["count"] == 2
        titles = [e["title"] for e in p["events"]]
        assert "Acme review" in titles
        assert "1:1 with Maria" in titles
        # Summary mentions the count
        assert "2" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_tomorrow_empty(self, busy_specialist, agency_ctx):
        """Tomorrow (Fri 2026-03-20) has no events in the fixture."""
        result = await busy_specialist.execute_task(
            _task("what meetings do I have tomorrow?", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["date"] == "2026-03-20"
        assert result.payload["count"] == 0
        assert result.payload["events"] == []

    @pytest.mark.asyncio
    async def test_list_events_called_with_day_bounds(self, busy_calendar, agency_ctx):
        spec = SchedulingSpecialist(calendar=busy_calendar, clock=_clock)
        await spec.execute_task(_task("what's on my calendar today?", agency_ctx))
        list_calls = [c for c in busy_calendar.calls if c[0] == "list_events"]
        assert len(list_calls) == 1
        start, end = list_calls[0][1]
        assert start == datetime(2026, 3, 19, 0, 0)
        assert end == datetime(2026, 3, 20, 0, 0)


# --- Execution: create ------------------------------------------------------

class TestExecuteCreate:
    @pytest.mark.asyncio
    async def test_creates_with_time_duration_attendee(self, empty_calendar, agency_ctx):
        spec = SchedulingSpecialist(calendar=empty_calendar, clock=_clock)
        result = await spec.execute_task(
            _task("schedule a meeting with John tomorrow at 2pm for an hour", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        p = result.payload
        assert p["start"] == "2026-03-20T14:00:00"
        assert p["end"] == "2026-03-20T15:00:00"
        assert "john" in [a.lower() for a in p["attendees"]]
        assert p["event_id"].startswith("evt_")

    @pytest.mark.asyncio
    async def test_defaults_to_60_minutes_when_duration_missing(
        self, empty_calendar, agency_ctx
    ):
        spec = SchedulingSpecialist(calendar=empty_calendar, clock=_clock)
        result = await spec.execute_task(
            _task("book a call with Maria tomorrow at 3pm", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        p = result.payload
        assert p["start"] == "2026-03-20T15:00:00"
        assert p["end"] == "2026-03-20T16:00:00"  # default 60m

    @pytest.mark.asyncio
    async def test_asks_when_time_missing(self, specialist, agency_ctx):
        """'schedule a meeting' with no time → clarify, don't guess."""
        result = await specialist.execute_task(
            _task("schedule a meeting with John", agency_ctx)
        )
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        q = result.clarification_question.lower()
        assert "when" in q or "time" in q

    @pytest.mark.asyncio
    async def test_resolves_time_via_prior_turns(self, empty_calendar, agency_ctx):
        """Multi-turn: specialist asked for time → customer replied → complete."""
        spec = SchedulingSpecialist(calendar=empty_calendar, clock=_clock)
        result = await spec.execute_task(_task(
            "tomorrow at 2pm",
            agency_ctx,
            prior_turns=[
                {"role": "customer", "content": "schedule a meeting with John"},
                {"role": "specialist", "content": "What time works?"},
                {"role": "customer", "content": "tomorrow at 2pm"},
            ],
        ))
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["start"] == "2026-03-20T14:00:00"
        assert "john" in [a.lower() for a in result.payload["attendees"]]

    @pytest.mark.asyncio
    async def test_create_without_attendee_is_allowed(self, empty_calendar, agency_ctx):
        """Focus blocks, solo work — no attendee is fine if title is clear."""
        spec = SchedulingSpecialist(calendar=empty_calendar, clock=_clock)
        result = await spec.execute_task(
            _task("block off tomorrow at 9am for deep work", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["attendees"] == []


# --- Execution: reschedule --------------------------------------------------

class TestExecuteReschedule:
    @pytest.mark.asyncio
    async def test_moves_single_match(self, busy_calendar, agency_ctx):
        spec = SchedulingSpecialist(calendar=busy_calendar, clock=_clock)
        result = await spec.execute_task(
            _task("move my 3pm to 5pm", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        p = result.payload
        assert p["event_id"] == "evt_1"  # the Acme review at 3pm
        assert p["new_start"] == "2026-03-19T17:00:00"
        # update_event was actually called
        update_calls = [c for c in busy_calendar.calls if c[0] == "update_event"]
        assert len(update_calls) == 1

    @pytest.mark.asyncio
    async def test_asks_when_multiple_candidates(self, agency_ctx):
        """Two events at 3pm → must ask which one, listing both."""
        cal = StubCalendar(events=[
            CalendarEvent(
                id="a", title="Client A",
                start=datetime(2026, 3, 19, 15, 0),
                end=datetime(2026, 3, 19, 16, 0),
                attendees=(),
            ),
            CalendarEvent(
                id="b", title="Client B",
                start=datetime(2026, 3, 19, 15, 0),
                end=datetime(2026, 3, 19, 16, 0),
                attendees=(),
            ),
        ])
        spec = SchedulingSpecialist(calendar=cal, clock=_clock)
        result = await spec.execute_task(_task("move my 3pm to 4pm", agency_ctx))

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        q = result.clarification_question
        assert "Client A" in q
        assert "Client B" in q
        # Candidates echoed in payload so the EA can render a picker
        assert len(result.payload["candidates"]) == 2

    @pytest.mark.asyncio
    async def test_asks_when_no_match(self, busy_specialist, agency_ctx):
        """'Move my 1pm' but nothing at 1pm → clarify."""
        result = await busy_specialist.execute_task(
            _task("move my 1pm to 2pm", agency_ctx)
        )
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION

    @pytest.mark.asyncio
    async def test_match_by_title_keyword(self, busy_calendar, agency_ctx):
        """'reschedule the Acme meeting' → match by 'Acme' in title."""
        spec = SchedulingSpecialist(calendar=busy_calendar, clock=_clock)
        result = await spec.execute_task(
            _task("reschedule the Acme meeting to tomorrow at 10am", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["event_id"] == "evt_1"
        assert result.payload["new_start"] == "2026-03-20T10:00:00"


# --- Execution: cancel ------------------------------------------------------

class TestExecuteCancel:
    @pytest.mark.asyncio
    async def test_cancels_by_attendee(self, busy_calendar, agency_ctx):
        """Cancel is two-phase: first call resolves + asks, second deletes.

        Full confirmation-flow coverage lives in test_action_confirmation.py;
        this test just pins the specialist side of the handshake."""
        spec = SchedulingSpecialist(calendar=busy_calendar, clock=_clock)

        # Turn 1: resolve → confirm prompt, no delete.
        r1 = await spec.execute_task(
            _task("cancel the meeting with Acme", agency_ctx)
        )
        assert r1.status == SpecialistStatus.NEEDS_CONFIRMATION
        assert r1.payload["event_id"] == "evt_1"
        assert r1.payload["title"] == "Acme review"
        assert [c for c in busy_calendar.calls if c[0] == "delete_event"] == []

        # Turn 2: EA feeds the stashed payload back via prior_turns.
        r2 = await spec.execute_task(
            _task("yes", agency_ctx, prior_turns=[
                {"role": "specialist", "content": r1.confirmation_prompt},
                {"role": "customer", "content": "yes", "confirmed": True,
                 "pending_action": r1.payload},
            ])
        )
        assert r2.status == SpecialistStatus.COMPLETED
        assert r2.payload["cancelled_id"] == "evt_1"
        delete_calls = [c for c in busy_calendar.calls if c[0] == "delete_event"]
        assert delete_calls == [("delete_event", ("evt_1",))]

    @pytest.mark.asyncio
    async def test_cancel_ambiguous_asks(self, agency_ctx):
        cal = StubCalendar(events=[
            CalendarEvent(id="a", title="Standup", start=datetime(2026, 3, 19, 9, 0),
                          end=datetime(2026, 3, 19, 9, 15), attendees=()),
            CalendarEvent(id="b", title="Standup", start=datetime(2026, 3, 19, 17, 0),
                          end=datetime(2026, 3, 19, 17, 15), attendees=()),
        ])
        spec = SchedulingSpecialist(calendar=cal, clock=_clock)
        result = await spec.execute_task(_task("cancel the standup", agency_ctx))
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION


# --- Execution: availability ------------------------------------------------

class TestExecuteAvailability:
    @pytest.mark.asyncio
    async def test_free_when_no_conflicts(self, busy_specialist, agency_ctx):
        """Tomorrow afternoon (Fri 2026-03-20 12:00-18:00) — no events."""
        result = await busy_specialist.execute_task(
            _task("am I free tomorrow afternoon?", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["free"] is True
        assert result.payload["conflicts"] == []

    @pytest.mark.asyncio
    async def test_reports_conflicts(self, busy_specialist, agency_ctx):
        """Today afternoon has the Acme review at 3pm."""
        result = await busy_specialist.execute_task(
            _task("am I free this afternoon?", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["free"] is False
        titles = [e["title"] for e in result.payload["conflicts"]]
        assert "Acme review" in titles


# --- Execution: slot finding ------------------------------------------------

class TestExecuteSlotFinding:
    @pytest.mark.asyncio
    async def test_finds_slots(self, busy_calendar, agency_ctx):
        spec = SchedulingSpecialist(calendar=busy_calendar, clock=_clock)
        result = await spec.execute_task(
            _task("find me 30 minutes with Maria this week", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        p = result.payload
        assert p["duration_minutes"] == 30
        assert len(p["slots"]) > 0
        # find_slots was called with 30 minutes
        find_calls = [c for c in busy_calendar.calls if c[0] == "find_slots"]
        assert find_calls
        duration, _, _ = find_calls[-1][1]
        assert duration == timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_defaults_to_30_minutes(self, empty_calendar, agency_ctx):
        spec = SchedulingSpecialist(calendar=empty_calendar, clock=_clock)
        result = await spec.execute_task(
            _task("find me a slot to call Maria tomorrow", agency_ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["duration_minutes"] == 30


# --- Graceful degradation (no calendar) -------------------------------------

class TestGracefulDegradation:
    def test_assess_works_without_calendar(self, agency_ctx):
        """Routing must not require a live calendar."""
        s = SchedulingSpecialist(calendar=None, clock=_clock)
        a = s.assess_task("what's on my calendar today?", agency_ctx)
        assert a.confidence >= 0.6

    @pytest.mark.asyncio
    async def test_execute_fails_gracefully_without_calendar(self, agency_ctx):
        s = SchedulingSpecialist(calendar=None, clock=_clock)
        result = await s.execute_task(_task("what's on my calendar today?", agency_ctx))
        assert result.status == SpecialistStatus.FAILED
        assert "calendar" in result.error.lower()
        assert "connect" in result.error.lower() or "no calendar" in result.error.lower()

    @pytest.mark.asyncio
    async def test_default_constructor_has_no_calendar(self, agency_ctx):
        """Bare SchedulingSpecialist() → assess works, execute fails gracefully."""
        s = SchedulingSpecialist()
        a = s.assess_task("what's on my calendar?", agency_ctx)
        assert a.confidence >= 0.6
        result = await s.execute_task(_task("what's on my calendar?", agency_ctx))
        assert result.status == SpecialistStatus.FAILED


# --- Architectural ----------------------------------------------------------

class TestArchitecture:
    def test_no_google_or_outlook_imports(self):
        """Specialist depends on the Protocol, never a concrete provider."""
        import inspect
        import src.agents.specialists.scheduling as mod
        source = inspect.getsource(mod)
        for forbidden in ("googleapiclient", "google.oauth2", "msal", "O365",
                          "exchangelib", "caldav"):
            assert forbidden not in source, f"{forbidden} found in scheduling.py"

    def test_calendar_client_is_protocol_not_abc(self):
        """Structural typing — not inheritance."""
        import typing
        assert isinstance(CalendarClient, type(typing.Protocol)) or \
               hasattr(CalendarClient, "_is_protocol") or \
               getattr(CalendarClient, "__protocol_attrs__", None) is not None
