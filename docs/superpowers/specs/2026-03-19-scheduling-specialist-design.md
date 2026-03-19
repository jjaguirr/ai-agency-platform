# Scheduling Specialist Design

## Overview

A third specialist for the EA delegation framework. Handles calendar management — daily overviews, event creation, rescheduling, cancellation, availability checks, and slot finding. Follows the same single-module pattern as `social_media.py` and `finance.py`.

This task also wires the existing `FinanceSpecialist` (currently unregistered) into the EA alongside the new `SchedulingSpecialist`.

## Domain Types

Defined in `src/agents/specialists/scheduling.py`, co-located with the Protocol and specialist class.

### CalendarEvent

```python
@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: List[str]        # plain email strings
    location: Optional[str] = None
```

**Timezone note:** All datetimes are naive (no tzinfo) for the initial implementation. The specialist assumes local time. Timezone-aware handling is deferred to the concrete calendar adapter.

### TimeSlot

```python
@dataclass
class TimeSlot:
    start: datetime
    end: datetime
```

## CalendarClient Protocol

Structural typing via `typing.Protocol` — no inheritance, no import of concrete implementations. Mirrors the `StockPriceClient` seam in `finance.py`.

**Error contract:** Never raise. Transport/auth failures return empty lists, `False`, or empty results as appropriate. Unknown event IDs return `False` from `delete_event`. This matches the finance specialist's `StockPriceClient` contract where failures return `{}`.

```python
class CalendarClient(Protocol):
    async def list_events(self, start: datetime, end: datetime) -> List[CalendarEvent]: ...
    async def create_event(self, title: str, start: datetime, end: datetime,
                           attendees: List[str], location: Optional[str] = None) -> CalendarEvent: ...
    async def update_event(self, event_id: str, **kwargs: Any) -> CalendarEvent: ...
    async def delete_event(self, event_id: str) -> bool: ...
    async def is_free(self, start: datetime, end: datetime) -> bool: ...
    async def find_available_slots(self, start: datetime, end: datetime,
                                   duration_minutes: int) -> List[TimeSlot]: ...
```

## Graceful Degradation

Constructor: `SchedulingSpecialist(calendar_client: Optional[CalendarClient] = None)`

- `assess_task` always works — routing is keyword-based, no client needed.
- `execute_task` with `calendar_client=None` returns `SpecialistResult` with `status=FAILED` and `error="No calendar service connected. Calendar operations are unavailable."`.

## Assessment (assess_task)

### Keyword Tiers

| Tier | Keywords/Phrases | Score |
|------|-----------------|-------|
| Unambiguous | "my calendar", "my schedule", "my meetings", "my appointments", "book a meeting", "cancel the meeting", "reschedule", "daily agenda" | +0.60 (break after first match) |
| Strong | "meeting with", "appointment with", "free at", "available at", "conflict at", "what's on my", "block time", "move the", "push back" | +0.35 |
| Weak | "calendar", "meeting", "appointment", "busy", "free", "slot" | +0.15 each, capped at 0.25 total (follows finance.py weak-phrase cap to prevent "calendar + meeting + busy" from stacking into a false positive) |

### Context Boosts

- Customer uses calendar tools (Google Calendar, Outlook, Calendly, etc.): +0.2
- Customer pain points mention scheduling/calendar: +0.15

### Caps and Gates

- Hard cap: 0.9
- Strategic gate: confidence >= 0.4 AND advisory pattern detected ("should I", "is it worth", "too many meetings", "how many meetings should I") → `is_strategic=True`

### Overlap Resolution

The key routing principle: **action type determines domain, not topic.**

| Message | Routes To | Why |
|---------|----------|-----|
| "What meetings do I have tomorrow?" | Scheduling | Calendar action (list events) |
| "Schedule a post for next Tuesday" | Social Media | Platform action (post), not calendar |
| "Set up a content planning meeting for marketing" | Scheduling | Calendar action (create meeting), topic irrelevant |
| "Schedule a payment for the 15th" | Finance | Financial action (payment), not calendar |
| "Book a meeting with the accountant to review Q3 expenses" | Scheduling | Calendar action (book meeting), topic irrelevant |
| "When should I plan the social media budget review?" | EA (strategic) | Three-way ambiguity, advisory framing |

"Schedule" alone is **not** a scheduling keyword. The specialist fires on calendar/meeting/appointment action nouns, not on the verb "schedule" in isolation. This prevents false positives on "schedule a post" or "schedule a payment."

## Execution (execute_task)

### Intent Routing

Message content determines which handler runs. Checked in order:

1. **Daily overview** — triggers: "what's on my calendar", "what meetings", "my schedule today/tomorrow", "daily agenda"
   → `_handle_daily_overview(task)`

2. **Slot finding** — triggers: "find time", "find a slot", "find me", "when can I meet", "when can we meet"
   → `_handle_find_slots(task)`

3. **Availability / conflict check** — triggers: "am I free", "do I have anything", "any conflicts", "am I available", "conflict", "double-booked"
   → `_handle_availability(task)`

4. **Rescheduling** — triggers: "move", "reschedule", "push back", "change the time", "move the"
   → `_handle_reschedule(task)`

5. **Cancellation** — triggers: "cancel", "remove the meeting", "delete the meeting"
   → `_handle_cancel(task)`

6. **Event creation** — default fallback when other intents don't match but assessment routed here
   → `_handle_create_event(task)`

Order matters: slot finding before availability (both use "free"), rescheduling before cancellation (both modify events), creation is the fallback.

### Handler Behaviors

#### _handle_daily_overview

- Calls `list_events(start_of_day, end_of_day)` for the referenced day.
- Returns `COMPLETED` with payload:
  ```python
  {
      "date": "2026-03-19",
      "events": [
          {"title": "...", "start": "...", "end": "...", "attendees": [...], "location": "..."},
          ...
      ],
      "event_count": 3
  }
  ```
- `summary_for_ea`: "You have 3 events today: Team Standup at 9am, Lunch with Maria at noon, ..."

#### _handle_create_event

- Extracts from message + prior_turns: title, time, duration, attendees.
- **Missing required fields → NEEDS_CLARIFICATION**:
  - No time/date mentioned → "What day and time should I schedule this?"
  - No attendees for "meeting with" → "Who should I invite?"
  - No duration → defaults to 60 minutes (common convention, not a guess on ambiguous data)
- On success: calls `create_event(...)`, returns `COMPLETED` with event details.
- Payload:
  ```python
  {
      "action": "created",
      "event": {"title": "...", "start": "...", "end": "...", "attendees": [...], "location": "..."}
  }
  ```

#### _handle_reschedule

- Identifies target event from message context (time reference, title, attendee name).
- If multiple events match → `NEEDS_CLARIFICATION`: "I see several meetings around that time: [list]. Which one should I move?"
- Extracts new time from message.
- Calls `update_event(event_id, start=..., end=...)`.
- Payload:
  ```python
  {
      "action": "rescheduled",
      "event_id": "...",
      "original_start": "...",
      "new_start": "...",
      "new_end": "..."
  }
  ```

#### _handle_cancel

- Identifies target event by title keyword, attendee name, or time reference.
- Multiple matches → `NEEDS_CLARIFICATION`: "Which meeting do you want to cancel? [list]"
- Calls `delete_event(event_id)`.
- Payload:
  ```python
  {
      "action": "cancelled",
      "event_id": "...",
      "title": "..."
  }
  ```

#### _handle_availability

Handles both "am I free?" and "do I have a conflict?" — these are the same operation (check a time range and report what's there).

- Extracts time range from message (e.g., "tomorrow afternoon" → 12pm-5pm).
- Calls `is_free(start, end)`.
- If free → payload: `{"free": True, "range": "..."}`
- If not → calls `list_events(start, end)` to show conflicts: `{"free": False, "conflicts": [...]}`

#### _handle_find_slots

- Extracts: duration, date range, attendees (if mentioned).
- Calls `find_available_slots(start, end, duration_minutes)`.
- Returns proposed slots in payload:
  ```python
  {
      "duration_minutes": 30,
      "available_slots": [
          {"start": "...", "end": "..."},
          ...
      ],
      "slot_count": 4
  }
  ```

### Shared Helpers

#### _customer_corpus(task)

Concatenates `task.description` with all customer-role entries from `task.prior_turns`. Filters out specialist turns. Matches the `_customer_corpus` helper in `finance.py`. Used by all handlers that need multi-turn extraction.

#### Date Parsing Strategy

Minimal date parsing for the initial implementation:
- "today" / bare "my schedule" → current date
- "tomorrow" → current date + 1 day
- "next Monday" / day-of-week references → next occurrence
- Explicit date strings (e.g., "March 25", "3/25") → parsed directly
- Time-of-day: "morning" → 8am-12pm, "afternoon" → 12pm-5pm, "evening" → 5pm-9pm
- Specific times: "at 2pm", "at 14:00" → parsed directly
- Unresolvable date/time → NEEDS_CLARIFICATION

### Multi-turn Clarification

Same `prior_turns` pattern as finance:
1. Specialist returns `NEEDS_CLARIFICATION` with question.
2. EA persists `active_delegation` with `prior_turns`.
3. Customer replies.
4. EA appends reply to `prior_turns`, re-dispatches to specialist.
5. Specialist concatenates message + customer prior_turns into corpus for extraction.

## Registration

**Current state:** `SocialMediaSpecialist` is imported at module level and registered unconditionally in `executive_assistant.py`. `FinanceSpecialist` exists in `src/agents/specialists/finance.py` but is not imported or registered. This task wires both finance and scheduling.

Each new specialist gets an independently guarded import. If finance fails, scheduling and social media still register. If scheduling fails, finance and social media still register.

```python
# Existing (module-level, unchanged)
from .specialists.social_media import SocialMediaSpecialist

# In __init__ or _register_specialists:
self.delegation_registry.register(SocialMediaSpecialist())

# New: Finance (guarded)
try:
    from .specialists.finance import FinanceSpecialist
    self.delegation_registry.register(FinanceSpecialist())
except ImportError:
    pass

# New: Scheduling (guarded)
try:
    from .specialists.scheduling import SchedulingSpecialist
    self.delegation_registry.register(SchedulingSpecialist())
except ImportError:
    pass
```

Zero changes to `specialist.py` or the delegation framework.

## Test Plan

TDD — tests written before implementation.

### CalendarClient Protocol Tests
- Stub client conforming by structural typing (no inheritance) works with specialist.
- No imports of httpx/requests/aiohttp in scheduling.py (seam isolation).

### Assessment Tests
- Unambiguous calendar queries → high confidence (>= 0.6), even without context boosts (lexical floor).
- Strategic advisory questions → `is_strategic=True`.
- Out-of-domain messages → low confidence (< 0.6).
- "Schedule a post for Tuesday" → below threshold (social media territory).
- "Schedule a payment for the 15th" → below threshold (finance territory).
- "Book a meeting with the accountant to review expenses" → high confidence (calendar action).
- "When should I plan the social media budget review?" → strategic flag.
- Context boosts: calendar tools and pain points increase confidence.

### Execution Tests
- Daily overview: returns structured event list.
- Event creation with full details: returns COMPLETED with event payload.
- Event creation missing time: returns NEEDS_CLARIFICATION.
- Event creation missing attendees (for "meeting with"): returns NEEDS_CLARIFICATION.
- Rescheduling single match: returns COMPLETED with updated times.
- Rescheduling multiple matches: returns NEEDS_CLARIFICATION with options.
- Cancellation single match: returns COMPLETED.
- Cancellation multiple matches: returns NEEDS_CLARIFICATION.
- Availability check free: reports free.
- Availability check busy: reports conflicts.
- Slot finding: returns available time slots.
- Multi-turn clarification via prior_turns resolves missing info.

### Graceful Degradation Tests
- `calendar_client=None`: assess_task still works, execute_task returns FAILED.

### Registration Tests
- EA initializes with all three specialists.
- EA initializes with any subset when imports fail.

### Overlap Tests (cross-specialist)
- Routing disambiguation between scheduling, social media, and finance.
