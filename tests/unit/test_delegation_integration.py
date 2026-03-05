"""
Delegation framework — integration tier.

test_delegation.py proves the node methods work when called directly. This
file proves the *wiring* works: the compiled graph routes through them, and
handle_customer_interaction's Redis plumbing round-trips active_delegation.

Uses a real EA constructor (real compiled graph) with I/O swapped post-hoc.
Construction succeeds without live services — Redis is lazy, Postgres/Mem0
failures are caught and logged, LLM stays None until we replace it.
"""
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.executive_assistant import (
    BusinessContext,
    ConversationChannel,
    ConversationIntent,
    ConversationPhase,
    ConversationState,
    ExecutiveAssistant,
)
from src.agents.specialists.base import (
    DelegationStatus,
    SpecialistResult,
    SpecialistTask,
)


# ---------------------------------------------------------------------------
# Fixture — real __init__, real compiled graph, mocked I/O
# ---------------------------------------------------------------------------

@pytest.fixture
def compiled_ea(caplog):
    # Construction logs warnings about missing services — expected, suppress.
    with caplog.at_level(logging.CRITICAL, logger="src.agents.executive_assistant"):
        ea = ExecutiveAssistant(customer_id="test_integ")

    # Swap the memory layer. Redis connect is lazy so no error fired yet.
    ea.memory = MagicMock()
    ea.memory.search_business_knowledge = AsyncMock(return_value=[
        {"content": "IG reels outperform static posts",
         "metadata": {"category": "social_media"}},
    ])
    ea.memory.get_business_context = AsyncMock(
        return_value=BusinessContext(business_name="Acme Co", industry="retail")
    )

    # Dict-backed conversation context for round-trip verification.
    store: dict[str, dict] = {}

    async def _store_ctx(cid, ctx):
        store[cid] = ctx

    async def _get_ctx(cid):
        return store.get(cid, {})

    ea.memory.store_conversation_context = AsyncMock(side_effect=_store_ctx)
    ea.memory.get_conversation_context = AsyncMock(side_effect=_get_ctx)

    # LLM — tests configure side_effect per-call-site.
    ea.llm = MagicMock()

    return ea, store


# ---------------------------------------------------------------------------
# Graph topology — catches edge-map key typos at compile time
# ---------------------------------------------------------------------------

class TestGraphTopology:
    def test_delegation_nodes_in_compiled_graph(self, compiled_ea):
        ea, _ = compiled_ea
        nodes = set(ea.graph.get_graph().nodes.keys())
        assert "delegation_decision" in nodes
        assert "specialist_execution" in nodes

    def test_delegation_nodes_reachable_from_intent_classification(self, compiled_ea):
        # If route_after_intent_classification returns a key not in the edge
        # map, LangGraph won't build the edge — node becomes an orphan.
        ea, _ = compiled_ea
        edges = ea.graph.get_graph().edges
        sources_to_targets = {(e.source, e.target) for e in edges}
        # intent_classification must be able to reach delegation_decision
        assert ("intent_classification", "delegation_decision") in sources_to_targets
        # delegation_decision must reach both outcomes
        assert ("delegation_decision", "specialist_execution") in sources_to_targets
        assert ("delegation_decision", "handle_general_assistance") in sources_to_targets
        # specialist_execution must reach both outcomes
        assert ("specialist_execution", "update_context") in sources_to_targets
        assert ("specialist_execution", "handle_general_assistance") in sources_to_targets

    def test_social_media_specialist_auto_registered(self, compiled_ea):
        ea, _ = compiled_ea
        assert "social_media" in ea.specialists
        # It's the real class, not a mock
        from src.agents.specialists.social_media import SocialMediaSpecialist
        assert isinstance(ea.specialists["social_media"], SocialMediaSpecialist)


# ---------------------------------------------------------------------------
# Full graph.ainvoke — proves the routers actually route
# ---------------------------------------------------------------------------

class TestGraphDelegationPath:
    """
    End-to-end through the compiled graph:
      intent_classification → route → delegation_decision → route
      → specialist_execution → route → update_context → END

    Uses the real auto-registered SocialMediaSpecialist. "how's my Instagram
    doing?" hits its metrics handler, which doesn't need an LLM — so the
    only LLM touchpoints are the EA's own (intent, strategic gate, weave).
    """

    @pytest.mark.asyncio
    async def test_full_delegation_chain_through_compiled_graph(self, compiled_ea):
        ea, _ = compiled_ea

        # Two sequential LLM calls along the happy path:
        #   1. intent_classification_node  → intent + confidence + delegation hint
        #   2. _weave_specialist_result    → conversational reformulation
        # _delegation_decision makes NO call — it reads the hint from step 1.
        ea.llm.ainvoke = AsyncMock(side_effect=[
            MagicMock(content="TASK_DELEGATION,0.9,social_media"),
            MagicMock(content="Good news — your Instagram engagement is up this week."),
        ])

        state = ConversationState(
            # Hits the real SocialMediaSpecialist's metrics handler (no
            # specialist-side LLM needed). Hint routing means keyword score
            # is now just a sanity log, not a gate.
            messages=[HumanMessage(content="how's my Instagram engagement doing?")],
            customer_id="test_integ",
            conversation_id="conv_graph",
            business_context=BusinessContext(
                business_name="Acme Co", industry="retail"
            ),
            current_intent=ConversationIntent.UNKNOWN,
            conversation_phase=ConversationPhase.INITIAL_CONTACT,
        )

        result = await ea.graph.ainvoke(state)

        # LangGraph returns dict for StateGraph; pull messages either way
        messages = result["messages"] if isinstance(result, dict) else result.messages

        # Exactly two LLM calls — intent(+hint) then weave. No strategic gate.
        assert ea.llm.ainvoke.await_count == 2
        # Hint was parsed and carried through
        collected = result.get("collected_info", {}) if isinstance(result, dict) else result.collected_info
        assert collected.get("_delegation_hint") == "social_media"

        # Final message is the woven specialist result (an AIMessage)
        assert isinstance(messages[-1], AIMessage)
        assert "engagement" in messages[-1].content.lower()

        # No fallback flag — clean path through specialist_execution → update_context
        collected = result.get("collected_info", {}) if isinstance(result, dict) else result.collected_info
        assert collected.get("_specialist_fallback") is not True

    @pytest.mark.asyncio
    async def test_ea_hint_routes_to_general_assistance(self, compiled_ea):
        ea, _ = compiled_ea

        # Intent classifier decided this is strategic (hint="ea"). Keywords
        # would have matched — instagram(0.45)+post(0.35)=0.8 — but the hint
        # overrides. _delegation_decision falls through, router sends to
        # general_assistance, which makes its own LLM call.
        ea.llm.ainvoke = AsyncMock(side_effect=[
            MagicMock(content="BUSINESS_ASSISTANCE,0.85,ea"),
            MagicMock(content="For a retail brand, posting frequency depends on..."),
        ])

        state = ConversationState(
            messages=[HumanMessage(content="should I post more on Instagram?")],
            customer_id="test_integ",
            conversation_id="conv_advise",
            business_context=BusinessContext(business_name="Acme Co", industry="retail"),
            current_intent=ConversationIntent.UNKNOWN,
            conversation_phase=ConversationPhase.INITIAL_CONTACT,
        )

        result = await ea.graph.ainvoke(state)

        collected = result.get("collected_info", {}) if isinstance(result, dict) else result.collected_info
        # Hint was parsed
        assert collected.get("_delegation_hint") == "ea"
        # And respected — no specialist selected despite keyword match
        assert "_selected_specialist" not in collected


# ---------------------------------------------------------------------------
# handle_customer_interaction — Redis round-trip for multi-turn delegation
# ---------------------------------------------------------------------------

class TestMultiTurnRedisRoundTrip:
    """
    Proves Edits 9 & 10: active_delegation written on turn N is hydrated
    into the ConversationState passed to graph.ainvoke on turn N+1.

    Graph is mocked here — we're isolating the plumbing, not the nodes.
    A dict-key mismatch between the store and the read would break this
    test but pass every node-level test in test_delegation.py.
    """

    @pytest.mark.asyncio
    async def test_active_delegation_survives_across_calls(self, compiled_ea):
        ea, store = compiled_ea

        # Turn 1 outcome: specialist asked a clarifying question.
        turn1_delegation = {
            "specialist_domain": "social_media",
            "original_task": "schedule a post tomorrow",
            "pending_question": "Which platform?",
            "clarifications_collected": {},
        }

        # Capture the state each graph invocation receives.
        captured_states: list[ConversationState] = []

        async def fake_graph(state):
            captured_states.append(state)
            # Turn 1: set active_delegation. Turn 2: clear it (completion).
            is_turn_1 = len(captured_states) == 1
            return {
                "messages": state.messages + [AIMessage(
                    content="Which platform?" if is_turn_1 else "Scheduled for Instagram."
                )],
                "active_delegation": turn1_delegation if is_turn_1 else None,
                "current_intent": ConversationIntent.TASK_DELEGATION,
                "confidence_score": 0.9,
                "workflow_created": False,
                "conversation_depth": len(captured_states),
            }

        ea.graph = MagicMock()
        ea.graph.ainvoke = fake_graph

        # --- Turn 1: specialist asks for clarification ---
        resp1 = await ea.handle_customer_interaction(
            "schedule a post tomorrow",
            ConversationChannel.CHAT,
            conversation_id="conv_rt",
        )
        assert "platform" in resp1.lower()

        # active_delegation persisted to the dict-backed store
        assert "conv_rt" in store
        assert store["conv_rt"]["active_delegation"] == turn1_delegation

        # Turn 1's input state had no prior delegation (fresh conversation)
        assert captured_states[0].active_delegation is None

        # --- Turn 2: customer answers; same conversation_id ---
        resp2 = await ea.handle_customer_interaction(
            "Instagram please",
            ConversationChannel.CHAT,
            conversation_id="conv_rt",
        )
        assert "scheduled" in resp2.lower()

        # Turn 2's input state was hydrated from the store — THE key assertion.
        # This fails if the write key and read key don't match.
        assert captured_states[1].active_delegation == turn1_delegation

        # Turn 2 cleared it → store reflects completion
        assert store["conv_rt"]["active_delegation"] is None

    @pytest.mark.asyncio
    async def test_redis_read_failure_does_not_abort_interaction(self, compiled_ea):
        # The defensive wrapper around get_conversation_context: a Redis
        # hiccup on hydration shouldn't kill an otherwise-fine interaction.
        ea, _ = compiled_ea
        ea.memory.get_conversation_context = AsyncMock(
            side_effect=ConnectionError("redis down")
        )

        captured = []

        async def fake_graph(state):
            captured.append(state)
            return {
                "messages": state.messages + [AIMessage(content="Hi there.")],
                "active_delegation": None,
                "current_intent": ConversationIntent.GENERAL_CONVERSATION,
                "confidence_score": 0.8,
                "workflow_created": False,
                "conversation_depth": 1,
            }

        ea.graph = MagicMock()
        ea.graph.ainvoke = fake_graph

        resp = await ea.handle_customer_interaction(
            "hello", ConversationChannel.CHAT, conversation_id="conv_resilient"
        )

        # Graph still ran — not the "I apologize" error fallback
        assert len(captured) == 1
        assert "apologize" not in resp.lower()
        # Hydration failed gracefully → fresh state, no active_delegation
        assert captured[0].active_delegation is None
