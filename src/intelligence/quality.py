"""
Heuristic quality signals for conversation triage.

All three detectors are pure: messages + delegation metadata in, bool
out. No I/O, no LLM. Tuned for recall — a false flag costs one glance
at a fine conversation; a miss means a frustrated customer goes unseen.
"""
from __future__ import annotations

import re
from typing import Sequence


# Phrases that signal frustration or a handoff request. Matched as whole
# regexes against lowercased user messages. Word boundaries on single
# tokens so "human resources" and "send to a real person at acme" don't
# trip; multi-word phrases are specific enough to match as substrings.
_ESCALATION_PATTERNS = tuple(re.compile(p) for p in (
    r"\btalk to a (?:human|real person|person)\b",
    r"\bspeak to a (?:human|real person|person)\b",
    r"\bis there a (?:human|real person)\b",
    r"\bget me a (?:human|real person)\b",
    r"\b(?:want|need) a (?:human|real person)\b",
    r"\bthis is (?:useless|ridiculous|broken|pointless)\b",
    r"\b(?:so|really|very|extremely) frustrated\b",
    r"\bi'?m frustrated\b",
))

# Median conversation is 4–6 messages. Twice that starts to smell.
LONG_THRESHOLD_DEFAULT = 12

# Delegation statuses that count as "the thing got done". Mirrors
# SpecialistStatus.COMPLETED.value — kept as a literal here so this
# module stays import-free of agent internals.
_TERMINAL_OK = frozenset({"completed"})
_TERMINAL_BAD = frozenset({"failed", "cancelled"})


def detect_escalation(messages: Sequence[dict]) -> bool:
    for m in messages:
        if m.get("role") != "user":
            continue
        text = (m.get("content") or "").lower()
        if any(p.search(text) for p in _ESCALATION_PATTERNS):
            return True
    return False


def detect_unresolved(
    messages: Sequence[dict],
    *,
    delegation_statuses: Sequence[str],
) -> bool:
    """A conversation is unresolved if either:
      - the last message is from the customer (they said something and
        got no reply), or
      - a delegation happened but none reached COMPLETED (specialist
        failed, was cancelled, or is still waiting on clarification the
        customer never provided).

    General Q&A with no delegations and an assistant reply is resolved
    by default — we have no signal it went wrong.
    """
    if not messages:
        return False

    if messages[-1].get("role") == "user":
        return True

    if delegation_statuses:
        # Something was attempted. At least one must have completed.
        return not any(s in _TERMINAL_OK for s in delegation_statuses)

    return False


def detect_long(messages: Sequence[dict], *, threshold: int = LONG_THRESHOLD_DEFAULT) -> bool:
    return len(messages) > threshold


def compute_quality_flags(
    messages: Sequence[dict],
    *,
    delegation_statuses: Sequence[str],
    long_threshold: int = LONG_THRESHOLD_DEFAULT,
) -> list[str]:
    """All signals in one pass. Stable order: escalation, unresolved, long."""
    flags: list[str] = []
    if detect_escalation(messages):
        flags.append("escalation")
    if detect_unresolved(messages, delegation_statuses=delegation_statuses):
        flags.append("unresolved")
    if detect_long(messages, threshold=long_threshold):
        flags.append("long")
    return flags
