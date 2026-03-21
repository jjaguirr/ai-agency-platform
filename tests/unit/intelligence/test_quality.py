"""
Quality signal detection — pure functions, no I/O.

Three signals, all heuristic:
  escalation  — keyword match on user messages ("talk to a human" etc.)
  unresolved  — last message is a customer question AND no delegation
                finished COMPLETED
  long        — turn count exceeds a per-topic threshold

These are hints for dashboard triage, not ground truth. False positives
are cheap (someone looks at a fine conversation); false negatives mean a
bad interaction goes unreviewed. Bias toward recall.
"""
import pytest

from src.intelligence.quality import (
    detect_escalation,
    detect_unresolved,
    detect_long,
    compute_quality_flags,
    LONG_THRESHOLD_DEFAULT,
)


# ─── escalation ────────────────────────────────────────────────────────────

class TestEscalation:
    @pytest.mark.parametrize("text", [
        "I want to talk to a human",
        "Can I speak to a real person?",
        "this is useless",
        "THIS IS RIDICULOUS",
        "I'm so frustrated with this",
        "talk to a human please",
        "get me a real person",
        "is there a human I can talk to",
    ])
    def test_escalation_phrases_detected(self, text):
        msgs = [{"role": "user", "content": text}]
        assert detect_escalation(msgs) is True

    @pytest.mark.parametrize("text", [
        "thanks, that was helpful",
        "can you check my calendar",
        "schedule a meeting with the human resources team",  # "human" ≠ escalation
        "send the invoice to a real person at acme corp",     # "real person" in context
        "",
    ])
    def test_benign_phrases_pass(self, text):
        msgs = [{"role": "user", "content": text}]
        assert detect_escalation(msgs) is False

    def test_only_scans_user_messages(self):
        # Assistant apologising shouldn't self-flag.
        msgs = [
            {"role": "user", "content": "check my schedule"},
            {"role": "assistant", "content": "I'm frustrated I can't find it, let me talk to a human colleague"},
        ]
        assert detect_escalation(msgs) is False

    def test_any_user_message_triggers(self):
        # Not just the last one — frustration early in a long conv still counts.
        msgs = [
            {"role": "user", "content": "this is useless"},
            {"role": "assistant", "content": "Let me try again"},
            {"role": "user", "content": "ok thanks that worked"},
        ]
        assert detect_escalation(msgs) is True

    def test_empty_conversation(self):
        assert detect_escalation([]) is False


# ─── unresolved ────────────────────────────────────────────────────────────

class TestUnresolved:
    def test_last_message_is_user_question_no_completion(self):
        msgs = [
            {"role": "user", "content": "can you check my invoices?"},
            {"role": "assistant", "content": "Which month?"},
            {"role": "user", "content": "march"},
        ]
        # Customer said something, nothing came back, no specialist completed.
        assert detect_unresolved(msgs, delegation_statuses=[]) is True

    def test_assistant_replied_last(self):
        msgs = [
            {"role": "user", "content": "check my invoices"},
            {"role": "assistant", "content": "You have 3 outstanding, total $4,200."},
        ]
        assert detect_unresolved(msgs, delegation_statuses=["completed"]) is False

    def test_assistant_replied_but_no_delegation_completed(self):
        # EA gave a generic reply but the specialist failed. Still unresolved —
        # the customer asked for something concrete and didn't get it.
        msgs = [
            {"role": "user", "content": "send the invoice to acme"},
            {"role": "assistant", "content": "I'm having trouble with that right now."},
        ]
        assert detect_unresolved(msgs, delegation_statuses=["failed"]) is True

    def test_no_delegations_assistant_answered(self):
        # General Q&A, no specialist involved, assistant answered. Resolved.
        msgs = [
            {"role": "user", "content": "what can you help me with"},
            {"role": "assistant", "content": "I handle scheduling, finance, social media..."},
        ]
        assert detect_unresolved(msgs, delegation_statuses=[]) is False

    def test_mixed_statuses_with_completion(self):
        # One failed, one completed → resolved overall.
        msgs = [
            {"role": "user", "content": "check calendar and send invoice"},
            {"role": "assistant", "content": "Calendar is clear. Invoice sent."},
        ]
        assert detect_unresolved(msgs, delegation_statuses=["failed", "completed"]) is False

    def test_needs_clarification_left_hanging(self):
        # Specialist asked for clarification, customer never replied.
        # Last message is assistant (the question) but status is not completed.
        msgs = [
            {"role": "user", "content": "schedule a meeting"},
            {"role": "assistant", "content": "With whom?"},
        ]
        assert detect_unresolved(msgs, delegation_statuses=["needs_clarification"]) is True

    def test_empty_conversation(self):
        assert detect_unresolved([], delegation_statuses=[]) is False


# ─── long ──────────────────────────────────────────────────────────────────

class TestLong:
    def test_under_threshold(self):
        msgs = [{"role": "user", "content": "x"}] * (LONG_THRESHOLD_DEFAULT - 1)
        assert detect_long(msgs) is False

    def test_at_threshold_is_not_long(self):
        # Strictly greater-than. Boundary belongs to "normal".
        msgs = [{"role": "user", "content": "x"}] * LONG_THRESHOLD_DEFAULT
        assert detect_long(msgs) is False

    def test_over_threshold(self):
        msgs = [{"role": "user", "content": "x"}] * (LONG_THRESHOLD_DEFAULT + 1)
        assert detect_long(msgs) is True

    def test_custom_threshold(self):
        msgs = [{"role": "user", "content": "x"}] * 5
        assert detect_long(msgs, threshold=3) is True
        assert detect_long(msgs, threshold=10) is False

    def test_empty(self):
        assert detect_long([]) is False


# ─── aggregate ─────────────────────────────────────────────────────────────

class TestComputeQualityFlags:
    def test_all_clear(self):
        msgs = [
            {"role": "user", "content": "check my calendar"},
            {"role": "assistant", "content": "You're free all day."},
        ]
        assert compute_quality_flags(msgs, delegation_statuses=["completed"]) == []

    def test_all_flags(self):
        msgs = [{"role": "user", "content": "this is useless"}] * 30
        flags = compute_quality_flags(msgs, delegation_statuses=["failed"])
        assert set(flags) == {"escalation", "unresolved", "long"}

    def test_stable_ordering(self):
        # Dashboard filtering relies on consistent flag names, and a stable
        # order makes test diffs readable.
        msgs = [{"role": "user", "content": "I want a real person"}] * 30
        flags = compute_quality_flags(msgs, delegation_statuses=[])
        assert flags == ["escalation", "unresolved", "long"]

    def test_only_escalation(self):
        msgs = [
            {"role": "user", "content": "talk to a human"},
            {"role": "assistant", "content": "I'll connect you."},
        ]
        # Assistant replied, no delegations → not unresolved. Short. Just escalation.
        assert compute_quality_flags(msgs, delegation_statuses=[]) == ["escalation"]
