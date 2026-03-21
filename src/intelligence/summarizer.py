"""LLM-powered conversation summarization.

Called by the intelligence sweep, never on the request path.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Summarize this business conversation in one to two sentences. "
    "Note the topic, which specialist handled it (if any), "
    "whether the request was resolved, and any follow-up items mentioned. "
    "Be concise — this summary will appear in a list view."
)


class ConversationSummarizer:

    def __init__(self, *, llm: Any, max_messages: int = 50):
        self._llm = llm
        self._max_messages = max_messages

    async def summarize(self, messages: list[dict[str, str]]) -> str:
        """Generate a one-line summary from conversation messages.

        Returns empty string on empty input or LLM failure.
        """
        if not messages:
            return ""

        # Truncate to last N messages to cap token usage.
        truncated = messages[-self._max_messages:]
        transcript = "\n".join(
            f"{m['role']}: {m['content']}" for m in truncated
        )

        try:
            response = await self._llm.ainvoke([
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=transcript),
            ])
            return response.content
        except Exception:
            logger.exception("Summarization LLM call failed")
            return ""
