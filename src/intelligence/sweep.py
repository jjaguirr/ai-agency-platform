"""Background intelligence sweep — runs inside the heartbeat tick cycle.

Finds idle conversations without summaries, generates LLM summaries,
computes quality signals, and derives topic tags. Processes a limited
batch per sweep to avoid starving the main heartbeat behaviors.
"""
from __future__ import annotations

import logging

from .config import IntelligenceConfig

logger = logging.getLogger(__name__)


class IntelligenceSweep:

    def __init__(
        self,
        *,
        conversation_repo,
        delegation_recorder,
        summarizer,
        quality_analyzer,
        config: IntelligenceConfig,
    ):
        self._repo = conversation_repo
        self._recorder = delegation_recorder
        self._summarizer = summarizer
        self._quality = quality_analyzer
        self._config = config

    async def run(self) -> int:
        """Execute one sweep pass. Returns number of conversations attempted."""
        conversations = await self._repo.get_conversations_needing_summary(
            idle_threshold_minutes=self._config.summary_idle_threshold_minutes,
            limit=self._config.sweep_batch_size,
        )

        for conv in conversations:
            try:
                await self._process(conv)
            except Exception:
                logger.exception(
                    "Intelligence sweep failed for conv=%s", conv["id"],
                )

        return len(conversations)

    async def _process(self, conv: dict) -> None:
        conv_id = conv["id"]
        cust_id = conv["customer_id"]

        # Fetch messages (using customer_id for tenant isolation)
        messages = await self._repo.get_messages(
            customer_id=cust_id, conversation_id=conv_id,
        )
        if messages is None:
            return

        # Generate summary
        summary = await self._summarizer.summarize(messages)
        if summary:
            await self._repo.set_summary(
                conversation_id=conv_id, summary=summary,
            )

        # Derive topic tags from delegation records
        await self._recorder.update_tags_from_delegations(
            customer_id=cust_id, conversation_id=conv_id,
        )

        # Compute quality signals
        delegation_statuses = await self._recorder.get_delegation_statuses(
            conversation_id=conv_id, customer_id=cust_id,
        )
        signals = self._quality.analyze(
            messages=messages,
            delegation_statuses=delegation_statuses,
        )
        await self._repo.set_quality_signals(
            conversation_id=conv_id, signals=signals.to_dict(),
        )
