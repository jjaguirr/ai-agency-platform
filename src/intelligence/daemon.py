"""
Background sweep that enriches idle conversations with derived metadata.

Runs as a sibling task to the FastAPI request workers — same process,
same asyncpg pool, zero contention with the response path. The sweep
query (find_idle_unsummarized) uses a partial index on
`WHERE summary IS NULL` so processed conversations cost nothing on
subsequent ticks.

Failure handling matches HeartbeatDaemon: one broken conversation
doesn't abort the batch; one broken tick doesn't kill the loop. The
LLM being unavailable means summaries stay NULL and the conversation
reappears next sweep — that IS the retry mechanism.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .quality import compute_quality_flags, LONG_THRESHOLD_DEFAULT
from .tagging import tags_from_delegations

logger = logging.getLogger(__name__)


class IntelligenceDaemon:
    def __init__(
        self,
        *,
        intel_repo,
        conv_repo,
        summarizer,
        idle_minutes: int = 30,
        batch_limit: int = 100,
        tick_interval: float = 60.0,
        long_threshold: int = LONG_THRESHOLD_DEFAULT,
    ) -> None:
        self._intel_repo = intel_repo
        self._conv_repo = conv_repo
        self._summarizer = summarizer
        self._idle_minutes = idle_minutes
        self._batch_limit = batch_limit
        self._tick_interval = tick_interval
        self._long_threshold = long_threshold

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="intelligence-daemon")
        logger.info(
            "Intelligence daemon started (tick=%.0fs idle=%dm batch=%d)",
            self._tick_interval, self._idle_minutes, self._batch_limit,
        )

    async def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Intelligence daemon stopped")

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Intelligence tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._tick_interval,
                )
                break  # stop_event set
            except asyncio.TimeoutError:
                pass  # next tick

    async def _tick(self) -> None:
        idle = await self._intel_repo.find_idle_unsummarized(
            idle_minutes=self._idle_minutes,
            limit=self._batch_limit,
        )
        if not idle:
            return

        for conversation_id, customer_id in idle:
            try:
                await self._process_one(conversation_id, customer_id)
            except Exception:
                # Isolation: one bad conversation doesn't poison the
                # batch. It stays summary=NULL and comes back next tick
                # — if the cause was transient it'll go through then.
                logger.exception(
                    "Intelligence processing failed for customer=%s conv=%s",
                    customer_id, conversation_id,
                )

    async def _process_one(self, conversation_id: str, customer_id: str) -> None:
        messages = await self._conv_repo.get_messages(
            customer_id=customer_id,
            conversation_id=conversation_id,
        )
        if messages is None:
            # Conversation gone between sweep and fetch — nothing to do.
            return

        delegations = await self._intel_repo.get_delegation_statuses(
            customer_id=customer_id,
            conversation_id=conversation_id,
        )

        summary = await self._summarizer.summarize(messages)
        if summary is None:
            # LLM failed or empty transcript. Writing topics/flags
            # without a summary would satisfy the WHERE summary IS NULL
            # predicate's inverse — the row would fall out of the sweep
            # with no summary on it. Skipping keeps it in the queue.
            return

        domains = [d for d, _ in delegations]
        statuses = [s for _, s in delegations]

        await self._intel_repo.set_intelligence(
            customer_id=customer_id,
            conversation_id=conversation_id,
            summary=summary,
            topics=tags_from_delegations(domains),
            quality_flags=compute_quality_flags(
                messages,
                delegation_statuses=statuses,
                long_threshold=self._long_threshold,
            ),
        )
