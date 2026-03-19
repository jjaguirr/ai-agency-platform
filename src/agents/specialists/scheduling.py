"""
Scheduling specialist agent.

Third specialist in the delegation framework. Handles calendar management
— daily overviews, event creation, rescheduling, cancellation, availability
checks, and slot finding — all through a CalendarClient seam. No hardcoded
Google or Outlook dependency.

Routing overlap with social_media and finance is action-type based:
"schedule a meeting" is scheduling, "schedule a post" is social media,
"schedule a payment" is finance. The signal is the action noun (meeting,
post, payment), not the verb "schedule".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

from src.agents.base.specialist import (
    SpecialistAgent,
    SpecialistResult,
    SpecialistStatus,
    SpecialistTask,
    TaskAssessment,
)

if TYPE_CHECKING:
    from src.agents.executive_assistant import BusinessContext

logger = logging.getLogger(__name__)


# --- Domain types -----------------------------------------------------------

@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: List[str]
    location: Optional[str] = None


@dataclass
class TimeSlot:
    start: datetime
    end: datetime


# --- External seam ----------------------------------------------------------

class CalendarClient(Protocol):
    """Contract for calendar providers. The specialist depends on this,
    never on a transport library. Concrete clients (GoogleCalendarClient,
    etc.) live outside this module and conform by structure — no inheritance.

    Contract: never raise. Transport/auth failures return empty lists,
    False, or empty results. Unknown event IDs return False from
    delete_event. The specialist treats missing data as degradation,
    not error."""

    async def list_events(self, start: datetime, end: datetime) -> List[CalendarEvent]: ...
    async def create_event(self, title: str, start: datetime, end: datetime,
                           attendees: List[str],
                           location: Optional[str] = None) -> CalendarEvent: ...
    async def update_event(self, event_id: str, **kwargs: Any) -> CalendarEvent: ...
    async def delete_event(self, event_id: str) -> bool: ...
    async def is_free(self, start: datetime, end: datetime) -> bool: ...
    async def find_available_slots(self, start: datetime, end: datetime,
                                   duration_minutes: int) -> List[TimeSlot]: ...


class SchedulingSpecialist(SpecialistAgent):

    def __init__(self, calendar_client: Optional[CalendarClient] = None):
        self._calendar_client = calendar_client

    @property
    def domain(self) -> str:
        return "scheduling"

    def assess_task(self, task_description: str, context: "BusinessContext") -> TaskAssessment:
        return TaskAssessment(confidence=0.0)

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        return SpecialistResult(
            status=SpecialistStatus.FAILED,
            domain=self.domain,
            payload={},
            confidence=0.0,
            error="Not implemented",
        )
