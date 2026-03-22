"""
Unit tests for personality-aware response synthesis.

The EA owns final phrasing (specialists return structured results), so
tone injection happens in _synthesize_specialist_result. All four tones
must produce meaningfully different prose from the same SpecialistResult.

These tests run the LLM-free path (ea.llm = None), which is the one we
can deterministically assert on. The LLM path gets tone guidance in the
prompt but its output is non-deterministic — covered by evaluation tests
elsewhere, not here.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

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
            business_name="Acme Co",
        ))
        mem.search_business_knowledge = AsyncMock(return_value=[])

        inst = ExecutiveAssistant(customer_id="test_cust")
        inst.llm = None
        yield inst


@pytest.fixture
def scheduling_result():
    """A completed scheduling result — the canonical 'meeting booked'
    case used in the task spec's tone examples."""
    return SpecialistResult(
        status=SpecialistStatus.COMPLETED,
        domain="scheduling",
        payload={
            "event_id": "evt_1",
            "title": "Strategy sync",
            "start": "2026-03-22T15:00:00",
            "end": "2026-03-22T15:30:00",
        },
        confidence=0.85,
        summary_for_ea="Booked: Strategy sync on 2026-03-22 15:00 for 30m.",
    )


@pytest.fixture
def ctx():
    from src.agents.executive_assistant import BusinessContext
    return BusinessContext(business_name="Acme Co")


# --- Tone differentiation ---------------------------------------------------

class TestToneDifferentiation:
    @pytest.mark.asyncio
    async def test_all_four_tones_produce_different_output(
        self, ea, scheduling_result, ctx
    ):
        outputs = {}
        for tone in ("professional", "friendly", "concise", "detailed"):
            ea._personality = {"tone": tone, "language": "en", "name": "Aria"}
            outputs[tone] = await ea._synthesize_specialist_result(
                scheduling_result, ctx
            )

        # Four distinct strings.
        assert len(set(outputs.values())) == 4, (
            f"tones collapsed: {outputs}"
        )

    @pytest.mark.asyncio
    async def test_concise_is_shortest(self, ea, scheduling_result, ctx):
        lengths = {}
        for tone in ("professional", "friendly", "concise", "detailed"):
            ea._personality = {"tone": tone, "language": "en", "name": "Aria"}
            out = await ea._synthesize_specialist_result(scheduling_result, ctx)
            lengths[tone] = len(out)

        assert lengths["concise"] == min(lengths.values())
        assert lengths["detailed"] == max(lengths.values())

    @pytest.mark.asyncio
    async def test_friendly_has_casual_markers(
        self, ea, scheduling_result, ctx
    ):
        ea._personality = {"tone": "friendly", "language": "en", "name": "Aria"}
        out = await ea._synthesize_specialist_result(scheduling_result, ctx)
        # Exclamation or casual opener — spec example: "All set!"
        assert any(m in out for m in ("!", "All set", "Got it", "Done —"))

    @pytest.mark.asyncio
    async def test_professional_has_no_exclamation(
        self, ea, scheduling_result, ctx
    ):
        ea._personality = {"tone": "professional", "language": "en", "name": "Aria"}
        out = await ea._synthesize_specialist_result(scheduling_result, ctx)
        assert "!" not in out

    @pytest.mark.asyncio
    async def test_detailed_includes_payload_context(
        self, ea, scheduling_result, ctx
    ):
        """Detailed tone surfaces extra data the other tones omit —
        e.g. the end time, which implies duration."""
        ea._personality = {"tone": "detailed", "language": "en", "name": "Aria"}
        detailed = await ea._synthesize_specialist_result(scheduling_result, ctx)

        ea._personality = {"tone": "professional", "language": "en", "name": "Aria"}
        prof = await ea._synthesize_specialist_result(scheduling_result, ctx)

        # The end time (15:30) is only in payload, not summary_for_ea —
        # detailed must surface it, professional must not. Previous
        # assertion also accepted "Strategy sync", which is already in
        # the base summary and so passed for every tone.
        assert "15:30" in detailed
        assert "15:30" not in prof


# --- Fallback behaviour -----------------------------------------------------

class TestFallback:
    @pytest.mark.asyncio
    async def test_unknown_tone_falls_back_to_professional(
        self, ea, scheduling_result, ctx
    ):
        ea._personality = {"tone": "sarcastic", "language": "en", "name": "Aria"}
        out = await ea._synthesize_specialist_result(scheduling_result, ctx)
        # Should not crash, should produce something.
        assert out
        assert "!" not in out  # professional fallback, not friendly

    @pytest.mark.asyncio
    async def test_no_summary_still_produces_prose(self, ea, ctx):
        """A specialist that only returns payload (no summary_for_ea)
        should still get a toned response."""
        bare = SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain="finance",
            payload={"amount": 500.0, "vendor": "Shopify"},
            confidence=0.8,
        )
        ea._personality = {"tone": "concise", "language": "en", "name": "Aria"}
        out = await ea._synthesize_specialist_result(bare, ctx)
        assert out
        assert "500" in out or "Shopify" in out


# --- LLM path gets tone guidance --------------------------------------------

class TestLLMPromptIncludesTone:
    @pytest.mark.asyncio
    async def test_tone_guidance_injected_into_prompt(
        self, ea, scheduling_result, ctx
    ):
        fake_llm = AsyncMock()
        fake_llm.ainvoke = AsyncMock(
            return_value=type("R", (), {"content": "ok"})()
        )
        ea.llm = fake_llm
        ea._personality = {"tone": "concise", "language": "en", "name": "Aria"}

        await ea._synthesize_specialist_result(scheduling_result, ctx)

        prompt = fake_llm.ainvoke.call_args[0][0][0].content
        # Assert on the guidance *text*, not the tone label — a prompt
        # that said only "Tone: concise" with no instruction would
        # otherwise pass.
        from src.agents.tone import guidance
        assert guidance("concise") in prompt
