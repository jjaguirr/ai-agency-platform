"""
Specialist agent protocol and delegation registry.

Contract between the EA (orchestrator) and domain specialists. Specialists
never see ConversationState, raw message history, or the memory client — they
receive a SpecialistTask with pre-fetched, domain-scoped context. Routing is
specialist self-assessment (no LLM on the hot path); the registry gates on
confidence AND a strategic-vs-operational flag.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.context import InteractionContext
    from src.agents.executive_assistant import BusinessContext
    from src.proactive.triggers import ProactiveTrigger

# ActionRisk lives in safety.models (single source of truth for the
# serialized enum values) but specialists are where it's set, so
# re-export it here so specialist code imports from one place.
from src.safety.models import ActionRisk  # noqa: F401

logger = logging.getLogger(__name__)


# --- Data types -------------------------------------------------------------

class SpecialistStatus(Enum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_CONFIRMATION = "needs_confirmation"
    FAILED = "failed"


@dataclass
class TaskAssessment:
    """A specialist's self-assessment of whether it should handle a task.

    confidence: how sure the specialist is that this task is in its domain.
    is_strategic: True means "this IS my domain but it needs business-level
      judgment — the EA should keep it." Example: "should I invest more in
      Instagram ads" is social-media domain but advisory, not operational.
    """
    confidence: float
    is_strategic: bool = False

    def __post_init__(self):
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class SpecialistTask:
    """What the EA hands to a specialist.

    domain_memories are pre-fetched by the EA — the specialist never gets
    direct memory-client access. prior_turns carries clarification Q&A on
    multi-turn delegations without exposing the full conversation.
    interaction_context is the cross-domain snapshot assembled by
    ContextAssembler — None when the assembler is not wired.
    """
    description: str
    customer_id: str
    business_context: "BusinessContext"
    domain_memories: List[Dict[str, Any]]
    prior_turns: List[Dict[str, str]] = field(default_factory=list)
    interaction_context: Optional["InteractionContext"] = None


@dataclass
class SpecialistResult:
    """What a specialist hands back to the EA.

    payload is the structured domain data (engagement rates, invoice totals,
    whatever). summary_for_ea is an optional hint the specialist can provide
    to help the EA phrase the response naturally — but the EA owns the final
    wording, so this is advisory.
    """
    status: SpecialistStatus
    domain: str
    payload: Dict[str, Any]
    confidence: float
    summary_for_ea: Optional[str] = None
    clarification_question: Optional[str] = None
    error: Optional[str] = None
    # Confirmation fields: set when status is NEEDS_CONFIRMATION. payload
    # carries whatever the specialist needs to execute on the confirmed
    # follow-up (event IDs, resolved targets) so it doesn't re-resolve.
    confirmation_prompt: Optional[str] = None
    action_risk: Optional[ActionRisk] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "domain": self.domain,
            "payload": self.payload,
            "confidence": self.confidence,
            "summary_for_ea": self.summary_for_ea,
            "clarification_question": self.clarification_question,
            "error": self.error,
            "confirmation_prompt": self.confirmation_prompt,
            "action_risk": self.action_risk.value if self.action_risk else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SpecialistResult":
        return cls(
            status=SpecialistStatus(d["status"]),
            domain=d["domain"],
            payload=d.get("payload", {}),
            confidence=d.get("confidence", 0.0),
            summary_for_ea=d.get("summary_for_ea"),
            clarification_question=d.get("clarification_question"),
            error=d.get("error"),
            confirmation_prompt=d.get("confirmation_prompt"),
            action_risk=ActionRisk(d["action_risk"]) if d.get("action_risk") else None,
        )


# --- Specialist ABC ---------------------------------------------------------

class SpecialistAgent(ABC):
    """Base class every domain specialist implements.

    Two methods matter:
    - assess_task: synchronous, cheap. Called during routing to decide if
      this specialist should get the task. No I/O.
    - execute_task: async, does the actual work. May take seconds. Always
      called through DelegationRegistry.execute() which wraps it in
      timeout + exception handling.
    """

    @property
    @abstractmethod
    def domain(self) -> str:
        """Stable identifier: 'social_media', 'finance', etc."""

    @abstractmethod
    def assess_task(self, task_description: str, context: "BusinessContext") -> TaskAssessment:
        """Cheap, synchronous self-assessment. No I/O, no LLM calls."""

    @abstractmethod
    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        """Do the work. May raise — the registry catches and converts to FAILED."""

    async def proactive_check(
        self, customer_id: str, context: "BusinessContext"
    ) -> Optional["ProactiveTrigger"]:
        """Optional proactive check — override to generate triggers on each heartbeat tick.

        Returns None by default. Specialists that implement proactive behavior
        (e.g., anomaly detection, periodic reports) override this. The heartbeat
        daemon calls it for every active customer on each tick.
        """
        return None


# --- Registry ---------------------------------------------------------------

@dataclass
class DelegationMatch:
    specialist: SpecialistAgent
    assessment: TaskAssessment


class DelegationRegistry:
    """Routes tasks to specialists.

    Strategic assessments are filtered out before ranking — highest-confidence
    non-strategic specialist above threshold wins.
    """

    def __init__(self, confidence_threshold: float = 0.6):
        self._specialists: Dict[str, SpecialistAgent] = {}
        self.confidence_threshold = confidence_threshold

    def register(self, specialist: SpecialistAgent) -> None:
        self._specialists[specialist.domain] = specialist
        logger.info(f"Registered specialist: {specialist.domain}")

    def get(self, domain: str) -> Optional[SpecialistAgent]:
        return self._specialists.get(domain)

    def route(self, task_description: str, context: "BusinessContext") -> Optional[DelegationMatch]:
        """Find the best specialist for this task, or None if EA should handle it."""
        if not self._specialists:
            return None

        candidates = []
        for spec in self._specialists.values():
            assessment = spec.assess_task(task_description, context)
            if assessment.is_strategic:
                logger.debug(
                    f"{spec.domain} flagged task as strategic (conf={assessment.confidence:.2f}) — EA keeps it"
                )
                continue
            if assessment.confidence >= self.confidence_threshold:
                candidates.append(DelegationMatch(spec, assessment))

        if not candidates:
            return None

        return max(candidates, key=lambda m: m.assessment.confidence)

    async def execute(
        self,
        specialist: SpecialistAgent,
        task: SpecialistTask,
        timeout: float,
    ) -> SpecialistResult:
        """Run a specialist under timeout + exception guard.

        Never raises. Hung → FAILED with timeout message. Crashed → FAILED
        with the exception message. The EA treats FAILED as "fall back to my
        own handling."
        """
        try:
            return await asyncio.wait_for(specialist.execute_task(task), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Specialist {specialist.domain} timed out after {timeout}s for customer {task.customer_id}"
            )
            return SpecialistResult(
                status=SpecialistStatus.FAILED,
                domain=specialist.domain,
                payload={},
                confidence=0.0,
                error=f"timeout after {timeout}s",
            )
        except Exception as e:
            logger.error(
                f"Specialist {specialist.domain} crashed for customer {task.customer_id}: {e}"
            )
            return SpecialistResult(
                status=SpecialistStatus.FAILED,
                domain=specialist.domain,
                payload={},
                confidence=0.0,
                error=str(e),
            )
