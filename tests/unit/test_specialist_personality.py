"""
Tests for personality-aware response synthesis.

The EA's _synthesize_specialist_result must respect the customer's tone
setting. The LLM path injects _TONE_GUIDANCE into the prompt; the no-LLM
path applies tone-aware formatting to the specialist's summary_for_ea.

Four tones must produce meaningfully different outputs for the same
specialist result.
"""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base.specialist import SpecialistResult, SpecialistStatus


# --- Fixtures ---------------------------------------------------------------

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

        instance = ExecutiveAssistant(customer_id="cust_tone")
        instance.llm = None
        yield instance


@pytest.fixture
def sample_result():
    """A finance specialist result used across all tone tests."""
    return SpecialistResult(
        status=SpecialistStatus.COMPLETED,
        domain="finance",
        payload={"amount": 500.0, "vendor": "Acme Corp", "category": "marketing"},
        confidence=0.85,
        summary_for_ea="Tracked $500.00 → Acme Corp (category: marketing).",
    )


@pytest.fixture
def context():
    from src.agents.executive_assistant import BusinessContext
    return BusinessContext(business_name="Sparkle & Shine")


# --- LLM path: prompt includes tone guidance --------------------------------

class TestLLMSynthesisToneGuidance:
    """When an LLM is available, the synthesis prompt must include the
    matching _TONE_GUIDANCE string for the configured tone."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tone,expected_fragment", [
        ("professional", "warm, professional"),
        ("friendly", "casual and friendly"),
        ("concise", "brief"),
        ("detailed", "thorough"),
    ])
    async def test_llm_prompt_includes_tone_guidance(
        self, ea, sample_result, context, tone, expected_fragment,
    ):
        from src.agents.executive_assistant import _TONE_GUIDANCE

        ea._personality = {"tone": tone, "language": "en", "name": "Aria"}

        llm = AsyncMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="relayed"))
        ea.llm = llm

        await ea._synthesize_specialist_result(sample_result, context)

        prompt = llm.ainvoke.call_args.args[0][0].content
        assert expected_fragment in prompt.lower(), (
            f"Tone '{tone}' guidance not found in prompt: {prompt[:200]}"
        )

    @pytest.mark.asyncio
    async def test_llm_prompt_uses_personality_name(self, ea, sample_result, context):
        ea._personality = {"tone": "friendly", "language": "en", "name": "Beacon"}

        llm = AsyncMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
        ea.llm = llm

        await ea._synthesize_specialist_result(sample_result, context)

        prompt = llm.ainvoke.call_args.args[0][0].content
        assert "Beacon" in prompt
        assert "Sarah" not in prompt


# --- No-LLM path: tone-aware formatting ------------------------------------

class TestNoLLMToneFormatting:
    """Without an LLM, the EA formats the specialist's summary_for_ea
    differently based on tone. Each tone must produce distinct output."""

    @pytest.mark.asyncio
    async def test_professional_returns_summary_as_is(self, ea, sample_result, context):
        ea._personality = {"tone": "professional", "language": "en", "name": "Aria"}
        result = await ea._synthesize_specialist_result(sample_result, context)
        assert result == sample_result.summary_for_ea

    @pytest.mark.asyncio
    async def test_concise_strips_preamble(self, ea, context):
        ea._personality = {"tone": "concise", "language": "en", "name": "Aria"}
        wordy = SpecialistResult(
            status=SpecialistStatus.COMPLETED, domain="finance",
            payload={"amount": 500}, confidence=0.85,
            summary_for_ea="Tracked $500.00 → Acme Corp (category: marketing).",
        )
        result = await ea._synthesize_specialist_result(wordy, context)
        # Concise should be short — no extra framing added
        assert len(result) <= len(wordy.summary_for_ea)

    @pytest.mark.asyncio
    async def test_friendly_adds_casual_framing(self, ea, sample_result, context):
        ea._personality = {"tone": "friendly", "language": "en", "name": "Aria"}
        result = await ea._synthesize_specialist_result(sample_result, context)
        # Friendly wraps with casual framing — should differ from raw summary
        assert result != sample_result.summary_for_ea

    @pytest.mark.asyncio
    async def test_detailed_includes_payload(self, ea, sample_result, context):
        ea._personality = {"tone": "detailed", "language": "en", "name": "Aria"}
        result = await ea._synthesize_specialist_result(sample_result, context)
        # Detailed should include structured payload info
        assert "marketing" in result
        assert "Acme" in result.replace("Acme Corp", "Acme")  # from payload or summary

    @pytest.mark.asyncio
    async def test_four_tones_produce_different_outputs(self, ea, sample_result, context):
        outputs = {}
        for tone in ("professional", "friendly", "concise", "detailed"):
            ea._personality = {"tone": tone, "language": "en", "name": "Aria"}
            outputs[tone] = await ea._synthesize_specialist_result(sample_result, context)

        # At least 3 of the 4 must be distinct (professional/concise could overlap
        # for very short summaries, but friendly and detailed should always differ).
        unique = set(outputs.values())
        assert len(unique) >= 3, f"Expected >=3 distinct outputs, got {len(unique)}: {outputs}"

    @pytest.mark.asyncio
    async def test_unknown_tone_falls_back_to_professional(self, ea, sample_result, context):
        ea._personality = {"tone": "nonexistent", "language": "en", "name": "Aria"}
        result = await ea._synthesize_specialist_result(sample_result, context)
        # Should not crash — falls back to professional (as-is)
        assert result == sample_result.summary_for_ea

    @pytest.mark.asyncio
    async def test_no_summary_fallback_includes_payload(self, ea, context):
        """When summary_for_ea is None, the fallback must still work."""
        bare = SpecialistResult(
            status=SpecialistStatus.COMPLETED, domain="finance",
            payload={"amount": 42}, confidence=0.8,
            summary_for_ea=None,
        )
        ea._personality = {"tone": "professional", "language": "en", "name": "Aria"}
        result = await ea._synthesize_specialist_result(bare, context)
        assert "42" in result  # payload should be visible in fallback
