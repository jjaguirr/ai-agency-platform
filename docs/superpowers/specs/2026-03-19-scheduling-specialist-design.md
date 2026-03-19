# Scheduling Specialist — Design

**Date:** 2026-03-19
**Scope:** third specialist in the delegation framework; wire finance + scheduling into the EA.

## Goal

Route calendar-management requests ("what's my day look like?", "move the 3pm", "find me 30 minutes with Maria") to a `SchedulingSpecialist` that talks to calendar providers through a `CalendarClient` Protocol seam. No Google/Outlook dependency baked in.

## Module: `src/agents/specialists/scheduling.py`

### Domain types

```python
@dataclass(frozen=True)
class TimeSlot:
    start: datetime
    end: datetime
    # .duration derived property

@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: tuple[str, ...]
    location: str | None = None
```

Frozen so slots and events are safely passed across the protocol boundary and hashable if needed.

### CalendarClient Protocol

Structural typing — concrete adapters conform by shape, never inherit.

```python
class CalendarClient(Protocol):
    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...
    async def create_event(self, title: str, start: datetime, end: datetime,
                           attendees: list[str], location: str | None = None) -> CalendarEvent: ...
    async def update_event(self, event_id: str, *, title: str | None = None,
                           start: datetime | None = None, end: datetime | None = None,
                           attendees: list[str] | None = None,
                           location: str | None = None) -> CalendarEvent: ...
    async def delete_event(self, event_id: str) -> None: ...
    async def is_free(self, start: datetime, end: datetime) -> bool: ...
    async def find_slots(self, duration: timedelta, window_start: datetime,
                         window_end: datetime) -> list[TimeSlot]: ...
```

### Constructor

```python
SchedulingSpecialist(calendar: CalendarClient | None = None,
                     clock: Callable[[], datetime] | None = None)
```

`clock` defaults to `datetime.now`. Tests inject a fixed clock so "tomorrow at 2pm" resolves deterministically.

### Graceful degradation (`calendar=None`)

`assess_task` always works — routing must not depend on a live calendar. `execute_task` returns `FAILED` with `error="No calendar connected"`. The EA falls back to general assistance.

## Routing (`assess_task`)

### Keyword tiers

| Tier | Weight | Phrases |
|------|--------|---------|
| Unambiguous | +0.60 (once) | `calendar`, `meeting`, `appointment`, `reschedule` |
| Strong | +0.35 each | `book a call`, `set up a meeting`, `schedule a meeting`, `schedule a call`, `am i free`, `availability`, `on my calendar`, `cancel the meeting`, `move my`, `find me N minutes`, `my 3pm`/`my 2pm` pattern |
| Weak | ≤ +0.25 capped | `sync`, `1:1`, `call with`, `conference`, `this week`, `tomorrow afternoon` |
| Context | +0.15 each | `Google Calendar`/`Outlook`/`Calendly` in `current_tools`; `scheduling`/`calendar`/`meeting` in `pain_points` |

### Negative guards

Bare "schedule" is weak signal — many domains schedule things. When `schedule` co-occurs with another domain's action noun, damp by −0.35 so the other specialist outscores:

- `schedule` + {`post`, `tweet`, `content`, `story`, `reel`, `hashtag`} → social media owns it
- `schedule` + {`payment`, `invoice`, `transfer`, `payroll`, `deposit`} → finance owns it

"Schedule a meeting with the accountant" has `meeting` (unambiguous) so scheduling still wins despite the finance noun.

### Strategic gate (at ≥0.4)

- `\bwhen should i\b` + (plan|schedule|meet) — "when should I plan the social media budget review?"
- `\bshould i (meet|schedule|book)\b`
- `\bis it worth meeting\b`
- `\bhow (many|often) .* meeting\b`
- `\bbetter to meet or\b`

Cap confidence at 0.9.

## Execution (`execute_task`)

Intent dispatch on pooled corpus (current message + prior customer turns):

### Overview
Cues: `what's on`, `my day`, `my calendar today`, `what meetings do i have`.
→ resolve day → `list_events` → payload `{date, events: [{start, end, title, attendees}], count}`.

### Create
Cues: `schedule a meeting`, `book a call`, `set up a meeting`, `add ... to my calendar`.
→ parse title, start, duration (default 60m if unspecified but time is clear), attendees.
Missing start time → `NEEDS_CLARIFICATION` ("What time works?").
Attendees optional (focus blocks are real).
→ `create_event` → payload `{event_id, title, start, end, attendees}`.

### Reschedule
Cues: `move`, `reschedule`, `push`, `shift ... to`.
→ `list_events` over the mentioned day → match by time or attendee/title mention.
0 candidates → clarify ("I don't see a 3pm — which meeting?").
>1 candidates → clarify, listing them ("You have two at 3pm: X and Y — which one?").
1 → `update_event` → payload echoes old/new times.

### Cancel
Cues: `cancel`, `delete the meeting`, `clear my`.
Same disambiguation as reschedule → `delete_event` → payload `{cancelled: event_id, title}`.

### Availability
Cues: `am i free`, `do i have anything`, `any conflict at`.
→ `is_free` + `list_events` over the range → payload `{free: bool, window, conflicts: [events]}`.

### Slot finding
Cues: `find me N minutes`, `find a slot`, `when can i meet`, `free time with`.
→ parse duration (default 30m) + window (default this work week) → `find_slots` → payload `{duration, slots: [...], proposed_top_3}`.

### Clarification resolution

Same `_customer_corpus()` pattern as finance — concatenate `task.description` with prior customer turns so a reply like "3pm works" fills the missing time from the original request.

## EA registration (`executive_assistant.py`)

Remove the module-level `from .specialists.social_media import SocialMediaSpecialist` (line 59). Replace the inline registration in `__init__` with three independently-guarded blocks:

```python
self.delegation_registry = DelegationRegistry(confidence_threshold=0.6)
for mod, cls in (("social_media", "SocialMediaSpecialist"),
                 ("finance", "FinanceSpecialist"),
                 ("scheduling", "SchedulingSpecialist")):
    try:
        m = __import__(f"src.agents.specialists.{mod}", fromlist=[cls])
        self.delegation_registry.register(getattr(m, cls)())
    except Exception as e:
        logger.warning(f"{cls} unavailable: {e}")
```

(Or three explicit try/except blocks — same effect. Each import failure isolated; any subset registers.)

Zero changes to `src/agents/base/specialist.py`.

## Validation checklist (from task spec)

- [ ] `uv run pytest tests/unit/ -q` — zero failures
- [ ] `CalendarClient` is a Protocol, no inheritance
- [ ] scheduling routes: overview, create, reschedule, cancel, availability, slot-find
- [ ] "Schedule a post for Tuesday" → social_media
- [ ] "Schedule a payment for the 15th" → finance
- [ ] "Book a meeting with the accountant to review expenses" → scheduling
- [ ] "When should I plan the social media budget review?" → strategic, EA keeps
- [ ] missing time/attendees → `NEEDS_CLARIFICATION`
- [ ] ambiguous "move my meeting" with multiple candidates → clarify
- [ ] works with mocked `CalendarClient`
- [ ] `calendar=None` → `FAILED` gracefully
- [ ] EA initializes with all three when imports succeed
- [ ] EA initializes with any subset when imports fail
- [ ] zero framework changes
- [ ] tests committed before implementation
