"""
generate(): description -> Generated | NeedsClarification.

The LLM is mocked — we only test orchestration. Parsing quality is the
LLM's job; our job is routing on confidence/gaps and wiring the pipeline.
"""
import pytest

from src.agents.ai_ml.workflow_generator import (
    Generated,
    NeedsClarification,
    ParsedProcess,
    StepSpec,
    TriggerSpec,
    generate,
    parse,
)


class FakeLLM:
    """Duck-types ChatOpenAI.with_structured_output(Schema).ainvoke(prompt)."""

    def __init__(self, returns: ParsedProcess):
        self._returns = returns
        self.captured_schema = None
        self.captured_prompt = None

    def with_structured_output(self, schema):
        self.captured_schema = schema
        return self

    async def ainvoke(self, prompt):
        self.captured_prompt = prompt
        return self._returns


def confident_parse():
    return ParsedProcess(
        trigger=TriggerSpec(kind="schedule", cron="0 9 * * 1"),
        steps=[StepSpec(action="fetch data", service="airtable")],
        confidence=0.9,
        gaps=[],
    )


# --- confidence routing ------------------------------------------------------

class TestConfidenceRouting:
    async def test_high_confidence_no_gaps_returns_generated(self):
        llm = FakeLLM(returns=confident_parse())
        result = await generate("fetch airtable every monday", llm=llm)
        assert isinstance(result, Generated)

    async def test_gaps_returns_needs_clarification(self):
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="do something")],
            confidence=0.9,
            gaps=["unclear what 'flag' means — notify? tag?"],
        )
        llm = FakeLLM(returns=parsed)
        result = await generate("flag the bad ones", llm=llm)
        assert isinstance(result, NeedsClarification)
        assert result.questions == ["unclear what 'flag' means — notify? tag?"]

    async def test_low_confidence_returns_needs_clarification(self):
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="automate marketing")],
            confidence=0.3,
            gaps=["which channels?", "what content?"],
        )
        llm = FakeLLM(returns=parsed)
        result = await generate("automate my marketing", llm=llm)
        assert isinstance(result, NeedsClarification)
        assert len(result.questions) == 2

    async def test_low_confidence_empty_gaps_still_asks(self):
        # Model was overconfident about its uncertainty — gaps empty but
        # confidence low. Shouldn't return NeedsClarification with zero
        # questions.
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="thing")],
            confidence=0.4,
            gaps=[],
        )
        llm = FakeLLM(returns=parsed)
        result = await generate("do the thing", llm=llm)
        assert isinstance(result, NeedsClarification)
        assert len(result.questions) >= 1  # generic fallback question

    async def test_confidence_exactly_at_threshold_passes(self):
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="work")],
            confidence=0.6,
            gaps=[],
        )
        llm = FakeLLM(returns=parsed)
        result = await generate("do work", llm=llm)
        assert isinstance(result, Generated)

    async def test_needs_clarification_preserves_partial(self):
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="schedule", cron="0 9 * * *"),
            steps=[StepSpec(action="fetch", service="stripe")],
            confidence=0.4,
            gaps=["which stripe resource?"],
        )
        llm = FakeLLM(returns=parsed)
        result = await generate("pull stripe stuff daily", llm=llm)
        assert isinstance(result, NeedsClarification)
        # EA stashes this, merges answer, re-calls generate()
        assert result.partial.trigger.cron == "0 9 * * *"
        assert result.partial.steps[0].service == "stripe"


# --- generated payload -------------------------------------------------------

class TestGeneratedPayload:
    async def test_generated_has_workflow_explanation_customization(self):
        llm = FakeLLM(returns=confident_parse())
        result = await generate("...", llm=llm)
        assert isinstance(result, Generated)
        assert len(result.workflow.nodes) == 2  # trigger + 1 step
        assert "1." in result.explanation
        # airtable is unknown → http fallback → 1 note
        assert len(result.customization_required) == 1

    async def test_explanation_matches_workflow(self):
        # Node names from the workflow should appear in the explanation
        llm = FakeLLM(returns=confident_parse())
        result = await generate("...", llm=llm)
        for node in result.workflow.nodes:
            assert node.name in result.explanation

    async def test_calendly_stripe_end_to_end(self):
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="schedule", cron="0 17 * * 5"),
            steps=[
                StepSpec(action="export appointments", service="calendly"),
                StepSpec(action="fetch payments", service="stripe"),
                StepSpec(action="cross-reference", inputs_from=[0, 1]),
                StepSpec(action="keep no-shows", condition="unpaid"),
                StepSpec(action="send reschedule link", service="email"),
            ],
            confidence=0.85,
            gaps=[],
        )
        llm = FakeLLM(returns=parsed)
        result = await generate("the friday calendly thing", llm=llm)
        assert isinstance(result, Generated)
        assert len(result.workflow.nodes) == 6
        assert "calendly" in result.explanation.lower()
        assert len(result.customization_required) == 3  # calendly, stripe, smtp


# --- parse() prompt construction ---------------------------------------------

class TestParsePrompt:
    async def test_uses_parsed_process_as_schema(self):
        llm = FakeLLM(returns=confident_parse())
        await parse("do stuff", {}, None, llm)
        assert llm.captured_schema is ParsedProcess

    async def test_description_reaches_prompt_verbatim(self):
        llm = FakeLLM(returns=confident_parse())
        desc = "every friday export the calendly appointments"
        await parse(desc, {}, None, llm)
        assert desc in str(llm.captured_prompt)

    async def test_template_hint_reaches_prompt(self):
        llm = FakeLLM(returns=confident_parse())
        hint = {"triggers": ["schedule"], "actions": ["fetch", "email"]}
        await parse("weekly report", {}, hint, llm)
        prompt = str(llm.captured_prompt).lower()
        assert "fetch" in prompt
        assert "email" in prompt

    async def test_no_hint_no_hint_section(self):
        llm = FakeLLM(returns=confident_parse())
        await parse("weekly report", {}, None, llm)
        prompt = str(llm.captured_prompt).lower()
        # No hint → don't mention templates/skeletons
        assert "skeleton" not in prompt
        assert "template" not in prompt

    async def test_business_insights_reach_prompt(self):
        llm = FakeLLM(returns=confident_parse())
        insights = {"tools_mentioned": ["calendly", "stripe"]}
        await parse("the friday thing", insights, None, llm)
        prompt = str(llm.captured_prompt).lower()
        assert "calendly" in prompt
        assert "stripe" in prompt

    async def test_empty_insights_does_not_crash(self):
        llm = FakeLLM(returns=confident_parse())
        result = await parse("do stuff", {}, None, llm)
        assert isinstance(result, ParsedProcess)


# --- generate() wiring -------------------------------------------------------

class TestGenerateWiring:
    async def test_insights_flow_through_to_parse(self):
        llm = FakeLLM(returns=confident_parse())
        insights = {"tools_mentioned": ["notion"]}
        await generate("...", business_insights=insights, llm=llm)
        assert "notion" in str(llm.captured_prompt).lower()

    async def test_template_hint_flows_through(self):
        llm = FakeLLM(returns=confident_parse())
        hint = {"actions": ["transform", "notify"]}
        await generate("...", template_hint=hint, llm=llm)
        assert "transform" in str(llm.captured_prompt).lower()

    async def test_llm_required(self):
        # No default LLM — WorkflowCreator always passes self.llm.
        # Forgetting it is a programmer error.
        with pytest.raises(TypeError):
            await generate("...")
