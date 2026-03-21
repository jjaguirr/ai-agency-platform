"""
EA delegation event tracking — durable specialist performance records.

The EA already persists mid-flight delegation state to Redis via
active_delegation. What's new: when a delegation reaches a terminal
state (COMPLETED, FAILED, or customer-declined confirmation), the EA
emits a DelegationRecord carrying turn count, timing, and confirmation
outcome. The conversations route drains these after each call and
writes them to Postgres.

The emit-then-drain shape means the EA stays Postgres-unaware — same
layering as message persistence. pop is destructive so a retry after a
Postgres hiccup doesn't double-write.

These tests call _delegate_to_specialist directly (same pattern as
test_ea_delegation.py) with infra mocked.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base.specialist import (
    DelegationRegistry,
    SpecialistAgent,
    SpecialistResult,
    SpecialistStatus,
    TaskAssessment,
)


# ─── fixtures (shared pattern with test_ea_delegation.py) ──────────────────

@pytest.fixture
def ea():
    with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
         patch("src.agents.executive_assistant.WorkflowCreator"), \
         patch("src.agents.executive_assistant.ChatOpenAI"):
        from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext

        mem = MockMem.return_value
        mem.get_business_context = AsyncMock(return_value=BusinessContext())
        mem.search_business_knowledge = AsyncMock(return_value=[])
        mem.store_conversation_context = AsyncMock()
        mem.get_conversation_context = AsyncMock(return_value={})

        inst = ExecutiveAssistant(customer_id="cust_track")
        inst.llm = None
        yield inst


@pytest.fixture
def state():
    from src.agents.executive_assistant import ConversationState, BusinessContext
    from langchain_core.messages import HumanMessage
    return ConversationState(
        messages=[HumanMessage(content="check my invoices")],
        customer_id="cust_track",
        conversation_id="conv_t",
        business_context=BusinessContext(),
    )


def _specialist(domain="finance", result=None):
    spec = MagicMock(spec=SpecialistAgent)
    spec.domain = domain
    spec.assess_task.return_value = TaskAssessment(confidence=0.9)

    async def _exec(task):
        return result or SpecialistResult(
            status=SpecialistStatus.COMPLETED, domain=domain,
            payload={"total": 100}, confidence=0.9,
            summary_for_ea="done",
        )
    spec.execute_task = _exec
    return spec


# ─── pop_delegation_events API ─────────────────────────────────────────────

class TestPopDelegationEvents:
    def test_fresh_ea_returns_empty(self, ea):
        assert ea.pop_delegation_events("any_conv") == []

    def test_pop_is_destructive(self, ea):
        # Reach in and stage an event — the unit under test is the pop
        # semantics, not the emit path (covered separately).
        from src.intelligence.repository import DelegationRecord
        now = datetime.now(timezone.utc)
        rec = DelegationRecord(
            conversation_id="conv_t", customer_id="cust_track",
            domain="finance", status="completed", turns=1,
            confirmation_requested=False, confirmation_outcome=None,
            started_at=now, ended_at=now,
        )
        ea._delegation_events.setdefault("conv_t", []).append(rec)

        first = ea.pop_delegation_events("conv_t")
        second = ea.pop_delegation_events("conv_t")
        assert len(first) == 1
        assert second == []

    def test_conversation_scoped(self, ea):
        from src.intelligence.repository import DelegationRecord
        now = datetime.now(timezone.utc)
        rec_a = DelegationRecord(
            conversation_id="conv_a", customer_id="c",
            domain="d", status="completed", turns=1,
            confirmation_requested=False, confirmation_outcome=None,
            started_at=now, ended_at=now,
        )
        ea._delegation_events.setdefault("conv_a", []).append(rec_a)
        assert ea.pop_delegation_events("conv_b") == []
        assert len(ea.pop_delegation_events("conv_a")) == 1


# ─── fresh single-turn delegation ──────────────────────────────────────────

class TestSingleTurnCompleted:
    @pytest.mark.asyncio
    async def test_completed_emits_one_event(self, ea, state):
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(_specialist())
        state.delegation_target = "finance"

        await ea._delegate_to_specialist(state)
        events = ea.pop_delegation_events("conv_t")

        assert len(events) == 1
        e = events[0]
        assert e.domain == "finance"
        assert e.status == "completed"
        assert e.turns == 1
        assert e.confirmation_requested is False
        assert e.confirmation_outcome is None
        assert e.conversation_id == "conv_t"
        assert e.customer_id == "cust_track"

    @pytest.mark.asyncio
    async def test_started_at_and_ended_at_populated(self, ea, state):
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(_specialist())
        state.delegation_target = "finance"

        before = datetime.now(timezone.utc)
        await ea._delegate_to_specialist(state)
        after = datetime.now(timezone.utc)

        e = ea.pop_delegation_events("conv_t")[0]
        assert before <= e.started_at <= after
        assert before <= e.ended_at <= after
        assert e.started_at <= e.ended_at


class TestSingleTurnFailed:
    @pytest.mark.asyncio
    async def test_failed_emits_event_with_failed_status(self, ea, state):
        spec = _specialist()

        async def _boom(task):
            raise RuntimeError("blew up")
        spec.execute_task = _boom

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "finance"

        await ea._delegate_to_specialist(state)
        events = ea.pop_delegation_events("conv_t")

        # Specialist failure is still tracked — that's the whole point
        # of the success_rate metric.
        assert len(events) == 1
        assert events[0].status == "failed"
        assert events[0].turns == 1

    @pytest.mark.asyncio
    async def test_missing_specialist_emits_nothing(self, ea, state):
        # Routing failed before any specialist ran — nothing to record.
        ea.delegation_registry = DelegationRegistry()
        state.delegation_target = "nonexistent"

        await ea._delegate_to_specialist(state)
        assert ea.pop_delegation_events("conv_t") == []


# ─── multi-turn: clarification then completed ──────────────────────────────

class TestMultiTurnClarification:
    @pytest.mark.asyncio
    async def test_clarification_turn_does_not_emit(self, ea, state):
        spec = _specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CLARIFICATION,
            domain="finance", payload={}, confidence=0.8,
            clarification_question="Which month?",
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "finance"

        await ea._delegate_to_specialist(state)

        # Mid-flight, not terminal. Nothing to persist yet.
        assert ea.pop_delegation_events("conv_t") == []
        # But turn count is tracked in active_delegation for the resume.
        assert state.active_delegation is not None
        assert state.active_delegation["turn_count"] == 1
        assert "started_at" in state.active_delegation

    @pytest.mark.asyncio
    async def test_resume_then_complete_emits_with_turn_count_2(self, ea, state):
        # Turn 2: active_delegation carries turn_count=1 from turn 1.
        from langchain_core.messages import HumanMessage
        started = datetime.now(timezone.utc) - timedelta(seconds=30)

        state.messages = [HumanMessage(content="march")]
        state.active_delegation = {
            "domain": "finance",
            "original_task": "check my invoices",
            "prior_turns": [{"role": "specialist", "content": "Which month?"}],
            "turn_count": 1,
            "started_at": started.isoformat(),
        }

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(_specialist())  # COMPLETED

        await ea._delegate_to_specialist(state)
        events = ea.pop_delegation_events("conv_t")

        assert len(events) == 1
        e = events[0]
        assert e.turns == 2
        # started_at is the ORIGINAL start, not this turn's start.
        assert e.started_at == started
        assert e.ended_at > started

    @pytest.mark.asyncio
    async def test_clarification_chain_increments_turn_count(self, ea, state):
        # Turn 2, still asking. turn_count should become 2, no emit.
        from langchain_core.messages import HumanMessage
        started = datetime.now(timezone.utc) - timedelta(seconds=30)

        state.messages = [HumanMessage(content="march I think")]
        state.active_delegation = {
            "domain": "finance",
            "original_task": "check my invoices",
            "prior_turns": [{"role": "specialist", "content": "Which month?"}],
            "turn_count": 1,
            "started_at": started.isoformat(),
        }

        spec = _specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CLARIFICATION,
            domain="finance", payload={}, confidence=0.8,
            clarification_question="This year or last?",
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        await ea._delegate_to_specialist(state)

        assert ea.pop_delegation_events("conv_t") == []
        assert state.active_delegation["turn_count"] == 2
        # started_at preserved across the chain
        assert state.active_delegation["started_at"] == started.isoformat()


# ─── confirmation flow ─────────────────────────────────────────────────────

class TestConfirmationFlow:
    @pytest.mark.asyncio
    async def test_needs_confirmation_does_not_emit(self, ea, state):
        spec = _specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="finance", payload={"invoice_id": "inv_1"},
            confidence=0.9,
            confirmation_prompt="Delete invoice inv_1?",
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "finance"

        await ea._delegate_to_specialist(state)

        assert ea.pop_delegation_events("conv_t") == []
        # Confirmation request marked in active_delegation.
        assert state.active_delegation is not None
        assert state.active_delegation.get("confirmation_requested") is True

    @pytest.mark.asyncio
    async def test_declined_confirmation_emits_cancelled(self, ea, state):
        from langchain_core.messages import HumanMessage
        started = datetime.now(timezone.utc) - timedelta(seconds=10)

        state.messages = [HumanMessage(content="no, don't do that")]
        state.active_delegation = {
            "domain": "finance",
            "original_task": "delete the invoice",
            "prior_turns": [{"role": "specialist", "content": "Delete inv_1?"}],
            "pending_action": {"invoice_id": "inv_1"},
            "turn_count": 1,
            "started_at": started.isoformat(),
            "confirmation_requested": True,
        }

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(_specialist())

        await ea._delegate_to_specialist(state)
        events = ea.pop_delegation_events("conv_t")

        assert len(events) == 1
        e = events[0]
        # Decline IS terminal — the delegation ended, just not the way
        # the customer originally asked. Tracked as cancelled.
        assert e.status == "cancelled"
        assert e.confirmation_requested is True
        assert e.confirmation_outcome == "declined"
        assert e.turns == 2  # request turn + decline turn

    @pytest.mark.asyncio
    async def test_confirmed_and_completed_records_confirmed(self, ea, state):
        from langchain_core.messages import HumanMessage
        started = datetime.now(timezone.utc) - timedelta(seconds=10)

        state.messages = [HumanMessage(content="yes")]
        state.active_delegation = {
            "domain": "finance",
            "original_task": "delete the invoice",
            "prior_turns": [{"role": "specialist", "content": "Delete inv_1?"}],
            "pending_action": {"invoice_id": "inv_1"},
            "turn_count": 1,
            "started_at": started.isoformat(),
            "confirmation_requested": True,
        }

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(_specialist())  # COMPLETED

        await ea._delegate_to_specialist(state)
        events = ea.pop_delegation_events("conv_t")

        assert len(events) == 1
        e = events[0]
        assert e.status == "completed"
        assert e.confirmation_requested is True
        assert e.confirmation_outcome == "confirmed"
        assert e.turns == 2


# ─── legacy active_delegation without tracking keys ────────────────────────

class TestBackcompat:
    @pytest.mark.asyncio
    async def test_resume_without_turn_count_defaults_sanely(self, ea, state):
        # Pre-existing Redis state from before this feature shipped.
        # No turn_count, no started_at. Should not crash; should emit
        # with turns=1 (best guess) and started_at=now-ish.
        from langchain_core.messages import HumanMessage

        state.messages = [HumanMessage(content="march")]
        state.active_delegation = {
            "domain": "finance",
            "original_task": "check my invoices",
            "prior_turns": [{"role": "specialist", "content": "Which month?"}],
            # no turn_count, no started_at
        }

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(_specialist())

        await ea._delegate_to_specialist(state)
        events = ea.pop_delegation_events("conv_t")

        assert len(events) == 1
        # Resume = at least 2 turns; without the counter we fall back to
        # that floor. Better an undercount than a crash.
        assert events[0].turns >= 1
        assert events[0].started_at is not None
