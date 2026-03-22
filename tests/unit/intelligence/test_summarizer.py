"""Tests for ConversationSummarizer — LLM-powered summary generation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.intelligence.summarizer import ConversationSummarizer


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    response = MagicMock()
    response.content = "Customer asked about invoices. Finance specialist resolved it."
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


class TestSummarize:
    async def test_returns_llm_generated_summary(self, mock_llm):
        summarizer = ConversationSummarizer(llm=mock_llm)
        messages = [
            {"role": "user", "content": "Can you check my invoices?"},
            {"role": "assistant", "content": "I found 3 unpaid invoices."},
        ]

        result = await summarizer.summarize(messages)

        assert result == "Customer asked about invoices. Finance specialist resolved it."
        mock_llm.ainvoke.assert_awaited_once()

    async def test_prompt_includes_message_content(self, mock_llm):
        summarizer = ConversationSummarizer(llm=mock_llm)
        messages = [
            {"role": "user", "content": "Schedule a meeting with Alice"},
        ]

        await summarizer.summarize(messages)

        call_args = mock_llm.ainvoke.await_args[0][0]
        prompt_text = call_args[0].content  # SystemMessage
        assert "summarize" in prompt_text.lower() or "summary" in prompt_text.lower()
        # The human message should contain the conversation
        human_text = call_args[1].content  # HumanMessage
        assert "Schedule a meeting with Alice" in human_text

    async def test_truncates_long_conversations(self, mock_llm):
        summarizer = ConversationSummarizer(llm=mock_llm, max_messages=3)
        messages = [
            {"role": "user", "content": f"Message {i}"} for i in range(10)
        ]

        await summarizer.summarize(messages)

        human_text = mock_llm.ainvoke.await_args[0][0][1].content
        # Should only contain last 3 messages
        assert "Message 7" in human_text
        assert "Message 9" in human_text
        assert "Message 0" not in human_text

    async def test_empty_messages_returns_fallback(self, mock_llm):
        summarizer = ConversationSummarizer(llm=mock_llm)

        result = await summarizer.summarize([])

        assert result == ""
        mock_llm.ainvoke.assert_not_awaited()

    async def test_llm_failure_returns_empty_string(self):
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(side_effect=RuntimeError("API down"))
        summarizer = ConversationSummarizer(llm=llm)
        messages = [{"role": "user", "content": "hello"}]

        result = await summarizer.summarize(messages)

        assert result == ""
