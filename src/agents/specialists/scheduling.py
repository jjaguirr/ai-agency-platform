"""
Scheduling specialist agent.

Third specialist in the delegation framework. Handles calendar queries,
meeting creation, rescheduling, cancellation, availability checks, and
slot finding. All calendar I/O goes through a `CalendarClient` Protocol
seam — no Google/Outlook/CalDAV import here.

Routing tension: "schedule" on its own is a weak signal. "Schedule a
post" is social; "schedule a payment" is finance; "schedule a meeting"
is us. The negative guards in `assess_task` damp our confidence when
"schedule" co-occurs with another domain's action noun so the other
specialist outscores us.

The constructor takes an optional `clock` callable so tests can pin
"tomorrow at 2pm" to a known reference. Defaults to `datetime.now`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Protocol, TYPE_CHECKING

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

@dataclass(frozen=True)
class TimeSlot:
    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: tuple[str, ...] = field(default_factory=tuple)
    location: Optional[str] = None


# --- External seam ----------------------------------------------------------

class CalendarClient(Protocol):
    """Structural typing contract for calendar providers.

    Concrete adapters (GoogleCalendarClient, OutlookClient, CalDAVClient)
    live outside this module and conform by shape — no inheritance. This
    keeps every provider's auth/transport stack out of the specialist and
    makes tests inject an in-memory double without touching class
    hierarchies.

    Contract: methods may raise on transport failure. The registry's
    `execute()` wrapper catches and converts to FAILED, so the specialist
    doesn't need its own try/except around every call."""

    async def list_events(self, start: datetime, end: datetime) -> List[CalendarEvent]:
        ...

    async def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        attendees: List[str],
        location: Optional[str] = None,
    ) -> CalendarEvent:
        ...

    async def update_event(
        self,
        event_id: str,
        *,
        title: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        attendees: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> CalendarEvent:
        ...

    async def delete_event(self, event_id: str) -> None:
        ...

    async def is_free(self, start: datetime, end: datetime) -> bool:
        ...

    async def find_slots(
        self,
        duration: timedelta,
        window_start: datetime,
        window_end: datetime,
    ) -> List[TimeSlot]:
        ...


# --- Assessment vocabulary --------------------------------------------------

_UNAMBIGUOUS_PHRASES = ["calendar", "meeting", "appointment", "reschedule"]

_STRONG_PHRASES = [
    "book a call", "set up a meeting", "schedule a meeting", "schedule a call",
    "set up a call", "am i free", "availability", "on my calendar",
    "cancel the meeting", "move my", "find me", "block off",
    "meet with", "any conflict", "do i have anything",
]

_WEAK_PHRASES = [
    "schedule", "sync", "1:1", "call with", "standup",
    "conference", "huddle", "slot",
]

# "Schedule a post/payment" is not ours — the noun after "schedule" is the
# signal. These are the action nouns that mean another domain owns the verb.
_SOCIAL_ACTION_NOUNS = {"post", "tweet", "reel", "story", "hashtag", "content"}
_FINANCE_ACTION_NOUNS = {"payment", "invoice", "transfer", "payroll", "deposit", "bill"}
_DAMP = 0.50

_CALENDAR_TOOLS = {"Google Calendar", "Outlook", "Calendly", "Cal.com", "iCal",
                   "Apple Calendar", "Fantastical"}

_STRATEGIC_PATTERNS = [
    r"\bwhen should i\b",
    r"\bshould i (meet|schedule|book|set up)\b",
    r"\bis it worth\b",
    r"\bworth it\b",
    r"\bhow (many|often|much)\b.*\bmeeting",
    r"\bbetter to meet\b",
    r"\bdoes it make sense to (meet|schedule|book)\b",
]


# --- Parsing helpers --------------------------------------------------------

# "2pm", "2:30pm", "at 3 pm", "at 14:00" — hour, optional minute, optional meridian.
_TIME_RE = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)

# "for 30 minutes", "for an hour", "for 2 hours"
_DURATION_RE = re.compile(
    r"\bfor\s+(?:(\d+)\s*(minute|min|hour|hr)s?|an?\s+(hour|half\s+hour))\b",
    re.IGNORECASE,
)

# "find me 30 minutes", "find me an hour"
_FIND_DURATION_RE = re.compile(
    r"\b(?:find\s+(?:me\s+)?|find\s+a\s+)(\d+)\s*(minute|min|hour|hr)s?\b",
    re.IGNORECASE,
)

# "my 3pm", "the 2pm" — time mention without explicit "at"
_BARE_HOUR_RE = re.compile(
    r"\b(?:my|the)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
    re.IGNORECASE,
)

# Proper-noun after "with" — "with John", "with Maria", "with Acme Corp"
_ATTENDEE_RE = re.compile(
    r"\bwith\s+([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,2})",
)

_STOPWORDS_TITLE = {
    "the", "a", "an", "my", "me", "i", "to", "for", "with", "at",
    "on", "today", "tomorrow", "this", "next", "week", "afternoon",
    "morning", "evening", "pm", "am",
}


class SchedulingSpecialist(SpecialistAgent):

    def __init__(
        self,
        calendar: Optional[CalendarClient] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._calendar = calendar
        self._clock = clock or datetime.now

    @property
    def domain(self) -> str:
        return "scheduling"

    # --- Assessment ---------------------------------------------------------

    def assess_task(
        self, task_description: str, context: "BusinessContext"
    ) -> TaskAssessment:
        text = task_description.lower()

        confidence = 0.0

        for phrase in _UNAMBIGUOUS_PHRASES:
            if phrase in text:
                confidence += 0.60
                break
        for phrase in _STRONG_PHRASES:
            if phrase in text:
                confidence += 0.35
        weak_hits = sum(1 for p in _WEAK_PHRASES if p in text)
        confidence += min(0.25, weak_hits * 0.15)

        # Damp when "schedule" co-occurs with another domain's action noun —
        # unless an unambiguous calendar word anchors us ("schedule a meeting
        # to pay the invoice" is still ours because of "meeting").
        if "schedul" in text:
            has_anchor = any(p in text for p in _UNAMBIGUOUS_PHRASES)
            if not has_anchor:
                words = set(re.findall(r"\b\w+\b", text))
                if words & _SOCIAL_ACTION_NOUNS or words & _FINANCE_ACTION_NOUNS:
                    confidence -= _DAMP

        if confidence > 0:
            tools = set(context.current_tools or [])
            if tools & _CALENDAR_TOOLS:
                confidence += 0.15
            pain = " ".join(context.pain_points or []).lower()
            if any(k in pain for k in ("meeting", "calendar", "schedul")):
                confidence += 0.15

        confidence = max(0.0, min(0.9, confidence))

        is_strategic = False
        if confidence >= 0.4:
            is_strategic = any(re.search(p, text) for p in _STRATEGIC_PATTERNS)

        return TaskAssessment(confidence=confidence, is_strategic=is_strategic)

    # --- Execution ----------------------------------------------------------

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        if self._calendar is None:
            return SpecialistResult(
                status=SpecialistStatus.FAILED,
                domain=self.domain,
                payload={},
                confidence=0.0,
                error=(
                    "No calendar connected — I can't see or edit your schedule. "
                    "Connect a calendar provider to enable this."
                ),
            )

        corpus = self._customer_corpus(task)
        text = corpus.lower()

        intent = self._classify_intent(text)
        handler = {
            "overview": self._handle_overview,
            "create": self._handle_create,
            "reschedule": self._handle_reschedule,
            "cancel": self._handle_cancel,
            "availability": self._handle_availability,
            "slot_find": self._handle_slot_find,
        }[intent]
        return await handler(task, corpus, text)

    # --- Intent dispatch ----------------------------------------------------

    def _classify_intent(self, text: str) -> str:
        # Order matters — more specific cues first.
        if any(c in text for c in ("find me", "find a slot", "find a time",
                                   "when can i meet", "find me a slot",
                                   "find time")):
            return "slot_find"
        if any(c in text for c in ("am i free", "do i have anything",
                                   "any conflict", "any conflicts",
                                   "am i available")):
            return "availability"
        if any(c in text for c in ("move my", "reschedule", "push my",
                                   "push the", "shift my", "shift the",
                                   "change my", "change the")):
            return "reschedule"
        if any(c in text for c in ("cancel", "delete the meeting",
                                   "delete my", "clear my calendar",
                                   "clear the")):
            return "cancel"
        if any(c in text for c in ("schedule a meeting", "schedule a call",
                                   "book a call", "book a meeting",
                                   "set up a meeting", "set up a call",
                                   "block off", "add to my calendar",
                                   "put on my calendar", "meet with")):
            return "create"
        return "overview"

    # --- Overview -----------------------------------------------------------

    async def _handle_overview(
        self, task: SpecialistTask, corpus: str, text: str
    ) -> SpecialistResult:
        day = self._resolve_day(text)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        events = await self._calendar.list_events(start, end)
        events_payload = [self._event_dict(e) for e in sorted(events, key=lambda e: e.start)]

        summary = (
            f"You have {len(events)} event{'s' if len(events) != 1 else ''} "
            f"on {start.strftime('%Y-%m-%d')}."
        )
        if events:
            titles = ", ".join(e.title for e in events[:3])
            summary += f" ({titles}{'…' if len(events) > 3 else ''})"

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "date": start.strftime("%Y-%m-%d"),
                "count": len(events),
                "events": events_payload,
            },
            confidence=0.85,
            summary_for_ea=summary,
        )

    # --- Create -------------------------------------------------------------

    async def _handle_create(
        self, task: SpecialistTask, corpus: str, text: str
    ) -> SpecialistResult:
        when = self._parse_datetime(text)
        if when is None:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={},
                confidence=0.3,
                clarification_question="What time works for this?",
            )

        duration = self._parse_duration(text) or timedelta(minutes=60)
        attendees = self._parse_attendees(corpus)
        title = self._derive_title(corpus, attendees)

        evt = await self._calendar.create_event(
            title=title,
            start=when,
            end=when + duration,
            attendees=attendees,
        )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "event_id": evt.id,
                "title": evt.title,
                "start": evt.start.isoformat(),
                "end": evt.end.isoformat(),
                "attendees": list(evt.attendees),
            },
            confidence=0.85,
            summary_for_ea=(
                f"Booked: {evt.title} on {evt.start.strftime('%Y-%m-%d %H:%M')} "
                f"for {int(duration.total_seconds() // 60)}m."
            ),
        )

    # --- Reschedule ---------------------------------------------------------

    async def _handle_reschedule(
        self, task: SpecialistTask, corpus: str, text: str
    ) -> SpecialistResult:
        candidates = await self._find_candidates(corpus, text)
        if len(candidates) != 1:
            return self._clarify_ambiguity(candidates, verb="reschedule")

        target = candidates[0]
        new_start = self._parse_target_time(text, ref_event=target)
        if new_start is None:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={"event_id": target.id, "title": target.title},
                confidence=0.3,
                clarification_question=(
                    f"When should I move '{target.title}' to?"
                ),
            )

        dur = target.end - target.start
        updated = await self._calendar.update_event(
            target.id, start=new_start, end=new_start + dur
        )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "event_id": updated.id,
                "title": updated.title,
                "old_start": target.start.isoformat(),
                "new_start": updated.start.isoformat(),
                "new_end": updated.end.isoformat(),
            },
            confidence=0.85,
            summary_for_ea=(
                f"Moved '{updated.title}' from "
                f"{target.start.strftime('%H:%M')} to "
                f"{updated.start.strftime('%Y-%m-%d %H:%M')}."
            ),
        )

    # --- Cancel -------------------------------------------------------------

    async def _handle_cancel(
        self, task: SpecialistTask, corpus: str, text: str
    ) -> SpecialistResult:
        candidates = await self._find_candidates(corpus, text)
        if len(candidates) != 1:
            return self._clarify_ambiguity(candidates, verb="cancel")

        target = candidates[0]
        await self._calendar.delete_event(target.id)

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "cancelled_id": target.id,
                "title": target.title,
                "was_at": target.start.isoformat(),
            },
            confidence=0.85,
            summary_for_ea=(
                f"Cancelled '{target.title}' "
                f"({target.start.strftime('%Y-%m-%d %H:%M')})."
            ),
        )

    # --- Availability -------------------------------------------------------

    async def _handle_availability(
        self, task: SpecialistTask, corpus: str, text: str
    ) -> SpecialistResult:
        start, end = self._resolve_window(text)
        free = await self._calendar.is_free(start, end)
        conflicts = (
            [] if free else await self._calendar.list_events(start, end)
        )

        payload = {
            "free": free,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "conflicts": [self._event_dict(e) for e in conflicts],
        }

        if free:
            summary = f"You're free {start.strftime('%Y-%m-%d %H:%M')}–{end.strftime('%H:%M')}."
        else:
            titles = ", ".join(e.title for e in conflicts)
            summary = f"Not free — conflicts: {titles}."

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.8,
            summary_for_ea=summary,
        )

    # --- Slot finding -------------------------------------------------------

    async def _handle_slot_find(
        self, task: SpecialistTask, corpus: str, text: str
    ) -> SpecialistResult:
        duration = self._parse_find_duration(text) or timedelta(minutes=30)
        start, end = self._resolve_window(text, default_span_days=5)

        slots = await self._calendar.find_slots(duration, start, end)
        payload = {
            "duration_minutes": int(duration.total_seconds() // 60),
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "slots": [{"start": s.start.isoformat(), "end": s.end.isoformat()}
                      for s in slots],
        }

        if slots:
            first = slots[0]
            summary = (
                f"Found {len(slots)} open {int(duration.total_seconds() // 60)}m "
                f"slot{'s' if len(slots) != 1 else ''}; earliest is "
                f"{first.start.strftime('%Y-%m-%d %H:%M')}."
            )
        else:
            summary = (
                f"No open {int(duration.total_seconds() // 60)}m slots in that window."
            )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.75,
            summary_for_ea=summary,
        )

    # --- Ambiguity & candidate search ---------------------------------------

    async def _find_candidates(self, corpus: str, text: str) -> List[CalendarEvent]:
        """Find the event(s) a reschedule/cancel request is about.

        Tries, in order: explicit time mention ("my 3pm"), proper-noun
        keyword in title or attendees ("the Acme meeting", "with Maria").
        Search window is the mentioned day, defaulting to today.

        The "to …" clause in a reschedule is the *destination*, not where
        the event currently is — strip it before resolving the search day
        so "reschedule X to tomorrow" looks for X today."""
        locator_text = re.split(r"\bto\b", text, maxsplit=1)[0]
        day = self._resolve_day(locator_text)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        events = await self._calendar.list_events(start, end)

        hr = self._parse_bare_hour(text)
        if hr is not None:
            matches = [e for e in events if e.start.hour == hr[0]
                       and e.start.minute == hr[1]]
            if matches:
                return matches

        keywords = set(re.findall(r"\b[A-Z][\w'.-]{1,}\b", corpus))
        for m in re.finditer(r"\bthe\s+(\w{3,})\b", text):
            keywords.add(m.group(1))
        keywords -= {"I", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}

        if keywords:
            matches = []
            for e in events:
                hay = (e.title + " " + " ".join(e.attendees)).lower()
                if any(k.lower() in hay for k in keywords):
                    matches.append(e)
            if matches:
                return matches

        return []

    def _clarify_ambiguity(
        self, candidates: List[CalendarEvent], verb: str
    ) -> SpecialistResult:
        if not candidates:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={"candidates": []},
                confidence=0.3,
                clarification_question=(
                    f"I don't see that event — which one did you want to {verb}?"
                ),
            )
        listing = "; ".join(
            f"{e.title} at {e.start.strftime('%H:%M')}" for e in candidates
        )
        return SpecialistResult(
            status=SpecialistStatus.NEEDS_CLARIFICATION,
            domain=self.domain,
            payload={"candidates": [self._event_dict(e) for e in candidates]},
            confidence=0.3,
            clarification_question=(
                f"You have {len(candidates)}: {listing}. Which one?"
            ),
        )

    # --- Parsing: time & duration -------------------------------------------

    def _resolve_day(self, text: str) -> datetime:
        now = self._clock()
        if "tomorrow" in text:
            return now + timedelta(days=1)
        if "next week" in text:
            return now + timedelta(days=7)
        return now

    def _parse_datetime(self, text: str) -> Optional[datetime]:
        """Parse a day + time mention. Bare numbers ("the 15th", "30 minutes")
        are rejected unless anchored by a meridian or the word 'at'."""
        day = self._resolve_day(text)

        candidates = []
        for m in _TIME_RE.finditer(text):
            hour_s, minute_s, meridian = m.group(1), m.group(2), m.group(3)
            preceding = text[max(0, m.start() - 4):m.start()].strip()
            if not meridian and not preceding.endswith("at"):
                continue
            hour = int(hour_s)
            minute = int(minute_s) if minute_s else 0
            if meridian:
                mer = meridian.lower()
                if mer == "pm" and hour < 12:
                    hour += 12
                elif mer == "am" and hour == 12:
                    hour = 0
            if 0 <= hour <= 23 and 0 <= minute < 60:
                candidates.append((hour, minute))

        if not candidates:
            return None

        hour, minute = candidates[0]
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _parse_target_time(
        self, text: str, ref_event: CalendarEvent
    ) -> Optional[datetime]:
        """'move my 3pm to 5pm' — 3pm identifies the event, 5pm is the target.
        The word 'to' anchors which one we return."""
        m = re.search(r"\bto\s+(?:tomorrow\s+)?(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
                      text, re.IGNORECASE)
        if not m:
            return None
        hour, minute, meridian = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        if meridian == "pm" and hour < 12:
            hour += 12
        elif meridian == "am" and hour == 12:
            hour = 0
        if "tomorrow" in text[m.start():m.end() + 12] or "tomorrow" in text[:m.start()]:
            day = self._clock() + timedelta(days=1)
        else:
            day = ref_event.start
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _parse_bare_hour(self, text: str) -> Optional[tuple[int, int]]:
        m = _BARE_HOUR_RE.search(text)
        if not m:
            return None
        hour, minute, meridian = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        if meridian == "pm" and hour < 12:
            hour += 12
        elif meridian == "am" and hour == 12:
            hour = 0
        return (hour, minute)

    def _parse_duration(self, text: str) -> Optional[timedelta]:
        m = _DURATION_RE.search(text)
        if not m:
            return None
        if m.group(3):  # "for an hour" / "for a half hour"
            phrase = m.group(3).lower()
            return timedelta(minutes=30) if "half" in phrase else timedelta(hours=1)
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("hour") or unit == "hr":
            return timedelta(hours=n)
        return timedelta(minutes=n)

    def _parse_find_duration(self, text: str) -> Optional[timedelta]:
        m = _FIND_DURATION_RE.search(text)
        if not m:
            return None
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("hour") or unit == "hr":
            return timedelta(hours=n)
        return timedelta(minutes=n)

    def _resolve_window(
        self, text: str, default_span_days: int = 0
    ) -> tuple[datetime, datetime]:
        """Resolve a time-window reference. Defaults to the named part of
        the named day; if `default_span_days` > 0 and no day named, span
        from today through that many days (slot-finding use case)."""
        day = self._resolve_day(text)
        base = day.replace(hour=0, minute=0, second=0, microsecond=0)

        if "afternoon" in text:
            return (base + timedelta(hours=12), base + timedelta(hours=18))
        if "morning" in text:
            return (base + timedelta(hours=8), base + timedelta(hours=12))
        if "evening" in text:
            return (base + timedelta(hours=17), base + timedelta(hours=21))

        if default_span_days > 0:
            return (base, base + timedelta(days=default_span_days))

        return (base, base + timedelta(days=1))

    # --- Parsing: attendees & title -----------------------------------------

    def _parse_attendees(self, corpus: str) -> List[str]:
        names = _ATTENDEE_RE.findall(corpus)
        return list(dict.fromkeys(names))  # preserve order, drop dupes

    def _derive_title(self, corpus: str, attendees: List[str]) -> str:
        """Cosmetic — not load-bearing. Pull an obvious phrase or fall back."""
        lower = corpus.lower()
        m = re.search(r"\bfor\s+((?:\w+\s+){0,3}\w+)", corpus, re.IGNORECASE)
        if m and "block" in lower:
            phrase = m.group(1).strip()
            words = [w for w in phrase.split()
                     if w.lower() not in _STOPWORDS_TITLE
                     and not re.match(r"\d", w)]
            if words:
                return " ".join(words).capitalize()
        if attendees:
            return f"Meeting with {attendees[0]}"
        return "Meeting"

    # --- Shared -------------------------------------------------------------

    def _customer_corpus(self, task: SpecialistTask) -> str:
        parts = [task.description]
        for turn in task.prior_turns:
            if turn.get("role") == "customer":
                parts.append(turn["content"])
        return "  ".join(parts)

    def _event_dict(self, e: CalendarEvent) -> Dict[str, Any]:
        return {
            "id": e.id,
            "title": e.title,
            "start": e.start.isoformat(),
            "end": e.end.isoformat(),
            "attendees": list(e.attendees),
            "location": e.location,
        }
