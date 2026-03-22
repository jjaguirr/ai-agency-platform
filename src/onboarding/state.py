"""
Onboarding state — Redis-backed per-customer wizard progress.

Key: ``onboarding:{customer_id}`` → JSON {status, step, collected}

State machine: not_started → in_progress → completed. The EA checks
``is_complete`` at the top of every interaction; anything other than
completed routes to the onboarding flow instead of normal delegation.

Step tracking lets a customer who drops off mid-flow resume where they
left off. ``collected`` is a scratch dict the flow uses to stash
answers (business context, timezone) before writing them to their
final homes (settings, customer metadata).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class OnboardingStep(str, Enum):
    INTRO = "intro"
    BUSINESS_CONTEXT = "business_context"
    PREFERENCES = "preferences"
    QUICK_WIN = "quick_win"
    DONE = "done"


@dataclass
class OnboardingState:
    status: str = "not_started"      # not_started | in_progress | completed
    step: OnboardingStep = OnboardingStep.INTRO
    collected: Dict[str, Any] = field(default_factory=dict)


def _key(customer_id: str) -> str:
    return f"onboarding:{customer_id}"


class OnboardingStateStore:
    def __init__(self, redis_client) -> None:
        self._r = redis_client

    async def get(self, customer_id: str) -> OnboardingState:
        raw = await self._r.get(_key(customer_id))
        if raw is None:
            return OnboardingState()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return OnboardingState(
            status=data.get("status", "not_started"),
            step=OnboardingStep(data.get("step", OnboardingStep.INTRO.value)),
            collected=data.get("collected", {}),
        )

    async def initialize(self, customer_id: str) -> None:
        """Seed not_started state. Idempotent — never resets a customer
        who has already progressed or completed."""
        existing = await self.get(customer_id)
        if existing.status != "not_started":
            return
        await self._write(customer_id, OnboardingState())

    async def advance(
        self,
        customer_id: str,
        step: OnboardingStep,
        *,
        collected: Dict[str, Any] | None = None,
    ) -> None:
        state = await self.get(customer_id)
        state.status = "in_progress"
        state.step = step
        if collected:
            state.collected.update(collected)
        await self._write(customer_id, state)

    async def complete(self, customer_id: str) -> None:
        state = await self.get(customer_id)
        state.status = "completed"
        state.step = OnboardingStep.DONE
        await self._write(customer_id, state)

    async def is_complete(self, customer_id: str) -> bool:
        return (await self.get(customer_id)).status == "completed"

    async def _write(self, customer_id: str, state: OnboardingState) -> None:
        await self._r.set(
            _key(customer_id),
            json.dumps({
                "status": state.status,
                "step": state.step.value,
                "collected": state.collected,
            }),
        )
