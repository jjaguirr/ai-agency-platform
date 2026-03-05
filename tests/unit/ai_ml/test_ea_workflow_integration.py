"""
Integration: generate() wired into the EA's LangGraph.

Mocks redis/Memory to instantiate EA, injects a fake LLM, drives
_create_workflow_node and _handle_clarification directly. The graph
itself compiles in __init__ — we don't drive it end-to-end, just the
nodes we changed.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.ai_ml.workflow_generator import ParsedProcess, StepSpec, TriggerSpec


class FakeLLM:
    def __init__(self, returns: ParsedProcess):
        self._returns = returns

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, prompt):
        return self._returns


@pytest.fixture
def ea():
    """EA with redis/mem0 mocked out. LLM is None; tests inject their own."""
    with patch("src.agents.executive_assistant.redis.Redis", return_value=MagicMock()), \
         patch("src.agents.executive_assistant.Memory") as mock_mem, \
         patch.dict("os.environ", {}, clear=False):
        # Clear OPENAI_API_KEY so llm init is skipped
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        mock_mem.from_config.return_value = MagicMock()
        from src.agents.executive_assistant import ExecutiveAssistant
        yield ExecutiveAssistant("test-customer")


@pytest.fixture
def state():
    from src.agents.executive_assistant import BusinessContext, ConversationState
    return ConversationState(
        messages=[HumanMessage(content="every friday export calendly appointments")],
        customer_id="test-customer",
        conversation_id="conv-1",
        business_context=BusinessContext(),
        needs_workflow=True,
        workflow_created=False,
    )


# --- _create_workflow_node: Generated path ----------------------------------

class TestCreateWorkflowNodeGenerated:
    async def test_high_confidence_sets_workflow_created(self, ea, state):
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="schedule", cron="0 17 * * 5"),
            steps=[StepSpec(action="export appointments", service="calendly")],
            confidence=0.9,
            gaps=[],
        ))
        result_state = await ea._create_workflow_node(state)
        assert result_state.workflow_created is True
        assert result_state.requires_clarification is False

    async def test_explanation_appended_to_messages(self, ea, state):
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="schedule", cron="0 17 * * 5"),
            steps=[StepSpec(action="export appointments", service="calendly")],
            confidence=0.9,
            gaps=[],
        ))
        before = len(state.messages)
        result_state = await ea._create_workflow_node(state)
        assert len(result_state.messages) == before + 1
        last = result_state.messages[-1]
        assert isinstance(last, AIMessage)
        assert "1." in last.content  # numbered explanation
        assert "calendly" in last.content.lower()

    async def test_workflow_json_stashed_in_collected_info(self, ea, state):
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="schedule", cron="0 17 * * 5"),
            steps=[StepSpec(action="export", service="calendly")],
            confidence=0.9,
            gaps=[],
        ))
        result_state = await ea._create_workflow_node(state)
        wf = result_state.collected_info.get("generated_workflow")
        assert wf is not None
        assert "nodes" in wf
        assert len(wf["nodes"]) == 2  # trigger + 1 step


# --- _create_workflow_node: NeedsClarification path -------------------------

class TestCreateWorkflowNodeClarification:
    async def test_low_confidence_sets_requires_clarification(self, ea, state):
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="automate stuff")],
            confidence=0.3,
            gaps=["which tool?", "what schedule?"],
        ))
        result_state = await ea._create_workflow_node(state)
        assert result_state.workflow_created is False
        assert result_state.requires_clarification is True

    async def test_gaps_become_pending_questions(self, ea, state):
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="do thing")],
            confidence=0.9,
            gaps=["what does 'flag' mean?"],
        ))
        result_state = await ea._create_workflow_node(state)
        assert result_state.pending_questions == ["what does 'flag' mean?"]

    async def test_partial_parse_stashed_for_resume(self, ea, state):
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="schedule", cron="0 9 * * *"),
            steps=[StepSpec(action="fetch", service="stripe")],
            confidence=0.4,
            gaps=["which resource?"],
        ))
        result_state = await ea._create_workflow_node(state)
        partial = result_state.collected_info.get("partial_parse")
        assert partial is not None
        assert partial["trigger"]["cron"] == "0 9 * * *"
        assert partial["steps"][0]["service"] == "stripe"

    async def test_no_explanation_appended_on_clarification(self, ea, state):
        # The clarification node asks the questions — this node shouldn't
        # also speak.
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="x")],
            confidence=0.3,
            gaps=["?"],
        ))
        before = len(state.messages)
        result_state = await ea._create_workflow_node(state)
        assert len(result_state.messages) == before


# --- _create_workflow_node: guards ------------------------------------------

class TestCreateWorkflowNodeGuards:
    async def test_skips_when_not_needs_workflow(self, ea, state):
        state.needs_workflow = False
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="manual"), steps=[], confidence=0.9,
        ))
        result_state = await ea._create_workflow_node(state)
        assert result_state.workflow_created is False
        assert "generated_workflow" not in result_state.collected_info

    async def test_skips_when_already_created(self, ea, state):
        state.workflow_created = True
        ea.llm = FakeLLM(returns=ParsedProcess(
            trigger=TriggerSpec(kind="manual"), steps=[], confidence=0.9,
        ))
        before = len(state.messages)
        result_state = await ea._create_workflow_node(state)
        assert len(result_state.messages) == before

    async def test_no_llm_falls_back_gracefully(self, ea, state):
        ea.llm = None
        result_state = await ea._create_workflow_node(state)
        assert result_state.workflow_created is False
        # Should tell the customer something, not crash
        assert len(result_state.messages) > 1


# --- _handle_clarification: pending_questions path --------------------------

class TestHandleClarificationPending:
    async def test_uses_pending_questions_directly(self, ea, state):
        # Generator produced targeted questions — use them, don't ask the
        # LLM to invent new ones.
        state.pending_questions = ["which stripe resource?", "how often?"]
        ea.llm = MagicMock()  # should NOT be called
        ea.memory.get_business_context = AsyncMock()

        result_state = await ea._handle_clarification(state)

        last = result_state.messages[-1].content
        assert "which stripe resource?" in last
        assert "how often?" in last
        ea.llm.ainvoke.assert_not_called()

    async def test_consumes_pending_questions(self, ea, state):
        state.pending_questions = ["q1"]
        ea.memory.get_business_context = AsyncMock()
        result_state = await ea._handle_clarification(state)
        # Next turn shouldn't re-ask the same questions
        assert result_state.pending_questions == []

    async def test_empty_pending_falls_through_to_llm(self, ea, state):
        # Old behavior preserved: no pending_questions → generic LLM prompt
        from src.agents.executive_assistant import BusinessContext
        state.pending_questions = []
        ea.memory.get_business_context = AsyncMock(return_value=BusinessContext())
        ea.llm = AsyncMock()
        ea.llm.ainvoke.return_value = MagicMock(content="generic clarification")

        result_state = await ea._handle_clarification(state)

        ea.llm.ainvoke.assert_called_once()
        assert result_state.messages[-1].content == "generic clarification"
