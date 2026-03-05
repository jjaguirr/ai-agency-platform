"""
Specialist agent contract.

Specialists are domain workers invoked by the Executive Assistant. They never
talk to customers directly — the EA builds a SpecialistTask, awaits execute(),
and weaves the SpecialistResult into its own conversational response.

The contract is deliberately narrow:
  - can_handle() is a cheap synchronous scorer for routing
  - execute() is the only async work surface
  - no access to raw message history; context arrives pre-scoped
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# BusinessContext lives in executive_assistant; import lazily to avoid
# a hard cycle (EA imports specialists, specialists reference BusinessContext).
# The dataclass field is typed as Any at runtime — tests import the real thing.


class DelegationStatus(Enum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"


@dataclass
class SpecialistTask:
    """Everything a specialist needs to do its job — and nothing more.

    Notably absent: raw conversation messages. The EA keeps full history;
    specialists see only the task description, the customer's business
    context, and memory entries pre-filtered to the specialist's declared
    categories. This is the context-scoping boundary.
    """
    task_description: str
    customer_id: str
    conversation_id: str
    business_context: Any  # BusinessContext — typed loosely to avoid import cycle
    domain_memories: list[dict]
    prior_clarifications: dict[str, str] = field(default_factory=dict)


@dataclass
class SpecialistResult:
    """What a specialist hands back to the EA.

    status drives the EA's next move:
      COMPLETED            → EA reformulates content+structured_data in its voice
      NEEDS_CLARIFICATION  → EA asks the customer, persists delegation state
      FAILED               → EA falls back to generalist handling

    confidence gives the EA a second chance to override: even a COMPLETED
    result with confidence < 0.4 triggers fallback.
    """
    status: DelegationStatus
    content: Optional[str] = None
    confidence: float = 0.0
    clarification_question: Optional[str] = None
    structured_data: Optional[dict] = None
    error: Optional[str] = None


class SpecialistAgent(ABC):
    """Base for all domain specialists.

    Subclasses declare:
      domain            — unique key for the registry ("social_media", "finance")
      memory_categories — metadata categories this specialist may read; the EA
                          filters memory search results to these before building
                          the SpecialistTask

    The EA injects its own LLM client so specialists share config and quota.
    """
    domain: str
    memory_categories: list[str]

    def __init__(self, llm: Any = None):
        self.llm = llm

    @abstractmethod
    def can_handle(self, task_description: str, intent: Any) -> float:
        """Cheap synchronous domain match. Return 0.0–1.0.

        Called on every registered specialist during delegation_decision.
        Should be fast — keyword scoring, not LLM calls. The EA picks the
        highest scorer above 0.5.
        """
        ...

    @abstractmethod
    async def execute(self, task: SpecialistTask) -> SpecialistResult:
        """Do the actual work.

        The EA wraps this in asyncio.wait_for with a timeout, so
        implementations should not implement their own hang detection.
        Raising an exception is equivalent to returning FAILED.
        """
        ...
