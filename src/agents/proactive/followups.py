"""
Commitment extraction — turning free-text promises into tracked follow-ups.

Scope is deliberately narrow: explicit imperative/commitment patterns
with an anchoring timeframe. False negatives are fine (the customer can
always say "remind me to X" explicitly). False positives that spam the
customer with imagined obligations are not fine — so vague, hedged, or
deadline-less language falls through.

Patterns that DO extract:
  • "remind me to X [by/on <day>|tomorrow]"  — imperative, unambiguous
  • "I'll / I will <verb> ... by/on <day>"   — first-person commitment + anchor
  • "let me get back to <person> <timeframe>"

The only pattern that tolerates a missing deadline is "remind me to X"
(defaults to tomorrow) — the imperative is explicit enough that we can
pick a sensible default without risking spam.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .triggers import Priority, ProactiveTrigger


# --- Commitment -------------------------------------------------------------

@dataclass(frozen=True)
class Commitment:
    """A tracked obligation with a deadline.

    Frozen → hashable → stable id derived from content. Two identical
    utterances produce identical ids, which lets the state store dedupe
    naturally if the customer repeats themselves.
    """
    text: str
    due: datetime
    raw: str

    @property
    def id(self) -> str:
        # Stable digest of the semantic fields. SHA-1 is fine — collision
        # resistance isn't a security property here, we just need a
        # deterministic key.
        h = hashlib.sha1()
        h.update(self.text.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.due.isoformat().encode("utf-8"))
        return h.hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "due": self.due.isoformat(), "raw": self.raw}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Commitment":
        return cls(text=d["text"], due=datetime.fromisoformat(d["due"]), raw=d["raw"])


# --- Date parsing -----------------------------------------------------------

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _next_weekday(ref: datetime, target: int) -> datetime:
    """Next occurrence of weekday `target` strictly after ref.date()."""
    delta = (target - ref.weekday()) % 7
    if delta == 0:
        delta = 7  # "by Thursday" said on Thursday means NEXT Thursday
    return (ref + timedelta(days=delta)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )


def _parse_timeframe(fragment: str, ref: datetime) -> Optional[datetime]:
    """Turn 'by Thursday' / 'tomorrow' / 'on Monday' into a datetime.

    Returns None for timeframes we don't understand — which means the
    enclosing pattern won't fire either (no-deadline I'll-statements are
    dropped, by design).
    """
    frag = fragment.lower().strip()
    if "tomorrow" in frag:
        return (ref + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
    if "today" in frag:
        return ref.replace(hour=17, minute=0, second=0, microsecond=0)
    for name, idx in _WEEKDAYS.items():
        if name in frag:
            return _next_weekday(ref, idx)
    return None


# --- Extraction patterns ----------------------------------------------------
#
# Each pattern is a regex with named groups:
#   task  → the verb-phrase we remind about
#   when  → optional timeframe fragment fed to _parse_timeframe
#
# We match case-insensitively and tolerate surrounding punctuation via
# a trailing lazy consumer. Patterns are ORed together — first match wins
# for a given utterance (no multi-commitment-per-message; keep it simple).

# "remind me to call John by Thursday"
_RE_REMIND = re.compile(
    r"remind\s+me\s+to\s+(?P<task>.+?)"
    r"(?:\s+(?:by|on|at)\s+(?P<when>\w+))?\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# "I'll send the proposal by Thursday" / "I will follow up on Monday"
# Requires an explicit by/on/at anchor — no default deadline for I'll.
_RE_ILL = re.compile(
    r"(?:I[’']?ll|I\s+will)\s+(?P<task>.+?)\s+(?:by|on|at)\s+(?P<when>\w+)"
    r"\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# "let me get back to them tomorrow"
# Same as I'll: requires the timeframe anchor. Without it, this pattern
# doesn't match at all — "I need to get back to them at some point"
# falls through.
_RE_GETBACK = re.compile(
    r"(?:let\s+me\s+|I(?:[’']?ll|\s+will)\s+)?get\s+back\s+to\s+"
    r"(?P<who>\w+)\s+(?P<when>tomorrow|today|"
    r"(?:on|by)\s+\w+)"
    r"\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def extract_commitments(text: str, *, ref: datetime) -> List[Commitment]:
    """Pull zero-or-more commitments out of a user utterance.

    Normalises curly apostrophes before matching — mobile keyboards are
    inconsistent about ’ vs ' and we don't want that to decide whether
    a reminder fires.
    """
    if not text or not text.strip():
        return []

    # Normalise smart quotes so a single regex handles both.
    norm = text.replace("\u2019", "'")

    # remind-me — the one pattern with a default deadline.
    m = _RE_REMIND.search(norm)
    if m:
        task = m.group("task").strip()
        # The task group is lazy, but a bare "remind me to chase the invoice"
        # leaves trailing whitespace captured as task — strip handles it.
        when = m.group("when")
        # If the "when" group captured a weekday that wasn't prefixed with
        # by/on/at (because the regex's (?:by|on|at) is mandatory when the
        # group matches), it won't — so this is correct. If when is None we
        # default to tomorrow.
        if when:
            due = _parse_timeframe(when, ref)
            if due is None:
                # The suffix wasn't a timeframe we understand — it was
                # probably part of the task ("remind me to call John").
                # Fold it back into the task and default the deadline.
                task = f"{task} {when}".rstrip()
                due = _parse_timeframe("tomorrow", ref)
        else:
            due = _parse_timeframe("tomorrow", ref)
        return [Commitment(text=task, due=due, raw=text)]

    # I'll / I will … by/on <day>
    m = _RE_ILL.search(norm)
    if m:
        task = m.group("task").strip()
        due = _parse_timeframe(m.group("when"), ref)
        if due is None:
            return []
        return [Commitment(text=task, due=due, raw=text)]

    # get back to <person> <timeframe>
    m = _RE_GETBACK.search(norm)
    if m:
        who = m.group("who")
        due = _parse_timeframe(m.group("when"), ref)
        if due is None:
            return []
        task = f"get back to {who}"
        return [Commitment(text=task, due=due, raw=text)]

    return []


# --- Trigger generation -----------------------------------------------------

def commitment_to_trigger(c: Commitment, *, now: datetime) -> Optional[ProactiveTrigger]:
    """Convert a due commitment into a deliverable trigger.

    Only fires at or after the due time. Cooldown key is the commitment's
    stable id — the gate stops this from firing every tick until the
    follow-up is resolved.
    """
    if now < c.due:
        return None
    return ProactiveTrigger(
        domain="ea",
        trigger_type="follow_up",
        priority=Priority.MEDIUM,
        title="Follow-up due",
        payload={"commitment_id": c.id, "text": c.text, "due": c.due.isoformat()},
        suggested_message=f"Reminder: {c.text}",
        cooldown_key=f"followup:{c.id}",
        created_at=now,
    )
