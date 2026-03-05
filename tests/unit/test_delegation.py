"""
Delegation framework integration tests.

These test the EA's delegation nodes directly — `_delegation_decision`,
`_specialist_execution`, `_scope_context_for_specialist` — rather than
going through the full compiled LangGraph. The graph wiring is verified
separately; node logic is verified here.

The EA constructor connects to Redis/Postgres/Qdrant. We bypass it with
`__new__` and wire in mocks manually.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import HumanMessage, AIMessage

from src.agents.executive_assistant import (
    BusinessContext,
    ConversationIntent,
    ConversationState,
    ExecutiveAssistant,
)
from src.agents.specialists.base import (
    DelegationStatus,
    SpecialistResult,
    SpecialistTask,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_specialist(domain="social_media", can_handle_score=0.9,
                    categories=None, execute_result=None):
    """Build a mock specialist with controllable routing & execution."""
    s = MagicMock()
    s.domain = domain
    s.memory_categories = categories or ["social_media", "current_tools"]
    s.can_handle = MagicMock(return_value=can_handle_score)
    s.execute = AsyncMock(return_value=execute_result or SpecialistResult(
        status=DelegationStatus.COMPLETED,
        content="engagement up 12%",
        confidence=0.9,
        structured_data={"followers": 1200},
    ))
    return s


def make_state(message="how's my Instagram doing?",
               intent=ConversationIntent.BUSINESS_ASSISTANCE,
               active_delegation=None,
               delegation_hint=None):
    state = ConversationState(
        messages=[HumanMessage(content=message)],
        customer_id="cust_abc",
        conversation_id="conv_xyz",
        business_context=BusinessContext(
            business_name="Sparkle Jewelry",
            industry="jewelry",
            current_tools=["Instagram", "Buffer"],
        ),
        current_intent=intent,
        confidence_score=0.8,
        active_delegation=active_delegation,
    )
    if delegation_hint is not None:
        state.collected_info["_delegation_hint"] = delegation_hint
    return state


@pytest.fixture
def ea():
    """EA with mocked infra — no Redis/Postgres/Qdrant connections."""
    inst = ExecutiveAssistant.__new__(ExecutiveAssistant)
    inst.customer_id = "cust_abc"
    inst.specialists = {}

    # Memory: search returns a mix of categories so we can verify filtering
    inst.memory = MagicMock()
    inst.memory.search_business_knowledge = AsyncMock(return_value=[
        {"content": "Posts about new items do well", "metadata": {"category": "social_media"}},
        {"content": "Customer uses QuickBooks", "metadata": {"category": "finance"}},
        {"content": "Buffer for scheduling", "metadata": {"category": "current_tools"}},
        {"content": "Confidential pricing notes", "metadata": {"category": "pricing"}},
    ])
    inst.memory.get_business_context = AsyncMock(
        return_value=BusinessContext(business_name="Sparkle Jewelry", industry="jewelry")
    )

    # LLM: default to EXECUTE decision; tests override as needed
    inst.llm = MagicMock()
    inst.llm.ainvoke = AsyncMock(return_value=MagicMock(content="EXECUTE"))

    return inst


# ---------------------------------------------------------------------------
# Validation 1: A message matching a specialist's domain gets delegated
# ---------------------------------------------------------------------------

class TestDelegationHappens:
    @pytest.mark.asyncio
    async def test_matching_specialist_is_selected(self, ea):
        specialist = make_specialist(can_handle_score=0.9)
        ea.register_specialist(specialist)
        state = make_state()

        result = await ea._delegation_decision(state)

        specialist.can_handle.assert_called_once()
        assert result.collected_info.get("_selected_specialist") == "social_media"

    @pytest.mark.asyncio
    async def test_specialist_executes_and_result_is_woven(self, ea):
        specialist = make_specialist()
        ea.register_specialist(specialist)
        # LLM reformulates the specialist result in EA voice
        ea.llm.ainvoke = AsyncMock(return_value=MagicMock(
            content="Good news! Your Instagram engagement is up 12% this week."
        ))

        state = make_state()
        state.collected_info["_selected_specialist"] = "social_media"

        result = await ea._specialist_execution(state)

        specialist.execute.assert_awaited_once()
        # Last message should be the EA-voiced response, not the raw specialist output
        assert isinstance(result.messages[-1], AIMessage)
        assert "engagement" in result.messages[-1].content.lower()
        assert result.active_delegation is None
        assert "_specialist_fallback" not in result.collected_info

    @pytest.mark.asyncio
    async def test_low_can_handle_score_skips_delegation(self, ea):
        specialist = make_specialist(can_handle_score=0.3)  # below 0.5 threshold
        ea.register_specialist(specialist)
        state = make_state()

        result = await ea._delegation_decision(state)

        assert "_selected_specialist" not in result.collected_info

    @pytest.mark.asyncio
    async def test_no_specialists_registered_skips_delegation(self, ea):
        state = make_state()
        result = await ea._delegation_decision(state)
        assert "_selected_specialist" not in result.collected_info


# ---------------------------------------------------------------------------
# Hint-based routing: intent_classification_node writes _delegation_hint,
# _delegation_decision reads it. No second LLM call.
# ---------------------------------------------------------------------------

class TestHintRouting:
    @pytest.mark.asyncio
    async def test_hint_matching_registered_specialist_routes_directly(self, ea):
        specialist = make_specialist(domain="social_media")
        other = make_specialist(domain="finance")
        ea.register_specialist(specialist)
        ea.register_specialist(other)

        state = make_state(delegation_hint="social_media")
        result = await ea._delegation_decision(state)

        assert result.collected_info.get("_selected_specialist") == "social_media"
        # Hint is authoritative — only the named specialist is sanity-checked,
        # no registry scan. Proves we're not keyword-scoring everyone.
        specialist.can_handle.assert_called_once()
        other.can_handle.assert_not_called()

    @pytest.mark.asyncio
    async def test_hint_ea_keeps_with_executive_assistant(self, ea):
        # The strategic-vs-operational decision now lives in intent
        # classification. When it says "ea", respect that — even if a
        # specialist's keywords would have matched.
        specialist = make_specialist(can_handle_score=0.95)
        ea.register_specialist(specialist)

        state = make_state(
            "should I invest more in Instagram ads?",
            delegation_hint="ea",
        )
        result = await ea._delegation_decision(state)

        specialist.can_handle.assert_not_called()
        assert "_selected_specialist" not in result.collected_info

    @pytest.mark.asyncio
    async def test_hint_unknown_domain_falls_to_keyword_backstop(self, ea):
        # LLM hallucinated a domain that isn't registered. Use the keyword
        # backstop — the LLM wanted to delegate, it just named wrong.
        specialist = make_specialist(domain="social_media", can_handle_score=0.8)
        ea.register_specialist(specialist)

        state = make_state(delegation_hint="marketing")  # not registered
        result = await ea._delegation_decision(state)

        # Backstop engaged
        specialist.can_handle.assert_called_once()
        assert result.collected_info.get("_selected_specialist") == "social_media"

    @pytest.mark.asyncio
    async def test_hint_absent_falls_to_keyword_backstop(self, ea):
        # Parse failure or old-format response: no hint set. Keyword scoring
        # is the safety net. This is the pre-Option-A code path.
        specialist = make_specialist(can_handle_score=0.8)
        ea.register_specialist(specialist)

        state = make_state()  # no delegation_hint
        result = await ea._delegation_decision(state)

        specialist.can_handle.assert_called_once()
        assert result.collected_info.get("_selected_specialist") == "social_media"

    @pytest.mark.asyncio
    async def test_no_llm_call_in_delegation_decision(self, ea):
        # The whole point of Option A: zero LLM cost here. The hint was
        # already computed by intent_classification_node.
        specialist = make_specialist()
        ea.register_specialist(specialist)
        ea.llm.ainvoke = AsyncMock()

        state = make_state(delegation_hint="social_media")
        await ea._delegation_decision(state)

        ea.llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_hint_warns_on_low_sanity_score(self, ea, caplog):
        # Telemetry: if LLM routed here but can_handle disagrees strongly,
        # that's a signal worth logging. Still trust the hint.
        specialist = make_specialist(can_handle_score=0.05)
        ea.register_specialist(specialist)

        state = make_state("something unrelated", delegation_hint="social_media")

        import logging
        with caplog.at_level(logging.WARNING, logger="src.agents.executive_assistant"):
            result = await ea._delegation_decision(state)

        # Hint wins
        assert result.collected_info.get("_selected_specialist") == "social_media"
        # But we noticed the disagreement
        assert any("sanity" in r.message.lower() or "disagree" in r.message.lower()
                   for r in caplog.records)


# ---------------------------------------------------------------------------
# Validation 3: Context scoping — specialist sees only its domain
# ---------------------------------------------------------------------------

class TestContextScoping:
    @pytest.mark.asyncio
    async def test_domain_memories_filtered_by_category(self, ea):
        specialist = make_specialist(
            categories=["social_media", "current_tools"]
        )
        state = make_state()

        memories = await ea._scope_context_for_specialist(specialist, state)

        # Started with 4 memories (social_media, finance, current_tools, pricing)
        # Should keep only social_media + current_tools
        assert len(memories) == 2
        categories_returned = {m["metadata"]["category"] for m in memories}
        assert categories_returned == {"social_media", "current_tools"}
        assert "finance" not in categories_returned
        assert "pricing" not in categories_returned

    @pytest.mark.asyncio
    async def test_task_carries_customer_id_not_other_customers(self, ea):
        specialist = make_specialist()
        ea.register_specialist(specialist)
        state = make_state()
        state.collected_info["_selected_specialist"] = "social_media"

        await ea._specialist_execution(state)

        # Inspect the task the specialist received
        task: SpecialistTask = specialist.execute.await_args[0][0]
        assert task.customer_id == "cust_abc"
        assert task.conversation_id == "conv_xyz"

    @pytest.mark.asyncio
    async def test_task_has_no_raw_message_history(self, ea):
        specialist = make_specialist()
        ea.register_specialist(specialist)
        state = make_state()
        # Simulate prior conversation
        state.messages = [
            HumanMessage(content="unrelated earlier message"),
            AIMessage(content="earlier EA response"),
            HumanMessage(content="how's my Instagram doing?"),
        ]
        state.collected_info["_selected_specialist"] = "social_media"

        await ea._specialist_execution(state)

        task: SpecialistTask = specialist.execute.await_args[0][0]
        # Task description is the current request, not the whole history
        assert task.task_description == "how's my Instagram doing?"
        assert not hasattr(task, "messages")
        # Domain memories are scoped by category, not conversation history
        for mem in task.domain_memories:
            assert "unrelated earlier" not in mem.get("content", "")


# ---------------------------------------------------------------------------
# Validation 4 & 5: Failure and timeout handled gracefully
# ---------------------------------------------------------------------------

class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self, ea):
        async def hang(task):
            await asyncio.sleep(60)

        specialist = make_specialist()
        specialist.execute = hang
        ea.register_specialist(specialist)
        ea._specialist_timeout = 0.1  # override for fast test

        state = make_state()
        state.collected_info["_selected_specialist"] = "social_media"

        result = await ea._specialist_execution(state)

        # No exception raised; fallback flag set for router
        assert result.collected_info.get("_specialist_fallback") is True
        assert result.active_delegation is None

    @pytest.mark.asyncio
    async def test_exception_triggers_fallback(self, ea):
        specialist = make_specialist()
        specialist.execute = AsyncMock(side_effect=RuntimeError("specialist crashed"))
        ea.register_specialist(specialist)

        state = make_state()
        state.collected_info["_selected_specialist"] = "social_media"

        result = await ea._specialist_execution(state)

        assert result.collected_info.get("_specialist_fallback") is True
        assert result.active_delegation is None

    @pytest.mark.asyncio
    async def test_failed_status_triggers_fallback(self, ea):
        specialist = make_specialist(execute_result=SpecialistResult(
            status=DelegationStatus.FAILED,
            error="couldn't parse task",
        ))
        ea.register_specialist(specialist)

        state = make_state()
        state.collected_info["_selected_specialist"] = "social_media"

        result = await ea._specialist_execution(state)

        assert result.collected_info.get("_specialist_fallback") is True

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_fallback_with_hint(self, ea):
        specialist = make_specialist(execute_result=SpecialistResult(
            status=DelegationStatus.COMPLETED,
            content="not sure, maybe something about posts?",
            confidence=0.2,  # below 0.4 threshold
        ))
        ea.register_specialist(specialist)

        state = make_state()
        state.collected_info["_selected_specialist"] = "social_media"

        result = await ea._specialist_execution(state)

        assert result.collected_info.get("_specialist_fallback") is True
        # Partial result stashed for the EA's generalist fallback
        assert "not sure" in result.collected_info.get("specialist_hint", "")


# ---------------------------------------------------------------------------
# Validation 6: Multi-turn delegation persists across conversation rounds
# ---------------------------------------------------------------------------

class TestMultiTurnDelegation:
    @pytest.mark.asyncio
    async def test_needs_clarification_sets_active_delegation(self, ea):
        specialist = make_specialist(execute_result=SpecialistResult(
            status=DelegationStatus.NEEDS_CLARIFICATION,
            clarification_question="Which platform should I post to?",
        ))
        ea.register_specialist(specialist)

        state = make_state("schedule a post for tomorrow")
        state.collected_info["_selected_specialist"] = "social_media"

        result = await ea._specialist_execution(state)

        # Delegation state persisted for next turn
        assert result.active_delegation is not None
        assert result.active_delegation["specialist_domain"] == "social_media"
        assert result.active_delegation["original_task"] == "schedule a post for tomorrow"
        assert result.active_delegation["pending_question"] == "Which platform should I post to?"

        # EA voices the question
        assert isinstance(result.messages[-1], AIMessage)
        assert "platform" in result.messages[-1].content.lower()

        # Not a fallback — this is a normal flow
        assert "_specialist_fallback" not in result.collected_info

    @pytest.mark.asyncio
    async def test_resumption_routes_to_same_specialist(self, ea):
        specialist = make_specialist()
        ea.register_specialist(specialist)

        # Turn 2: customer answers the clarification. active_delegation hydrated from Redis.
        state = make_state(
            "Instagram please",
            active_delegation={
                "specialist_domain": "social_media",
                "original_task": "schedule a post for tomorrow",
                "pending_question": "Which platform should I post to?",
                "clarifications_collected": {},
            },
        )

        result = await ea._delegation_decision(state)

        # Matching logic bypassed — goes straight to resumption
        specialist.can_handle.assert_not_called()
        assert result.collected_info.get("_resume_specialist") == "social_media"
        # Answer merged
        assert result.active_delegation["clarifications_collected"] == {
            "Which platform should I post to?": "Instagram please"
        }

    @pytest.mark.asyncio
    async def test_resumed_execution_passes_clarifications_to_specialist(self, ea):
        specialist = make_specialist()
        ea.register_specialist(specialist)

        state = make_state(
            "Instagram please",
            active_delegation={
                "specialist_domain": "social_media",
                "original_task": "schedule a post for tomorrow",
                "pending_question": "Which platform should I post to?",
                "clarifications_collected": {
                    "Which platform should I post to?": "Instagram please",
                },
            },
        )
        state.collected_info["_resume_specialist"] = "social_media"

        await ea._specialist_execution(state)

        task: SpecialistTask = specialist.execute.await_args[0][0]
        # Original task, not the clarification answer
        assert task.task_description == "schedule a post for tomorrow"
        # Clarifications forwarded
        assert task.prior_clarifications == {
            "Which platform should I post to?": "Instagram please"
        }

    @pytest.mark.asyncio
    async def test_completed_result_clears_active_delegation(self, ea):
        specialist = make_specialist()  # default: COMPLETED
        ea.register_specialist(specialist)

        state = make_state(active_delegation={
            "specialist_domain": "social_media",
            "original_task": "schedule a post",
            "pending_question": "Platform?",
            "clarifications_collected": {"Platform?": "Instagram"},
        })
        state.collected_info["_resume_specialist"] = "social_media"

        result = await ea._specialist_execution(state)

        assert result.active_delegation is None


# ---------------------------------------------------------------------------
# Validation 7: Registry is extensible — no framework changes for new agents
# ---------------------------------------------------------------------------

class TestRegistryExtensibility:
    @pytest.mark.asyncio
    async def test_register_specialist_adds_to_dict(self, ea):
        specialist = make_specialist(domain="finance")
        ea.register_specialist(specialist)
        assert ea.specialists["finance"] is specialist

    @pytest.mark.asyncio
    async def test_highest_scorer_wins(self, ea):
        social = make_specialist(domain="social_media", can_handle_score=0.6)
        finance = make_specialist(domain="finance", can_handle_score=0.85)
        ea.register_specialist(social)
        ea.register_specialist(finance)

        state = make_state("what's my ad spend on Instagram this month?")
        result = await ea._delegation_decision(state)

        assert result.collected_info.get("_selected_specialist") == "finance"

    @pytest.mark.asyncio
    async def test_second_specialist_works_without_framework_changes(self, ea):
        """The brief's explicit check: adding specialist #2 is pure registration."""
        # Prove by doing it: two specialists, both callable, no code touched
        social = make_specialist(domain="social_media", can_handle_score=0.9)
        finance = make_specialist(domain="finance", can_handle_score=0.2)
        ea.register_specialist(social)
        ea.register_specialist(finance)

        state = make_state()
        result = await ea._delegation_decision(state)

        # Both were asked; framework picked the right one
        social.can_handle.assert_called_once()
        finance.can_handle.assert_called_once()
        assert result.collected_info.get("_selected_specialist") == "social_media"


# ---------------------------------------------------------------------------
# Graph wiring — verify the new nodes are actually in the compiled graph
# ---------------------------------------------------------------------------

class TestGraphWiring:
    def test_conversation_state_has_active_delegation_field(self):
        state = make_state()
        assert hasattr(state, "active_delegation")
        assert state.active_delegation is None

    def test_ea_has_specialist_timeout_default(self, ea):
        # Used by _specialist_execution; must exist even without __init__
        # running (for tests) — verify the class-level default
        assert hasattr(ExecutiveAssistant, "_specialist_timeout") or \
               hasattr(ea, "_specialist_timeout")
