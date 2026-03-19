"""
ProactiveTrigger dataclass + Priority enum.

The trigger is the unit the proactive system passes around: a specialist's
proactive_check returns one (or None), the gate evaluates it, the outbound
router delivers it. Tests here cover the contract shape and ordering.
"""
import pytest

from src.agents.proactive.triggers import Priority, ProactiveTrigger


class TestPriority:
    def test_priority_is_totally_ordered(self):
        assert Priority.LOW < Priority.MEDIUM < Priority.HIGH < Priority.URGENT

    def test_priority_supports_min_comparison(self):
        # Gate filters by "priority >= threshold" — must compare cleanly
        assert Priority.HIGH >= Priority.MEDIUM
        assert not (Priority.LOW >= Priority.MEDIUM)

    def test_urgent_is_maximum(self):
        assert max(Priority) == Priority.URGENT


class TestProactiveTriggerShape:
    def test_minimal_trigger(self):
        t = ProactiveTrigger(
            domain="finance",
            trigger_type="anomaly",
            priority=Priority.HIGH,
            title="Spending spike",
            payload={"delta_pct": 42.0},
            suggested_message="Your spending is 42% above baseline this week.",
        )
        assert t.domain == "finance"
        assert t.cooldown_key is None  # default

    def test_cooldown_key_optional(self):
        t = ProactiveTrigger(
            domain="ea",
            trigger_type="briefing",
            priority=Priority.MEDIUM,
            title="Morning briefing",
            payload={},
            suggested_message="Good morning — here's your day.",
            cooldown_key="morning_briefing",
        )
        assert t.cooldown_key == "morning_briefing"

    def test_trigger_is_serializable(self):
        """Triggers flow through Redis (notifications queue) — must round-trip JSON."""
        t = ProactiveTrigger(
            domain="scheduling",
            trigger_type="conflict",
            priority=Priority.URGENT,
            title="Double-booked at 3pm",
            payload={"event_ids": ["e1", "e2"]},
            suggested_message="You have two meetings at 3pm — want me to reschedule one?",
            cooldown_key="conflict:e1:e2",
        )
        d = t.to_dict()
        round = ProactiveTrigger.from_dict(d)
        assert round == t

    def test_sort_by_priority_then_created(self, fixed_now):
        """
        Notifications endpoint orders by priority DESC then created_at ASC.
        The trigger carries a created_at timestamp set at construction.
        """
        from datetime import timedelta

        older_high = ProactiveTrigger(
            domain="a", trigger_type="x", priority=Priority.HIGH,
            title="t", payload={}, suggested_message="m",
            created_at=fixed_now,
        )
        newer_high = ProactiveTrigger(
            domain="a", trigger_type="x", priority=Priority.HIGH,
            title="t", payload={}, suggested_message="m",
            created_at=fixed_now + timedelta(minutes=5),
        )
        urgent = ProactiveTrigger(
            domain="a", trigger_type="x", priority=Priority.URGENT,
            title="t", payload={}, suggested_message="m",
            created_at=fixed_now + timedelta(minutes=10),
        )

        triggers = [newer_high, urgent, older_high]
        ordered = sorted(triggers, key=ProactiveTrigger.sort_key)
        assert ordered == [urgent, older_high, newer_high]
