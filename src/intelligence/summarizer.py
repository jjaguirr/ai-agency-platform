"""
LLM-backed conversation summarizer.

Runs in the background sweep, never on the response path. The LLM is
injected as a plain async callable so tests don't need to know about
langchain, and production can swap models without touching this module.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional, Sequence

logger = logging.getLogger(__name__)

# Hard cap on what we store. The list view renders this inline; two
# sentences of English is ~300 chars. If the LLM ignores the one-sentence
# instruction we clamp rather than reject.
SUMMARY_MAX_CHARS = 500

# Default transcript budget. gpt-4o handles far more but a conversation
# that long is an outlier; the tail carries the outcome.
_DEFAULT_MAX_TRANSCRIPT_CHARS = 8000

_PROMPT = (
    "Summarize this customer conversation in one sentence. "
    "Note the topic, the outcome, and any follow-ups mentioned.\n\n"
    "{transcript}"
)

LLMCallable = Callable[[str], Awaitable[str]]


class ConversationSummarizer:
    def __init__(
        self,
        llm: LLMCallable,
        *,
        max_transcript_chars: int = _DEFAULT_MAX_TRANSCRIPT_CHARS,
    ):
        self._llm = llm
        self._max_transcript_chars = max_transcript_chars

    async def summarize(self, messages: Sequence[dict]) -> Optional[str]:
        if not messages:
            return None

        transcript = self._render(messages)
        prompt = _PROMPT.format(transcript=transcript)

        try:
            raw = await self._llm(prompt)
        except Exception as e:
            # Non-fatal: the conversation keeps summary=NULL and the
            # next sweep picks it up again. Logging at warning because
            # a persistent failure here (bad key, quota) is worth a look.
            logger.warning("Summarizer LLM call failed: %s", e)
            return None

        out = (raw or "").strip()
        if not out:
            return None
        return out[:SUMMARY_MAX_CHARS]

    def _render(self, messages: Sequence[dict]) -> str:
        """Render messages tail-first until the char budget is hit.

        Walking backwards means we keep the most recent exchange (where
        the outcome lives) and drop the greeting. Reversed on return so
        the LLM sees chronological order.
        """
        lines: list[str] = []
        budget = self._max_transcript_chars
        for m in reversed(messages):
            role = m.get("role", "?")
            content = m.get("content") or ""
            line = f"{role}: {content}"
            if len(line) > budget:
                break
            lines.append(line)
            budget -= len(line) + 1  # +1 for the newline join
        return "\n".join(reversed(lines))
