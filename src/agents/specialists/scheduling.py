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


# --- Assessment vocabulary --------------------------------------------------

_UNAMBIGUOUS_PHRASES = [
    "my calendar", "my schedule", "my meetings", "my appointments",
    "book a meeting", "cancel the meeting", "reschedule",
    "daily agenda",
]
_STRONG_PHRASES = [
    "meeting with", "appointment with", "free at", "available at",
    "conflict at", "what's on my", "block time", "move the",
    "push back", "what meetings", "a meeting", "planning meeting",
]
_WEAK_PHRASES = [
    "calendar", "meeting", "appointment", "busy", "free", "slot",
    "standup", "focus time",
]

_STRATEGIC_PATTERNS = [
    r"\bshould i\b",
    r"\bis it worth\b",
    r"\bworth it\b",
    r"\bdoes .+ make sense\b",
    r"\bhow many meetings should\b",
    r"\btoo many meetings\b",
]

_CALENDAR_TOOLS = {
    "Google Calendar", "Outlook", "Calendly", "Cal.com",
    "Apple Calendar", "Fantastical",
}


class SchedulingSpecialist(SpecialistAgent):

    def __init__(self, calendar_client: Optional[CalendarClient] = None):
        self._calendar_client = calendar_client

    @property
    def domain(self) -> str:
        return "scheduling"

    def assess_task(self, task_description: str, context: "BusinessContext") -> TaskAssessment:
        text = task_description.lower()

        confidence = 0.0

        # Unambiguous phrases — one hit is enough to route.
        for phrase in _UNAMBIGUOUS_PHRASES:
            if phrase in text:
                confidence += 0.6
                break

        # Strong scheduling signals
        for phrase in _STRONG_PHRASES:
            if phrase in text:
                confidence += 0.35

        # Weak signals — capped so "calendar + meeting + busy" doesn't
        # stack into a false positive. Follows finance.py pattern.
        weak_hits = sum(1 for p in _WEAK_PHRASES if p in text)
        confidence += min(0.25, weak_hits * 0.15)

        # Context boost — only if there's some lexical signal already.
        if confidence > 0:
            tools = set(context.current_tools or [])
            if tools & _CALENDAR_TOOLS:
                confidence += 0.2
            pain_points = [p.lower() for p in (context.pain_points or [])]
            if any(any(k in pp for k in ["schedul", "calendar", "meeting"])
                   for pp in pain_points):
                confidence += 0.15

        confidence = min(0.9, confidence)

        # Strategic gate — same pattern as social media and finance.
        is_strategic = False
        if confidence >= 0.4:
            is_strategic = any(re.search(p, text) for p in _STRATEGIC_PATTERNS)

        return TaskAssessment(confidence=confidence, is_strategic=is_strategic)

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        if self._calendar_client is None:
            return SpecialistResult(
                status=SpecialistStatus.FAILED,
                domain=self.domain,
                payload={},
                confidence=0.0,
                error="No calendar service connected. Calendar operations are unavailable.",
            )

        text = task.description.lower()

        # Intent routing — order matters (see spec).
        if self._is_daily_overview(text):
            return await self._handle_daily_overview(task)
        if self._is_find_slots(text):
            return await self._handle_find_slots(task)
        if self._is_availability_check(text):
            return await self._handle_availability(task)
        if self._is_reschedule(text):
            return await self._handle_reschedule(task)
        if self._is_cancel(text):
            return await self._handle_cancel(task)
        return await self._handle_create_event(task)

    # --- Shared helpers -------------------------------------------------------

    def _customer_corpus(self, task: SpecialistTask) -> str:
        """Concatenate current message + prior customer turns for multi-turn
        extraction. Specialist turns are excluded."""
        parts = [task.description]
        for turn in task.prior_turns:
            if turn.get("role") == "customer":
                parts.append(turn["content"])
        return "  ".join(parts)

    # --- Intent detection (internal) ------------------------------------------

    def _is_daily_overview(self, text: str) -> bool:
        cues = [
            "what's on my calendar", "whats on my calendar",
            "what meetings", "my schedule today", "my schedule tomorrow",
            "daily agenda", "what's my day",
            "my schedule for", "what do i have",
        ]
        return any(cue in text for cue in cues)

    def _is_find_slots(self, text: str) -> bool:
        cues = [
            "find time", "find a slot", "find me",
            "when can i meet", "when can we meet",
            "find available",
        ]
        return any(cue in text for cue in cues)

    def _is_availability_check(self, text: str) -> bool:
        cues = [
            "am i free", "am i available", "do i have anything",
            "any conflicts", "conflict at", "double-booked",
            "do i have a conflict",
        ]
        return any(cue in text for cue in cues)

    def _is_reschedule(self, text: str) -> bool:
        cues = [
            "move the", "move my", "reschedule",
            "push back", "change the time",
        ]
        return any(cue in text for cue in cues)

    def _is_cancel(self, text: str) -> bool:
        cues = [
            "cancel the", "cancel my", "remove the meeting",
            "delete the meeting",
        ]
        return any(cue in text for cue in cues)

    # --- Handler stubs (to be implemented in later tasks) ---------------------

    async def _handle_daily_overview(self, task: SpecialistTask) -> SpecialistResult:
        start = datetime(2026, 1, 1, 0, 0)
        end = datetime(2099, 12, 31, 23, 59)

        events = await self._calendar_client.list_events(start, end)

        event_dicts = [
            {
                "title": e.title,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "attendees": e.attendees,
                "location": e.location,
            }
            for e in events
        ]

        count = len(events)
        if count == 0:
            summary = "Your calendar is clear — no events scheduled."
        else:
            titles = ", ".join(e.title for e in events[:5])
            summary = f"You have {count} event{'s' if count != 1 else ''}: {titles}."

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "events": event_dicts,
                "event_count": count,
            },
            confidence=0.85,
            summary_for_ea=summary,
        )

    async def _handle_find_slots(self, task):
        return SpecialistResult(
            status=SpecialistStatus.FAILED, domain=self.domain,
            payload={}, confidence=0.0, error="Not implemented",
        )

    async def _handle_availability(self, task):
        return SpecialistResult(
            status=SpecialistStatus.FAILED, domain=self.domain,
            payload={}, confidence=0.0, error="Not implemented",
        )

    async def _handle_reschedule(self, task):
        return SpecialistResult(
            status=SpecialistStatus.FAILED, domain=self.domain,
            payload={}, confidence=0.0, error="Not implemented",
        )

    async def _handle_cancel(self, task):
        return SpecialistResult(
            status=SpecialistStatus.FAILED, domain=self.domain,
            payload={}, confidence=0.0, error="Not implemented",
        )

    async def _handle_create_event(self, task):
        return SpecialistResult(
            status=SpecialistStatus.FAILED, domain=self.domain,
            payload={}, confidence=0.0, error="Not implemented",
        )
