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


# --- last_specialist_domain: surfaced for persistence layer -----------------
# The conversations route needs to know which specialist handled a turn
# so it can tag the stored assistant message. The EA can't return it
# (handle_customer_interaction → str is a frozen contract) so it's
# exposed as a post-call instance attribute, reset per interaction.

class TestLastSpecialistDomain:
    def test_defaults_to_none_at_construction(self, ea):
        """Fresh EA, never delegated → None. Mirrors audit_logger/
        settings_redis injection pattern."""
        assert ea.last_specialist_domain is None

    @pytest.mark.asyncio
    async def test_set_on_completed(self, ea, state):
        spec = _make_specialist(domain="social_media")
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        await ea._delegate_to_specialist(state)

        assert ea.last_specialist_domain == "social_media"

    @pytest.mark.asyncio
    async def test_set_on_needs_clarification(self, ea, state):
        """Mid-flight delegation still counts — the specialist engaged,
        the assistant message is the specialist's question. Dashboard
        should show this conversation touched that domain."""
        spec = _make_specialist(
            domain="scheduling",
            result=SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain="scheduling",
                payload={},
                confidence=0.7,
                summary_for_ea="",
                clarification_question="Which calendar?",
            ),
        )
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "scheduling"

        await ea._delegate_to_specialist(state)

        assert ea.last_specialist_domain == "scheduling"

    @pytest.mark.asyncio
    async def test_set_on_needs_confirmation(self, ea, state):
        spec = _make_specialist(
            domain="finance",
            result=SpecialistResult(
                status=SpecialistStatus.NEEDS_CONFIRMATION,
                domain="finance",
                payload={"action": "transfer", "amount": 5000},
                confidence=0.9,
                summary_for_ea="",
                confirmation_prompt="Transfer $5000?",
            ),
        )
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "finance"

        await ea._delegate_to_specialist(state)

        assert ea.last_specialist_domain == "finance"

    @pytest.mark.asyncio
    async def test_none_on_failed_fallback(self, ea, state):
        """FAILED → EA handles via general_assistance. The specialist
        didn't produce the response, so don't tag it."""
        spec = _make_specialist(
            domain="social_media",
            result=SpecialistResult(
                status=SpecialistStatus.FAILED,
                domain="social_media",
                payload={},
                confidence=0.0,
                summary_for_ea="",
                error="API timeout",
            ),
        )
        ea.delegation_registry = DelegationRegistry()
        ea.delegation_registry.register(spec)
        state.delegation_target = "social_media"

        await ea._delegate_to_specialist(state)

        assert ea.last_specialist_domain is None

    @pytest.mark.asyncio
    async def test_none_when_no_specialist_registered(self, ea, state):
        """Target domain not in registry → general_assistance fallback."""
        ea.delegation_registry = DelegationRegistry()  # empty
        state.delegation_target = "nonexistent"

        await ea._delegate_to_specialist(state)

        assert ea.last_specialist_domain is None

    @pytest.mark.asyncio
    async def test_reset_at_top_of_each_interaction(self, ea):
        """Stale domain from the previous turn must not leak. If this
        turn goes to general_assistance, the stored message should be
        tagged None, not whatever the last turn's specialist was.

        Safe under the one-EA-per-customer contract: WhatsApp/chat
        serialise turns, so there's no concurrent interaction racing
        the reset.
        """
        from src.agents.executive_assistant import ConversationChannel

        ea.last_specialist_domain = "finance"  # leftover from a prior turn
        ea.graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="general reply")],
        })

        await ea.handle_customer_interaction(
            message="hi", channel=ConversationChannel.CHAT, conversation_id="c1",
        )

        assert ea.last_specialist_domain is None


# --- Context assembler wiring -----------------------------------------------

class TestContextAssemblerWiring:
    def test_context_assembler_defaults_to_none(self, ea):
        """Same injection pattern as audit_logger — set by factory, not ctor."""
        assert ea._context_assembler is None

    @pytest.mark.asyncio
    async def test_delegation_passes_interaction_context_when_assembler_wired(self, ea, state):
        """When a ContextAssembler is wired, specialist receives non-None context."""
        from src.agents.context import ContextAssembler, InteractionContext, CustomerPreferences

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

        # Wire a mock assembler that returns a minimal InteractionContext
        assembler = AsyncMock(spec=ContextAssembler)
        assembler.assemble = AsyncMock(return_value=InteractionContext(
            customer_preferences=CustomerPreferences(tone="friendly"),
        ))
        ea._context_assembler = assembler

        await ea._delegate_to_specialist(state)

        assert len(received) == 1
        assert received[0].interaction_context is not None
        assert received[0].interaction_context.customer_preferences.tone == "friendly"

    @pytest.mark.asyncio
    async def test_delegation_works_without_context_assembler(self, ea, state):
        """No assembler wired → interaction_context is None, no crash."""
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
        ea._context_assembler = None

        await ea._delegate_to_specialist(state)

        assert len(received) == 1
        assert received[0].interaction_context is None

    @pytest.mark.asyncio
    async def test_context_assembly_failure_doesnt_block_delegation(self, ea, state):
        """Assembler raises → delegation proceeds with None context."""
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

        broken_assembler = AsyncMock()
        broken_assembler.assemble = AsyncMock(side_effect=RuntimeError("assembler boom"))
        ea._context_assembler = broken_assembler

        await ea._delegate_to_specialist(state)

        assert len(received) == 1
        assert received[0].interaction_context is None
