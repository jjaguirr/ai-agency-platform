"""
NEEDS_CONFIRMATION flow — high-risk specialist actions gate on explicit yes.

A specialist that's about to do something hard to reverse returns
NEEDS_CONFIRMATION instead of executing. The EA stashes what the
specialist needs to resume (pending_action) in active_delegation,
asks the customer, and on the next turn parses the reply:

  clear affirmative → re-invoke specialist with a confirmed marker
  anything else     → cancel, clear delegation, say so

The yes-set is deliberately closed. "yeah sure" and "what about next
week" both cancel — the cost of a false-negative (customer has to ask
again) is much lower than a false-positive (we deleted something the
customer didn't mean to delete).

Fixtures and patterns follow test_ea_delegation.py exactly.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base.specialist import (
    ActionRisk,
    DelegationRegistry,
    SpecialistAgent,
    SpecialistResult,
    SpecialistStatus,
    SpecialistTask,
    TaskAssessment,
)


# --- Enum + field additions -------------------------------------------------

class TestSpecialistStatusEnum:
    def test_has_needs_confirmation(self):
        assert SpecialistStatus.NEEDS_CONFIRMATION.value == "needs_confirmation"

    def test_existing_values_unchanged(self):
        # Don't break anything that already serializes these.
        assert SpecialistStatus.COMPLETED.value == "completed"
        assert SpecialistStatus.NEEDS_CLARIFICATION.value == "needs_clarification"
        assert SpecialistStatus.FAILED.value == "failed"


class TestActionRiskEnum:
    def test_has_three_levels(self):
        assert ActionRisk.LOW.value == "low"
        assert ActionRisk.MEDIUM.value == "medium"
        assert ActionRisk.HIGH.value == "high"


class TestSpecialistResultFields:
    def test_confirmation_prompt_defaults_none(self):
        r = SpecialistResult(
            status=SpecialistStatus.COMPLETED, domain="x",
            payload={}, confidence=0.5,
        )
        assert r.confirmation_prompt is None
        assert r.action_risk is None

    def test_to_dict_includes_new_fields(self):
        r = SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION, domain="scheduling",
            payload={"event_id": "evt_1"}, confidence=0.8,
            confirmation_prompt="About to cancel X. Confirm?",
            action_risk=ActionRisk.HIGH,
        )
        d = r.to_dict()
        assert d["status"] == "needs_confirmation"
        assert d["confirmation_prompt"] == "About to cancel X. Confirm?"
        assert d["action_risk"] == "high"

    def test_from_dict_roundtrip(self):
        d = {
            "status": "needs_confirmation",
            "domain": "scheduling",
            "payload": {"event_id": "e"},
            "confidence": 0.9,
            "confirmation_prompt": "Confirm?",
            "action_risk": "high",
        }
        r = SpecialistResult.from_dict(d)
        assert r.status == SpecialistStatus.NEEDS_CONFIRMATION
        assert r.confirmation_prompt == "Confirm?"
        assert r.action_risk == ActionRisk.HIGH

    def test_from_dict_missing_new_fields_defaults_none(self):
        # Old serialized results (pre-confirmation) must still load.
        d = {"status": "completed", "domain": "x", "payload": {},
             "confidence": 0.5}
        r = SpecialistResult.from_dict(d)
        assert r.confirmation_prompt is None
        assert r.action_risk is None


# --- Affirmative parsing ----------------------------------------------------

class TestIsAffirmative:
    @pytest.mark.parametrize("text", [
        "yes", "Yes", "YES", "yep", "yeah",
        "confirm", "confirmed", "go ahead", "do it",
        "proceed", "ok", "okay", "sure",
        "Yes.", "yes!", "ok.",
    ])
    def test_clear_yes(self, text):
        from src.agents.executive_assistant import _is_affirmative
        assert _is_affirmative(text) is True

    @pytest.mark.parametrize("text", [
        "no", "nope", "cancel", "stop", "don't",
        "what about next week", "actually hold on",
        "yes but can we change the time",  # conditional → not a clear yes
        "maybe", "I'm not sure",
        "", "   ",
    ])
    def test_anything_else_is_false(self, text):
        from src.agents.executive_assistant import _is_affirmative
        assert _is_affirmative(text) is False


# --- Lightweight EA fixture -------------------------------------------------

@pytest.fixture
def ea():
    with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
         patch("src.agents.executive_assistant.WorkflowCreator"), \
         patch("src.agents.executive_assistant.ChatOpenAI"):
        from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext

        mem = MockMem.return_value
        mem.get_business_context = AsyncMock(return_value=BusinessContext(
            business_name="Test Co",
        ))
        mem.search_business_knowledge = AsyncMock(return_value=[])
        mem.store_conversation_context = AsyncMock()
        mem.get_conversation_context = AsyncMock(return_value={})
        mem.store_business_context = AsyncMock()

        instance = ExecutiveAssistant(customer_id="cust_test")
        instance.llm = None
        yield instance


def _state(msg, active_delegation=None):
    from src.agents.executive_assistant import (
        ConversationState, BusinessContext, ConversationIntent,
    )
    from langchain_core.messages import HumanMessage
    return ConversationState(
        messages=[HumanMessage(content=msg)],
        customer_id="cust_test", conversation_id="conv_1",
        business_context=BusinessContext(business_name="Test Co"),
        current_intent=ConversationIntent.TASK_DELEGATION,
        active_delegation=active_delegation,
    )


def _confirmation_specialist(domain="scheduling", prompt="Confirm?",
                             payload=None, on_confirm=None):
    """Specialist that asks for confirmation on first call, executes on second.

    on_confirm is the result to return when prior_turns carries a
    confirmed marker — lets tests verify the specialist actually got
    re-invoked with the right context.
    """
    spec = MagicMock(spec=SpecialistAgent)
    spec.domain = domain
    spec.assess_task.return_value = TaskAssessment(confidence=0.9)

    async def _exec(task: SpecialistTask):
        confirmed = any(
            t.get("confirmed") for t in task.prior_turns
        )
        if confirmed:
            return on_confirm or SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain=domain,
                payload={"executed": True}, confidence=0.9,
                summary_for_ea="Done.", action_risk=ActionRisk.HIGH,
            )
        return SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION, domain=domain,
            payload=payload or {"event_id": "evt_1", "title": "Acme review"},
            confidence=0.9,
            confirmation_prompt=prompt,
            action_risk=ActionRisk.HIGH,
        )
    spec.execute_task = _exec
    return spec


# --- EA: NEEDS_CONFIRMATION → pending_action stashed ------------------------

class TestConfirmationRequested:
    @pytest.mark.asyncio
    async def test_sets_active_delegation_with_pending_action(self, ea):
        spec = _confirmation_specialist(
            prompt="I'm about to cancel 'Acme review'. Confirm?",
            payload={"event_id": "evt_1", "title": "Acme review"},
        )
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state("cancel the Acme meeting")
        state.delegation_target = "scheduling"

        out = await ea._delegate_to_specialist(state)

        assert out.active_delegation is not None
        assert out.active_delegation["domain"] == "scheduling"
        # The specialist's payload is stashed so turn 2 can execute
        # without re-resolving which event.
        assert out.active_delegation["pending_action"] == {
            "event_id": "evt_1", "title": "Acme review",
        }
        # Customer sees the confirmation prompt.
        assert "Acme review" in out.messages[-1].content
        assert "Confirm" in out.messages[-1].content

    @pytest.mark.asyncio
    async def test_confirmation_prompt_in_prior_turns(self, ea):
        spec = _confirmation_specialist(prompt="Confirm delete?")
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state("cancel it")
        state.delegation_target = "scheduling"

        out = await ea._delegate_to_specialist(state)

        # prior_turns records the prompt so turn 2's specialist sees
        # the full history — same as clarification.
        turns = out.active_delegation["prior_turns"]
        assert turns[-1]["role"] == "specialist"
        assert turns[-1]["content"] == "Confirm delete?"


# --- EA resume: affirmative → execute ---------------------------------------

class TestConfirmationAffirmed:
    @pytest.mark.asyncio
    async def test_yes_reinvokes_specialist_with_confirmed_marker(self, ea):
        received = []

        spec = MagicMock(spec=SpecialistAgent)
        spec.domain = "scheduling"
        spec.assess_task.return_value = TaskAssessment(confidence=0.9)

        async def _exec(task):
            received.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="scheduling",
                payload={"cancelled_id": "evt_1"}, confidence=0.9,
                summary_for_ea="Cancelled.", action_risk=ActionRisk.HIGH,
            )
        spec.execute_task = _exec

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state("yes", active_delegation={
            "domain": "scheduling",
            "original_task": "cancel the Acme meeting",
            "prior_turns": [
                {"role": "specialist", "content": "Confirm cancel?"},
            ],
            "pending_action": {"event_id": "evt_1", "title": "Acme review"},
        })

        out = await ea._delegate_to_specialist(state)

        # Specialist was re-invoked.
        assert len(received) == 1
        task = received[0]
        # prior_turns carries the customer's "yes" with confirmed=True
        # so the specialist knows to execute, not re-prompt.
        assert any(t.get("confirmed") for t in task.prior_turns)
        # The pending_action payload is available to the specialist
        # via prior_turns so it doesn't re-resolve the target event.
        assert any(
            t.get("pending_action") == {"event_id": "evt_1", "title": "Acme review"}
            for t in task.prior_turns
        )
        # Delegation cleared after execution.
        assert out.active_delegation is None

    @pytest.mark.asyncio
    async def test_yes_clears_delegation_after_execute(self, ea):
        spec = _confirmation_specialist()
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state("confirm", active_delegation={
            "domain": "scheduling", "original_task": "cancel x",
            "prior_turns": [{"role": "specialist", "content": "Sure?"}],
            "pending_action": {"event_id": "e"},
        })

        out = await ea._delegate_to_specialist(state)
        assert out.active_delegation is None


# --- EA resume: anything else → cancel --------------------------------------

class TestConfirmationDeclined:
    @pytest.mark.parametrize("reply", [
        "no", "nope", "cancel that", "actually wait",
        "what about next week instead",
    ])
    @pytest.mark.asyncio
    async def test_non_yes_cancels_without_invoking_specialist(self, ea, reply):
        spec = MagicMock(spec=SpecialistAgent)
        spec.domain = "scheduling"
        spec.assess_task.return_value = TaskAssessment(confidence=0.9)
        spec.execute_task = AsyncMock()  # must NOT be awaited

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state(reply, active_delegation={
            "domain": "scheduling", "original_task": "cancel x",
            "prior_turns": [{"role": "specialist", "content": "Sure?"}],
            "pending_action": {"event_id": "e"},
        })

        out = await ea._delegate_to_specialist(state)

        # Specialist was never invoked.
        spec.execute_task.assert_not_awaited()
        # Delegation cleared.
        assert out.active_delegation is None
        # Customer gets a cancellation acknowledgment.
        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        assert "cancel" in out.messages[-1].content.lower()

    @pytest.mark.asyncio
    async def test_clarification_resume_unaffected(self, ea):
        """A delegation WITHOUT pending_action is a clarification resume,
        not a confirmation resume — the existing path must still work."""
        received = []

        spec = MagicMock(spec=SpecialistAgent)
        spec.domain = "social_media"
        spec.assess_task.return_value = TaskAssessment(confidence=0.9)

        async def _exec(task):
            received.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="social_media",
                payload={}, confidence=0.8, summary_for_ea="ok",
            )
        spec.execute_task = _exec

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        # No pending_action key — this is a clarification answer, not
        # a confirmation reply. "Instagram" is not in the yes-set but
        # must NOT be treated as a decline.
        state = _state("Instagram please", active_delegation={
            "domain": "social_media",
            "original_task": "check engagement",
            "prior_turns": [
                {"role": "specialist", "content": "Which platform?"},
            ],
        })

        out = await ea._delegate_to_specialist(state)

        # Specialist was invoked with the clarification answer.
        assert len(received) == 1
        assert "Instagram" in received[0].prior_turns[-1]["content"]
        assert out.active_delegation is None


# --- Persistence round-trip -------------------------------------------------

class TestPendingActionPersistence:
    @pytest.mark.asyncio
    async def test_pending_action_stored_in_redis_context(self, ea):
        spec = _confirmation_specialist(
            payload={"event_id": "evt_1", "title": "X"},
        )
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="cancel the X meeting",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_persist",
        )

        ea.memory.store_conversation_context.assert_awaited()
        _, saved = ea.memory.store_conversation_context.await_args.args
        assert saved["active_delegation"]["pending_action"]["event_id"] == "evt_1"

    @pytest.mark.asyncio
    async def test_pending_action_restored_and_confirmed(self, ea):
        received = []

        spec = MagicMock(spec=SpecialistAgent)
        spec.domain = "scheduling"
        spec.assess_task.return_value = TaskAssessment(confidence=0.9)

        async def _exec(task):
            received.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="scheduling",
                payload={}, confidence=0.9, summary_for_ea="done",
            )
        spec.execute_task = _exec

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        ea.memory.get_conversation_context = AsyncMock(return_value={
            "active_delegation": {
                "domain": "scheduling",
                "original_task": "cancel X",
                "prior_turns": [{"role": "specialist", "content": "Sure?"}],
                "pending_action": {"event_id": "evt_1"},
            },
        })

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="yes",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_persist",
        )

        assert len(received) == 1
        # Confirmed marker present after round-trip.
        assert any(t.get("confirmed") for t in received[0].prior_turns)


# --- SchedulingSpecialist reference impl ------------------------------------

class TestSchedulingCancelConfirmation:
    """_handle_cancel is the reference HIGH-risk implementation.

    First call: resolve the target event, return NEEDS_CONFIRMATION
    with the event details in payload. NO delete.

    Second call (prior_turns carries confirmed=True): execute delete
    using the event_id from pending_action, NOT by re-resolving. The
    re-resolve might pick a different event if the calendar changed
    between turns.
    """

    @pytest.fixture
    def calendar(self):
        from tests.unit.test_scheduling_specialist import StubCalendar
        from src.agents.specialists.scheduling import CalendarEvent
        from datetime import datetime
        return StubCalendar(events=[
            CalendarEvent(
                id="evt_1", title="Acme review",
                start=datetime(2026, 3, 19, 15, 0),
                end=datetime(2026, 3, 19, 16, 0),
                attendees=("john@acme.com",),
            ),
        ])

    @pytest.fixture
    def spec(self, calendar):
        from src.agents.specialists.scheduling import SchedulingSpecialist
        from datetime import datetime
        return SchedulingSpecialist(
            calendar=calendar, clock=lambda: datetime(2026, 3, 19, 10, 0),
        )

    def _task(self, desc, prior_turns=None):
        from src.agents.executive_assistant import BusinessContext
        return SpecialistTask(
            description=desc,
            customer_id="c",
            business_context=BusinessContext(business_name="X"),
            domain_memories=[],
            prior_turns=prior_turns or [],
        )

    @pytest.mark.asyncio
    async def test_first_call_asks_confirmation_no_delete(self, spec, calendar):
        result = await spec.execute_task(
            self._task("cancel the Acme meeting")
        )
        assert result.status == SpecialistStatus.NEEDS_CONFIRMATION
        assert result.action_risk == ActionRisk.HIGH
        assert result.payload["event_id"] == "evt_1"
        assert "Acme review" in result.confirmation_prompt
        # NOT deleted yet.
        delete_calls = [c for c in calendar.calls if c[0] == "delete_event"]
        assert delete_calls == []

    @pytest.mark.asyncio
    async def test_confirmed_call_executes_delete(self, spec, calendar):
        result = await spec.execute_task(
            self._task("yes", prior_turns=[
                {"role": "specialist", "content": "Confirm cancel?"},
                {"role": "customer", "content": "yes", "confirmed": True,
                 "pending_action": {"event_id": "evt_1", "title": "Acme review"}},
            ])
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["cancelled_id"] == "evt_1"
        delete_calls = [c for c in calendar.calls if c[0] == "delete_event"]
        assert delete_calls == [("delete_event", ("evt_1",))]

    @pytest.mark.asyncio
    async def test_confirmed_uses_pending_action_not_reresolve(self, spec, calendar):
        """Between turn 1 and turn 2, another Acme meeting got created.
        The confirmed delete must hit the ORIGINAL event_id, not
        re-resolve and pick the wrong one."""
        from src.agents.specialists.scheduling import CalendarEvent
        from datetime import datetime
        calendar._events.append(CalendarEvent(
            id="evt_99", title="Acme planning",
            start=datetime(2026, 3, 20, 10, 0),
            end=datetime(2026, 3, 20, 11, 0),
            attendees=("jane@acme.com",),
        ))

        result = await spec.execute_task(
            self._task("yes", prior_turns=[
                {"role": "specialist", "content": "Confirm?"},
                {"role": "customer", "content": "yes", "confirmed": True,
                 "pending_action": {"event_id": "evt_1", "title": "Acme review"}},
            ])
        )
        assert result.payload["cancelled_id"] == "evt_1"
        # evt_99 untouched
        remaining = [e.id for e in calendar._events]
        assert "evt_99" in remaining
        assert "evt_1" not in remaining


# --- Audit integration ------------------------------------------------------

class TestConfirmationAudit:
    @pytest.mark.asyncio
    async def test_confirmation_requested_audits(self, ea):
        audit = AsyncMock()
        ea.audit_logger = audit

        spec = _confirmation_specialist()
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state("cancel X")
        state.delegation_target = "scheduling"

        await ea._delegate_to_specialist(state)

        audit.log.assert_awaited()
        call = audit.log.await_args
        # (customer_id, event)
        assert call.args[0] == "cust_test"
        event = call.args[1]
        from src.safety.models import AuditEventType
        assert event.event_type == AuditEventType.HIGH_RISK_ACTION_REQUESTED
        assert event.details["domain"] == "scheduling"

    @pytest.mark.asyncio
    async def test_confirmation_declined_audits(self, ea):
        audit = AsyncMock()
        ea.audit_logger = audit

        spec = MagicMock(spec=SpecialistAgent)
        spec.domain = "scheduling"
        spec.assess_task.return_value = TaskAssessment(confidence=0.9)
        spec.execute_task = AsyncMock()

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state("no", active_delegation={
            "domain": "scheduling", "original_task": "cancel X",
            "prior_turns": [{"role": "specialist", "content": "Sure?"}],
            "pending_action": {"event_id": "e"},
        })

        await ea._delegate_to_specialist(state)

        audit.log.assert_awaited()
        event = audit.log.await_args.args[1]
        from src.safety.models import AuditEventType
        assert event.event_type == AuditEventType.HIGH_RISK_ACTION_DECLINED

    @pytest.mark.asyncio
    async def test_no_audit_logger_works_fine(self, ea):
        # ea.audit_logger defaults to None — existing construction must
        # keep working without any audit wiring.
        assert ea.audit_logger is None

        spec = _confirmation_specialist()
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = _state("cancel X")
        state.delegation_target = "scheduling"

        # Must not raise.
        out = await ea._delegate_to_specialist(state)
        assert out.active_delegation is not None
