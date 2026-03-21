"""
ConversationSummarizer — LLM-backed one-sentence summary.

The LLM is injected as a bare async callable (str → str). In production
that's a thin wrapper around ChatOpenAI.ainvoke; here it's a mock. What
we test: prompt construction, transcript truncation, and that an LLM
failure doesn't propagate (summarizer returns None, daemon moves on).
"""
import pytest
from unittest.mock import AsyncMock

from src.intelligence.summarizer import ConversationSummarizer, SUMMARY_MAX_CHARS


@pytest.fixture
def llm():
    return AsyncMock(return_value="Customer asked about invoices; finance specialist resolved it.")


@pytest.fixture
def summarizer(llm):
    return ConversationSummarizer(llm)


def _msgs(*pairs):
    """Helper: ("user", "hi"), ("assistant", "hello") → [{"role":..., "content":...}]"""
    return [{"role": r, "content": c} for r, c in pairs]


class TestSummarize:
    async def test_returns_llm_output(self, summarizer, llm):
        msgs = _msgs(("user", "check my invoices"), ("assistant", "3 outstanding"))
        out = await summarizer.summarize(msgs)
        assert out == "Customer asked about invoices; finance specialist resolved it."
        llm.assert_awaited_once()

    async def test_prompt_contains_transcript(self, summarizer, llm):
        msgs = _msgs(
            ("user", "schedule a call with acme"),
            ("assistant", "Done, booked for 3pm"),
        )
        await summarizer.summarize(msgs)
        prompt = llm.await_args.args[0]
        assert "schedule a call with acme" in prompt
        assert "booked for 3pm" in prompt
        # Role labels so the LLM knows who said what
        assert "user:" in prompt.lower()
        assert "assistant:" in prompt.lower()

    async def test_prompt_asks_for_one_sentence(self, summarizer, llm):
        await summarizer.summarize(_msgs(("user", "hi")))
        prompt = llm.await_args.args[0]
        # The instruction must be in there — exact phrasing flexible.
        assert "one sentence" in prompt.lower() or "one-sentence" in prompt.lower()

    async def test_prompt_mentions_outcome_and_followups(self, summarizer, llm):
        # Task spec: "Note the topic, outcome, and any follow-ups."
        await summarizer.summarize(_msgs(("user", "hi")))
        prompt = llm.await_args.args[0].lower()
        assert "outcome" in prompt
        assert "follow" in prompt  # follow-up / follow-ups / followup

    async def test_empty_messages_no_llm_call(self, summarizer, llm):
        out = await summarizer.summarize([])
        assert out is None
        llm.assert_not_awaited()

    async def test_llm_exception_returns_none(self, llm):
        llm.side_effect = RuntimeError("rate limited")
        s = ConversationSummarizer(llm)
        out = await s.summarize(_msgs(("user", "hi"), ("assistant", "hello")))
        # Swallowed — the daemon will retry on the next sweep. A raised
        # exception here would abort the whole batch.
        assert out is None

    async def test_long_transcript_truncated(self, llm):
        # 200 turns of chatter. The prompt must stay bounded — we don't
        # want a 100k-token summarization request for a long conversation.
        s = ConversationSummarizer(llm, max_transcript_chars=500)
        msgs = _msgs(*[("user", "message " * 20)] * 200)
        await s.summarize(msgs)
        prompt = llm.await_args.args[0]
        # Some overhead for the instruction wrapper; transcript portion bounded.
        assert len(prompt) < 500 + 1000

    async def test_truncation_keeps_tail(self, llm):
        # Recent turns matter more than the opener — the outcome is at
        # the end. First message dropped, last preserved.
        s = ConversationSummarizer(llm, max_transcript_chars=200)
        msgs = _msgs(
            ("user", "FIRST_MESSAGE " * 20),
            ("assistant", "middle " * 20),
            ("user", "LAST_MESSAGE"),
        )
        await s.summarize(msgs)
        prompt = llm.await_args.args[0]
        assert "LAST_MESSAGE" in prompt
        assert "FIRST_MESSAGE" not in prompt

    async def test_output_clamped(self, llm):
        # LLM ignores the instruction and returns an essay. Clamp it
        # so the list view doesn't blow up.
        llm.return_value = "word " * 1000
        s = ConversationSummarizer(llm)
        out = await s.summarize(_msgs(("user", "hi"), ("assistant", "hello")))
        assert out is not None
        assert len(out) <= SUMMARY_MAX_CHARS

    async def test_output_stripped(self, llm):
        llm.return_value = "  \n  summary with whitespace  \n  "
        s = ConversationSummarizer(llm)
        out = await s.summarize(_msgs(("user", "hi")))
        assert out == "summary with whitespace"

    async def test_empty_llm_output_returns_none(self, llm):
        # Rather an empty summary slot (daemon retries) than storing "".
        llm.return_value = "   "
        s = ConversationSummarizer(llm)
        out = await s.summarize(_msgs(("user", "hi")))
        assert out is None
