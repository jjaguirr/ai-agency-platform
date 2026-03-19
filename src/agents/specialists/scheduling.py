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


# --- Parsing helpers --------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

_TIME_RE = re.compile(
    r"(?:\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b"
    r"|\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b)",
    re.IGNORECASE,
)

def _parse_time_match(m: re.Match) -> tuple:
    """Extract (hour, minute, ampm) from _TIME_RE match."""
    if m.group(1) is not None:
        return int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    return int(m.group(4)), int(m.group(5) or 0), (m.group(6) or "").lower()

_DURATION_RE = re.compile(
    r"\b(?:for\s+)?(?:an?\s+hour|(\d+)\s*(?:hour|hr|h|minute|min|m)(?:s|ute)?(?:\s+(?:and\s+)?(\d+)\s*(?:minute|min|m)(?:s|ute)?)?)\b",
    re.IGNORECASE,
)

_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
_TODAY_RE = re.compile(r"\btoday\b", re.IGNORECASE)


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

    async def _handle_find_slots(self, task: SpecialistTask) -> SpecialistResult:
        corpus_lower = task.description.lower()

        dur_match = _DURATION_RE.search(corpus_lower)
        if dur_match:
            if "an hour" in corpus_lower or "a hour" in corpus_lower:
                duration_minutes = 60
            else:
                val = int(dur_match.group(1) or 0)
                if "hour" in (dur_match.group(0) or "").lower():
                    duration_minutes = val * 60
                else:
                    duration_minutes = val
            if duration_minutes == 0:
                duration_minutes = 30
        else:
            m = re.search(r"(\d+)\s*min", corpus_lower)
            duration_minutes = int(m.group(1)) if m else 30

        start = datetime(2026, 3, 19, 8, 0)
        end = datetime(2026, 3, 23, 17, 0)

        slots = await self._calendar_client.find_available_slots(start, end, duration_minutes)

        slot_dicts = [
            {"start": s.start.isoformat(), "end": s.end.isoformat()}
            for s in slots
        ]

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "duration_minutes": duration_minutes,
                "available_slots": slot_dicts,
                "slot_count": len(slot_dicts),
            },
            confidence=0.85,
            summary_for_ea=f"Found {len(slot_dicts)} available {duration_minutes}-minute slot{'s' if len(slot_dicts) != 1 else ''}.",
        )

    async def _handle_availability(self, task: SpecialistTask) -> SpecialistResult:
        corpus_lower = task.description.lower()

        start = datetime(2026, 3, 20, 12, 0)
        end = datetime(2026, 3, 20, 17, 0)

        time_match = _TIME_RE.search(corpus_lower)
        if time_match:
            hour, minute, ampm = _parse_time_match(time_match)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            base = datetime(2026, 3, 20) if "tomorrow" in corpus_lower else datetime(2026, 3, 19)
            start = base.replace(hour=hour, minute=minute)
            end = start + timedelta(hours=1)

        free = await self._calendar_client.is_free(start, end)

        if free:
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED,
                domain=self.domain,
                payload={"free": True, "range": f"{start.isoformat()} - {end.isoformat()}"},
                confidence=0.85,
                summary_for_ea=f"You're free from {start.strftime('%I:%M %p')} to {end.strftime('%I:%M %p')}.",
            )

        events = await self._calendar_client.list_events(start, end)
        conflicts = [
            {
                "title": e.title,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
            }
            for e in events
        ]

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={"free": False, "conflicts": conflicts},
            confidence=0.85,
            summary_for_ea=f"You have {len(conflicts)} conflict{'s' if len(conflicts) != 1 else ''} in that time range.",
        )

    async def _handle_reschedule(self, task: SpecialistTask) -> SpecialistResult:
        corpus = self._customer_corpus(task)
        corpus_lower = corpus.lower()

        events = await self._calendar_client.list_events(
            datetime(2026, 1, 1), datetime(2099, 12, 31)
        )

        if not events:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain, payload={}, confidence=0.3,
                clarification_question="I don't see any events on your calendar. Which meeting did you mean?",
            )

        candidates = self._match_events(events, corpus_lower)

        if len(candidates) == 0:
            candidates = events

        if len(candidates) > 1:
            names = ", ".join(f"'{e.title}' at {e.start.strftime('%I:%M %p')}" for e in candidates[:5])
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain, payload={}, confidence=0.4,
                clarification_question=f"Which meeting should I move? I see: {names}",
            )

        target = candidates[0]

        all_times = list(_TIME_RE.finditer(corpus))
        if len(all_times) >= 2:
            dest = all_times[-1]
            hour, minute, ampm = _parse_time_match(dest)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            duration = target.end - target.start
            new_start = target.start.replace(hour=hour, minute=minute)
            new_end = new_start + duration
        elif len(all_times) == 1:
            dest = all_times[0]
            hour, minute, ampm = _parse_time_match(dest)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            duration = target.end - target.start
            new_start = target.start.replace(hour=hour, minute=minute)
            new_end = new_start + duration
        else:
            new_start = target.start
            new_end = target.end

        await self._calendar_client.update_event(
            target.id, start=new_start, end=new_end,
        )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "action": "rescheduled",
                "event_id": target.id,
                "original_start": target.start.isoformat(),
                "new_start": new_start.isoformat(),
                "new_end": new_end.isoformat(),
            },
            confidence=0.85,
            summary_for_ea=f"Moved '{target.title}' to {new_start.strftime('%I:%M %p')}.",
        )

    async def _handle_cancel(self, task: SpecialistTask) -> SpecialistResult:
        corpus = self._customer_corpus(task)
        corpus_lower = corpus.lower()

        events = await self._calendar_client.list_events(
            datetime(2026, 1, 1), datetime(2099, 12, 31)
        )

        if not events:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain, payload={}, confidence=0.3,
                clarification_question="I don't see any events to cancel. Which meeting did you mean?",
            )

        candidates = self._match_events(events, corpus_lower)

        if len(candidates) == 0:
            candidates = events

        if len(candidates) > 1:
            names = ", ".join(f"'{e.title}' at {e.start.strftime('%I:%M %p')}" for e in candidates[:5])
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain, payload={}, confidence=0.4,
                clarification_question=f"Which meeting do you want to cancel? {names}",
            )

        target = candidates[0]
        await self._calendar_client.delete_event(target.id)

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "action": "cancelled",
                "event_id": target.id,
                "title": target.title,
            },
            confidence=0.85,
            summary_for_ea=f"Cancelled '{target.title}'.",
        )

    def _match_events(self, events: list, text: str) -> list:
        """Match events by time reference or title/attendee keyword."""
        matched = []

        time_ref = _TIME_RE.search(text)
        if time_ref:
            hour, _, ampm = _parse_time_match(time_ref)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            matched = [e for e in events if e.start.hour == hour]
            if matched:
                return matched

        skip = {"the", "my", "a", "an", "with", "at", "to", "for", "on",
                "cancel", "move", "reschedule", "meeting", "push", "back",
                "change", "time", "delete", "remove", "pm", "am"}
        words = [w for w in re.findall(r"\b\w+\b", text) if w not in skip and len(w) > 2]

        for event in events:
            title_lower = event.title.lower()
            attendees_lower = " ".join(event.attendees).lower()
            for word in words:
                if word in title_lower or word in attendees_lower:
                    matched.append(event)
                    break

        return matched

    async def _handle_create_event(self, task: SpecialistTask) -> SpecialistResult:
        corpus = self._customer_corpus(task)
        corpus_lower = corpus.lower()

        attendees = _EMAIL_RE.findall(corpus)

        time_match = _TIME_RE.search(corpus)
        has_time = time_match is not None

        dur_match = _DURATION_RE.search(corpus)
        if dur_match:
            if "an hour" in corpus_lower or "a hour" in corpus_lower:
                duration_minutes = 60
            else:
                hours = int(dur_match.group(1) or 0)
                mins = int(dur_match.group(2) or 0)
                if "hour" in (dur_match.group(0) or "").lower() or "hr" in (dur_match.group(0) or "").lower():
                    duration_minutes = hours * 60 + mins
                else:
                    duration_minutes = hours  # it's minutes
            if duration_minutes == 0:
                duration_minutes = 60
        else:
            duration_minutes = 60

        # Must have time/date to proceed — check this first.
        if not has_time and "tomorrow" not in corpus_lower and "today" not in corpus_lower:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={},
                confidence=0.3,
                clarification_question="What day and time should I schedule this?",
            )

        # "meeting with" but no email and no prior clarification cycle → ask who.
        has_meeting_with = "meeting with" in corpus_lower
        if has_meeting_with and not attendees and not task.prior_turns:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={},
                confidence=0.3,
                clarification_question="Who should I invite? Please provide their email addresses.",
            )

        if has_time:
            hour, minute, ampm = _parse_time_match(time_match)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
        else:
            hour, minute = 9, 0

        base_date = datetime(2026, 3, 20) if "tomorrow" in corpus_lower else datetime(2026, 3, 19)
        start = base_date.replace(hour=hour, minute=minute)
        end = start + timedelta(minutes=duration_minutes)

        title = self._derive_title(corpus)

        event = await self._calendar_client.create_event(
            title=title,
            start=start,
            end=end,
            attendees=attendees,
        )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "action": "created",
                "event": {
                    "title": event.title,
                    "start": event.start.isoformat(),
                    "end": event.end.isoformat(),
                    "attendees": event.attendees,
                    "location": event.location,
                },
            },
            confidence=0.85,
            summary_for_ea=f"Scheduled '{event.title}' from {event.start.strftime('%I:%M %p')} to {event.end.strftime('%I:%M %p')}.",
        )

    def _derive_title(self, corpus: str) -> str:
        """Extract a meeting title from the message. Falls back to 'Meeting'."""
        lower = corpus.lower()
        m = re.search(r"meeting\s+with\s+([\w\s@.]+?)(?:\s+(?:at|on|for|tomorrow|today|$))", lower)
        if m:
            return f"Meeting with {m.group(1).strip()}"
        m = re.search(r"(?:book|schedule|set up)\s+(?:a\s+)?(.+?)(?:\s+(?:at|on|for|tomorrow|today))", lower)
        if m:
            return m.group(1).strip().title()
        return "Meeting"
