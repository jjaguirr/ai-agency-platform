"""Redis-backed onboarding state machine.

Key: ``onboarding:{customer_id}`` → JSON blob tracking the multi-step
onboarding conversation.  Mirrors the ProactiveStateStore pattern.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

NUM_STEPS = 5


@dataclass
class OnboardingState:
    status: str = "not_started"
    current_step: int = 0
    collected: dict = field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    interrupted: bool = False


class OnboardingStateStore:
    """Redis-backed onboarding state, one key per customer."""

    def __init__(self, redis_client) -> None:
        self._r = redis_client

    def _key(self, customer_id: str) -> str:
        return f"onboarding:{customer_id}"

    async def get(self, customer_id: str) -> Optional[OnboardingState]:
        raw = await self._r.get(self._key(customer_id))
        if raw is None:
            return None
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        data = json.loads(decoded)
        return OnboardingState(**data)

    async def get_status(self, customer_id: str) -> str:
        raw = await self._r.get(self._key(customer_id))
        if raw is None:
            return "unknown"
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        data = json.loads(decoded)
        return data.get("status", "unknown")

    async def _save(self, customer_id: str, state: OnboardingState) -> None:
        await self._r.set(self._key(customer_id), json.dumps(asdict(state)))

    async def initialize(self, customer_id: str) -> None:
        await self._save(customer_id, OnboardingState())

    async def advance(
        self, customer_id: str, collected_data: Optional[dict] = None,
    ) -> OnboardingState:
        state = await self.get(customer_id)
        if state is None:
            state = OnboardingState()

        if state.status == "not_started":
            state.status = "in_progress"
            state.started_at = datetime.now(timezone.utc).isoformat()

        if collected_data:
            state.collected.update(collected_data)

        state.current_step += 1

        if state.current_step >= NUM_STEPS:
            state.status = "completed"
            state.completed_at = datetime.now(timezone.utc).isoformat()

        await self._save(customer_id, state)
        return state

    async def mark_completed(self, customer_id: str) -> None:
        state = await self.get(customer_id)
        if state is None:
            state = OnboardingState()
        state.status = "completed"
        if state.completed_at is None:
            state.completed_at = datetime.now(timezone.utc).isoformat()
        await self._save(customer_id, state)

    async def mark_interrupted(self, customer_id: str) -> None:
        state = await self.get(customer_id)
        if state is None:
            return
        state.interrupted = True
        await self._save(customer_id, state)
