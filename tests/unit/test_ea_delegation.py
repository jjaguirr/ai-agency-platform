"""
Unit tests for EA delegation integration.

These test the delegation node and state-persistence logic in isolation —
the full LangGraph flow is covered by integration tests with real infra.
What matters here: the node contract, the fallback path, and multi-turn
state threading through Redis.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base.specialist import (
    DelegationRegistry,
    SpecialistAgent,
    SpecialistTask,
    SpecialistResult,
    SpecialistStatus,
    TaskAssessment,
)


# --- Fixtures: lightweight EA with infra mocked away ------------------------

@pytest.fixture
def ea():
    """An ExecutiveAssistant with all infra constructors patched out.

    The graph still compiles (so routing functions exist) but memory,
    workflow_creator, and llm are mocks. This lets us call node methods
    directly without Redis/Postgres/OpenAI.
    """
    with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
         patch("src.agents.executive_assistant.WorkflowCreator"), \
         patch("src.agents.executive_assistant.ChatOpenAI"):
        from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext

        mem = MockMem.return_value
        mem.get_business_context = AsyncMock(return_value=BusinessContext(
            business_name="Sparkle & Shine",
            industry="jewelry",
            current_tools=["Instagram", "Facebook"],
            pain_points=["manual social media"],
        ))
        mem.search_business_knowledge = AsyncMock(return_value=[
            {"content": "Posts product photos daily at 9am", "score": 0.9, "metadata": {"category": "social_media"}},
        ])
        mem.store_conversation_context = AsyncMock()
        mem.get_conversation_context = AsyncMock(return_value={})
        mem.store_business_context = AsyncMock()

        instance = ExecutiveAssistant(customer_id="test_cust")
        instance.llm = None  # force LLM-free synthesis paths
        yield instance


@pytest.fixture
def state():
    """Fresh conversation state with a customer message already loaded."""
    from src.agents.executive_assistant import ConversationState, BusinessContext, ConversationIntent
    from langchain_core.messages import HumanMessage

    return ConversationState(
        messages=[HumanMessage(content="how's my Instagram engagement this week?")],
        customer_id="test_cust",
        conversation_id="conv_1",
        business_context=BusinessContext(
            business_name="Sparkle & Shine",
            industry="jewelry",
            current_tools=["Instagram", "Facebook"],
            pain_points=["manual social media"],
        ),
        current_intent=ConversationIntent.TASK_DELEGATION,
        confidence_score=0.8,
    )


def _make_specialist(domain="social_media", confidence=0.8, strategic=False, result=None, delay=0.0):
    """Build a specialist double with configurable behavior."""
    spec = MagicMock(spec=SpecialistAgent)
    spec.domain = domain
    spec.assess_task.return_value = TaskAssessment(confidence=confidence, is_strategic=strategic)

    async def _exec(task):
        if delay:
            await asyncio.sleep(delay)
        return result or SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=domain,
            payload={"engagement_rate": 0.042, "platforms": ["Instagram"]},
            confidence=confidence,
            summary_for_ea="Instagram engagement at 4.2% — healthy for jewelry retail.",
        )
    spec.execute_task = _exec
    return spec


# --- ConversationState: new delegation fields -------------------------------

class TestConversationStateFields:
    def test_has_active_delegation_field_defaulting_none(self):
        from src.agents.executive_assistant import ConversationState, BusinessContext
        s = ConversationState(
            messages=[], customer_id="c", conversation_id="conv",
            business_context=BusinessContext(),
        )
        assert s.active_delegation is None

    def test_has_delegation_target_field_defaulting_none(self):
        from src.agents.executive_assistant import ConversationState, BusinessContext
        s = ConversationState(
            messages=[], customer_id="c", conversation_id="conv",
            business_context=BusinessContext(),
        )
        assert s.delegation_target is None


# --- EA init: registry wired ------------------------------------------------

class TestRegistryWiring:
    def test_ea_has_delegation_registry(self, ea):
        assert isinstance(ea.delegation_registry, DelegationRegistry)

    def test_social_media_specialist_registered_by_default(self, ea):
        assert ea.delegation_registry.get("social_media") is not None


# --- Delegation node: happy path --------------------------------------------

class TestDelegateNodeCompleted:
    @pytest.mark.asyncio
    async def test_specialist_result_woven_into_ea_response(self, ea, state):
        spec = _make_specialist()
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        out = await ea._delegate_to_specialist(state)

        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        response = out.messages[-1].content
        # EA voice, not a raw data dump — mentions the metric conversationally
        assert "4.2%" in response or "engagement" in response.lower()
        # Delegation completed → no pending state
        assert out.active_delegation is None

    @pytest.mark.asyncio
    async def test_specialist_receives_scoped_memory_not_full_state(self, ea, state):
        """The specialist gets domain_memories pre-fetched by EA, not
        the memory client and not state.messages."""
        received = []

        async def _capture(task):
            received.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="social_media",
                payload={}, confidence=0.8, summary_for_ea="ok",
            )

        spec = _make_specialist()
        spec.execute_task = _capture
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        await ea._delegate_to_specialist(state)

        assert len(received) == 1
        task = received[0]
        assert task.customer_id == "test_cust"
        assert len(task.domain_memories) == 1  # from the mocked search
        assert task.domain_memories[0]["content"] == "Posts product photos daily at 9am"
        # Memory search was called with a domain-scoped query
        ea.memory.search_business_knowledge.assert_awaited()
        query = ea.memory.search_business_knowledge.await_args.args[0]
        assert "social" in query.lower() or "instagram" in query.lower()


# --- Delegation node: failure → fallback ------------------------------------

class TestDelegateNodeFailed:
    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_general_assistance(self, ea, state):
        """Hung specialist → EA responds anyway, no delegation state left over."""
        slow = _make_specialist(delay=10.0)
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(slow)
        ea.specialist_timeout = 0.05
        state.delegation_target = "social_media"

        out = await ea._delegate_to_specialist(state)

        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        # Some response was generated (fallback path)
        assert len(out.messages[-1].content) > 0
        # Failed delegation leaves no pending state
        assert out.active_delegation is None

    @pytest.mark.asyncio
    async def test_exception_falls_back_to_general_assistance(self, ea, state):
        spec = _make_specialist()

        async def _boom(task):
            raise RuntimeError("API exploded")
        spec.execute_task = _boom

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        out = await ea._delegate_to_specialist(state)

        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        assert out.active_delegation is None
        # Customer never sees "API exploded"
        assert "API exploded" not in out.messages[-1].content

    @pytest.mark.asyncio
    async def test_missing_specialist_falls_back(self, ea, state):
        """delegation_target set but specialist not registered (misconfiguration)."""
        ea.delegation_registry = DelegationRegistry()  # empty
        state.delegation_target = "social_media"

        out = await ea._delegate_to_specialist(state)

        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        assert out.active_delegation is None


# --- Delegation node: clarification → multi-turn ----------------------------

class TestDelegateNodeClarification:
    @pytest.mark.asyncio
    async def test_clarification_sets_active_delegation(self, ea, state):
        spec = _make_specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CLARIFICATION,
            domain="social_media", payload={}, confidence=0.4,
            clarification_question="Which platforms should I check?",
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        out = await ea._delegate_to_specialist(state)

        assert out.active_delegation is not None
        assert out.active_delegation["domain"] == "social_media"
        assert "Which platforms" in out.active_delegation["prior_turns"][-1]["content"]
        # EA wraps the question in its own voice
        assert "Which platforms" in out.messages[-1].content

    @pytest.mark.asyncio
    async def test_follow_up_carries_prior_turns_to_specialist(self, ea):
        """Turn 2: customer answers the clarification. Specialist receives
        prior_turns and the new message, completes the task."""
        from src.agents.executive_assistant import ConversationState, BusinessContext, ConversationIntent
        from langchain_core.messages import HumanMessage

        received = []

        async def _capture(task):
            received.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="social_media",
                payload={"platforms": ["Instagram", "Facebook"]}, confidence=0.8,
                summary_for_ea="Both platforms checked.",
            )

        spec = _make_specialist()
        spec.execute_task = _capture
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = ConversationState(
            messages=[HumanMessage(content="Instagram and Facebook please")],
            customer_id="test_cust", conversation_id="conv_1",
            business_context=BusinessContext(business_name="X"),
            current_intent=ConversationIntent.TASK_DELEGATION,
            active_delegation={
                "domain": "social_media",
                "original_task": "check my engagement",
                "prior_turns": [
                    {"role": "specialist", "content": "Which platforms should I check?"},
                ],
            },
        )

        out = await ea._delegate_to_specialist(state)

        assert len(received) == 1
        task = received[0]
        # Specialist sees the clarification history + customer's reply
        assert len(task.prior_turns) == 2
        assert task.prior_turns[0]["content"] == "Which platforms should I check?"
        assert "Instagram and Facebook" in task.prior_turns[1]["content"]
        # Completed → delegation state cleared
        assert out.active_delegation is None


# --- Redis persistence: state continuity across turns -----------------------

class TestDelegationPersistence:
    @pytest.mark.asyncio
    async def test_active_delegation_saved_to_conversation_context(self, ea, state):
        """After a turn where specialist asked for clarification, the
        delegation state must land in Redis so the next turn can resume."""
        spec = _make_specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CLARIFICATION,
            domain="social_media", payload={}, confidence=0.4,
            clarification_question="Which platforms?",
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="check my engagement",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_persist",
        )

        # store_conversation_context was called with active_delegation payload
        ea.memory.store_conversation_context.assert_awaited()
        _, saved = ea.memory.store_conversation_context.await_args.args
        assert "active_delegation" in saved
        assert saved["active_delegation"] is not None
        assert saved["active_delegation"]["domain"] == "social_media"

    @pytest.mark.asyncio
    async def test_active_delegation_restored_from_conversation_context(self, ea):
        """Next turn: Redis returns the prior delegation state. EA routes
        straight back to the specialist without re-assessing."""
        received = []

        async def _capture(task):
            received.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="social_media",
                payload={}, confidence=0.8, summary_for_ea="done",
            )

        spec = _make_specialist()
        spec.execute_task = _capture
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        # Redis returns prior delegation state
        ea.memory.get_conversation_context = AsyncMock(return_value={
            "active_delegation": {
                "domain": "social_media",
                "original_task": "check engagement",
                "prior_turns": [
                    {"role": "specialist", "content": "Which platforms?"},
                ],
            },
        })

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="Instagram please",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_persist",
        )

        # Specialist was called with prior_turns restored
        assert len(received) == 1
        assert len(received[0].prior_turns) == 2
        assert "Instagram please" in received[0].prior_turns[-1]["content"]


# --- Routing: delegation gate in the intent router --------------------------

class TestRoutingGate:
    @pytest.mark.asyncio
    async def test_strategic_task_stays_with_ea(self, ea, state):
        """Real SocialMediaSpecialist flags strategic → general_assistance route."""
        from src.agents.specialists.social_media import SocialMediaSpecialist
        from langchain_core.messages import HumanMessage

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(SocialMediaSpecialist())

        state.messages = [HumanMessage(content="should I invest more in Instagram ads?")]
        # Routing should NOT set delegation_target
        match = ea.delegation_registry.route(state.messages[-1].content, state.business_context)
        assert match is None  # strategic → registry returns None

    @pytest.mark.asyncio
    async def test_operational_task_routes_to_specialist(self, ea, state):
        from src.agents.specialists.social_media import SocialMediaSpecialist
        from langchain_core.messages import HumanMessage

        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(SocialMediaSpecialist())

        state.messages = [HumanMessage(content="how's my Instagram doing?")]
        match = ea.delegation_registry.route(state.messages[-1].content, state.business_context)
        assert match is not None
        assert match.specialist.domain == "social_media"


# --- Delegation node: NEEDS_CONFIRMATION → confirmation flow ----------------

class TestDelegateNodeConfirmation:
    @pytest.mark.asyncio
    async def test_needs_confirmation_sets_pending_confirmation(self, ea, state):
        """Specialist returns NEEDS_CONFIRMATION with action_risk=HIGH →
        EA stores pending_confirmation in active_delegation and presents a
        confirmation prompt to the customer."""
        spec = _make_specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="social_media", payload={"amount": 500}, confidence=0.9,
            summary_for_ea="Transfer $500 to vendor account.",
            action_risk="high",
            pending_action={"type": "transfer", "amount": 500, "to": "vendor_123"},
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        out = await ea._delegate_to_specialist(state)

        # Delegation state preserved with pending_confirmation
        assert out.active_delegation is not None
        assert "pending_confirmation" in out.active_delegation
        pc = out.active_delegation["pending_confirmation"]
        assert pc["risk"] == "high"
        assert pc["action"]["type"] == "transfer"
        assert out.active_delegation["domain"] == "social_media"

        # EA asked the customer to confirm
        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        response = out.messages[-1].content.lower()
        assert "confirm" in response or "proceed" in response or "approve" in response

    @pytest.mark.asyncio
    async def test_customer_confirms_executes_action(self, ea):
        """Customer says 'yes' to a pending confirmation → specialist executes."""
        from src.agents.executive_assistant import ConversationState, BusinessContext, ConversationIntent
        from langchain_core.messages import HumanMessage

        executed = []

        async def _capture(task):
            executed.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="social_media",
                payload={"transfer_id": "tx_123"}, confidence=0.9,
                summary_for_ea="Transfer completed successfully.",
            )

        spec = _make_specialist()
        spec.execute_task = _capture
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = ConversationState(
            messages=[HumanMessage(content="Yes, go ahead")],
            customer_id="test_cust", conversation_id="conv_1",
            business_context=BusinessContext(business_name="X"),
            current_intent=ConversationIntent.TASK_DELEGATION,
            active_delegation={
                "domain": "social_media",
                "original_task": "transfer $500 to vendor",
                "pending_confirmation": {
                    "action": {"type": "transfer", "amount": 500},
                    "risk": "high",
                    "specialist_result": {
                        "status": "needs_confirmation",
                        "domain": "social_media",
                        "payload": {"amount": 500},
                        "confidence": 0.9,
                        "summary_for_ea": "Transfer $500.",
                        "action_risk": "high",
                        "pending_action": {"type": "transfer", "amount": 500},
                    },
                },
            },
        )

        out = await ea._delegate_to_specialist(state)

        # Specialist was re-invoked to execute
        assert len(executed) == 1
        # The task description should indicate this is a confirmed action
        assert "CONFIRMED" in executed[0].description
        # Pending confirmation cleared
        assert out.active_delegation is None
        # Customer gets a completion response with actual content
        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        response = out.messages[-1].content
        assert len(response) > 0
        # Should reflect the specialist's result, not a cancellation
        assert "cancel" not in response.lower()

    @pytest.mark.asyncio
    async def test_customer_declines_cancels_action(self, ea):
        """Customer says 'no' to a pending confirmation → action cancelled."""
        from src.agents.executive_assistant import ConversationState, BusinessContext, ConversationIntent
        from langchain_core.messages import HumanMessage, AIMessage

        executed = []

        async def _capture(task):
            executed.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="social_media",
                payload={}, confidence=0.9, summary_for_ea="Done.",
            )

        spec = _make_specialist()
        spec.execute_task = _capture
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = ConversationState(
            messages=[HumanMessage(content="No, cancel that")],
            customer_id="test_cust", conversation_id="conv_1",
            business_context=BusinessContext(business_name="X"),
            current_intent=ConversationIntent.TASK_DELEGATION,
            active_delegation={
                "domain": "social_media",
                "original_task": "transfer $500 to vendor",
                "pending_confirmation": {
                    "action": {"type": "transfer", "amount": 500},
                    "risk": "high",
                    "specialist_result": {
                        "status": "needs_confirmation",
                        "domain": "social_media",
                        "payload": {"amount": 500},
                        "confidence": 0.9,
                    },
                },
            },
        )

        out = await ea._delegate_to_specialist(state)

        # Specialist was NOT re-invoked
        assert len(executed) == 0
        # Pending confirmation cleared
        assert out.active_delegation is None
        # Customer gets a cancellation message
        assert isinstance(out.messages[-1], AIMessage)
        response = out.messages[-1].content
        assert len(response) > 0
        assert "cancel" in response.lower()

    @pytest.mark.asyncio
    async def test_confirmation_persisted_to_redis(self, ea, state):
        """NEEDS_CONFIRMATION delegation state must be saved to Redis so the
        next turn can handle confirm/decline."""
        spec = _make_specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="social_media", payload={"amount": 500}, confidence=0.9,
            summary_for_ea="Transfer $500.",
            action_risk="high",
            pending_action={"type": "transfer", "amount": 500},
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="transfer $500 to vendor",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_confirm",
        )

        ea.memory.store_conversation_context.assert_awaited()
        _, saved = ea.memory.store_conversation_context.await_args.args
        assert "active_delegation" in saved
        assert saved["active_delegation"] is not None
        assert "pending_confirmation" in saved["active_delegation"]

    @pytest.mark.asyncio
    async def test_medium_risk_not_confirmed(self, ea, state):
        """NEEDS_CONFIRMATION with action_risk=medium → treat as COMPLETED
        (only HIGH requires confirmation)."""
        spec = _make_specialist(result=SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="social_media", payload={"post_id": "p_1"}, confidence=0.8,
            summary_for_ea="Post scheduled.",
            action_risk="medium",
            pending_action={"type": "schedule_post"},
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        out = await ea._delegate_to_specialist(state)

        # Medium risk: auto-approved, no pending confirmation
        assert out.active_delegation is None
        from langchain_core.messages import AIMessage
        assert isinstance(out.messages[-1], AIMessage)
        response = out.messages[-1].content
        assert len(response) > 0
        # Should be a completion response, not a confirmation prompt
        assert "confirm" not in response.lower()
        assert "cancel" not in response.lower()

    @pytest.mark.asyncio
    async def test_ambiguous_message_defaults_to_decline(self, ea):
        """Ambiguous message (neither clearly yes nor no) → safe default: decline."""
        from src.agents.executive_assistant import ConversationState, BusinessContext, ConversationIntent
        from langchain_core.messages import HumanMessage, AIMessage

        executed = []

        async def _capture(task):
            executed.append(task)
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED, domain="social_media",
                payload={}, confidence=0.9, summary_for_ea="Done.",
            )

        spec = _make_specialist()
        spec.execute_task = _capture
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = ConversationState(
            messages=[HumanMessage(content="Hmm, I'm not sure about that")],
            customer_id="test_cust", conversation_id="conv_1",
            business_context=BusinessContext(business_name="X"),
            current_intent=ConversationIntent.TASK_DELEGATION,
            active_delegation={
                "domain": "social_media",
                "original_task": "transfer $500",
                "pending_confirmation": {
                    "action": {"type": "transfer", "amount": 500},
                    "risk": "high",
                    "specialist_result": {
                        "status": "needs_confirmation",
                        "domain": "social_media",
                        "payload": {"amount": 500},
                        "confidence": 0.9,
                    },
                },
            },
        )

        out = await ea._delegate_to_specialist(state)

        # Ambiguous → decline (safe default). Specialist NOT invoked.
        assert len(executed) == 0
        assert out.active_delegation is None
        assert isinstance(out.messages[-1], AIMessage)
        assert "cancel" in out.messages[-1].content.lower()

    @pytest.mark.asyncio
    async def test_confirm_but_specialist_fails_falls_back(self, ea):
        """Customer confirms but specialist fails on execution → fallback."""
        from src.agents.executive_assistant import ConversationState, BusinessContext, ConversationIntent
        from langchain_core.messages import HumanMessage, AIMessage

        spec = _make_specialist(result=SpecialistResult(
            status=SpecialistStatus.FAILED, domain="social_media",
            payload={}, confidence=0.0, error="Service unavailable",
        ))
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)

        state = ConversationState(
            messages=[HumanMessage(content="Yes, proceed")],
            customer_id="test_cust", conversation_id="conv_1",
            business_context=BusinessContext(business_name="X"),
            current_intent=ConversationIntent.TASK_DELEGATION,
            active_delegation={
                "domain": "social_media",
                "original_task": "transfer $500",
                "pending_confirmation": {
                    "action": {"type": "transfer", "amount": 500},
                    "risk": "high",
                    "specialist_result": {
                        "status": "needs_confirmation",
                        "domain": "social_media",
                        "payload": {"amount": 500},
                        "confidence": 0.9,
                    },
                },
            },
        )

        out = await ea._delegate_to_specialist(state)

        # Failed after confirmation → fallback, delegation cleared
        assert out.active_delegation is None
        assert isinstance(out.messages[-1], AIMessage)
        # Customer should still get *some* response (fallback)
        assert len(out.messages[-1].content) > 0
