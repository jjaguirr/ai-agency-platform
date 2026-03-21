"""Tests for ProactiveTrigger, Priority enum, and specialist proactive_check extension."""
import pytest
from datetime import datetime, timezone

from src.proactive.triggers import Priority, ProactiveTrigger


class TestPriority:
    def test_ordering(self):
        assert Priority.LOW < Priority.MEDIUM < Priority.HIGH < Priority.URGENT

    def test_comparison_with_threshold(self):
        assert Priority.MEDIUM >= Priority.MEDIUM
        assert Priority.HIGH >= Priority.MEDIUM
        assert not (Priority.LOW >= Priority.MEDIUM)

    def test_urgent_always_above_any_threshold(self):
        for threshold in Priority:
            assert Priority.URGENT >= threshold


class TestProactiveTrigger:
    def test_construction(self):
        trigger = ProactiveTrigger(
            domain="ea",
            trigger_type="morning_briefing",
            priority=Priority.MEDIUM,
            title="Morning Briefing",
            payload={"events": 3},
            suggested_message="Good morning! You have 3 events today.",
            cooldown_key="ea:morning_briefing",
        )
        assert trigger.domain == "ea"
        assert trigger.trigger_type == "morning_briefing"
        assert trigger.priority == Priority.MEDIUM
        assert trigger.payload == {"events": 3}
        assert trigger.cooldown_key == "ea:morning_briefing"
        assert isinstance(trigger.created_at, datetime)

    def test_cooldown_key_defaults_to_none(self):
        trigger = ProactiveTrigger(
            domain="finance",
            trigger_type="anomaly",
            priority=Priority.HIGH,
            title="Spending spike",
            payload={},
            suggested_message="Unusual spending detected.",
        )
        assert trigger.cooldown_key is None

    def test_to_dict_round_trip(self):
        trigger = ProactiveTrigger(
            domain="ea",
            trigger_type="follow_up",
            priority=Priority.HIGH,
            title="Follow up reminder",
            payload={"commitment": "call John"},
            suggested_message="You said you'd call John.",
            cooldown_key="follow_up:abc123",
        )
        d = trigger.to_dict()
        restored = ProactiveTrigger.from_dict(d)
        assert restored.domain == trigger.domain
        assert restored.trigger_type == trigger.trigger_type
        assert restored.priority == trigger.priority
        assert restored.title == trigger.title
        assert restored.payload == trigger.payload
        assert restored.suggested_message == trigger.suggested_message
        assert restored.cooldown_key == trigger.cooldown_key

    def test_to_dict_contains_expected_keys(self):
        trigger = ProactiveTrigger(
            domain="ea",
            trigger_type="briefing",
            priority=Priority.LOW,
            title="Test",
            payload={},
            suggested_message="Test message",
        )
        d = trigger.to_dict()
        assert set(d.keys()) == {
            "domain", "trigger_type", "priority", "title",
            "payload", "suggested_message", "cooldown_key", "created_at",
        }
        assert d["priority"] == "LOW"


class TestSpecialistProactiveCheck:
    """Verify the proactive_check extension is backwards-compatible."""

    def test_existing_specialists_have_default_proactive_check(self):
        """All existing specialists inherit the default (returns None)."""
        from src.agents.base.specialist import SpecialistAgent
        assert hasattr(SpecialistAgent, "proactive_check")

    async def test_default_proactive_check_returns_none(self):
        """A specialist that doesn't override proactive_check returns None."""
        from src.agents.specialists.social_media import SocialMediaSpecialist
        specialist = SocialMediaSpecialist()
        from src.agents.executive_assistant import BusinessContext
        ctx = BusinessContext(business_name="Test")
        result = await specialist.proactive_check("cust_1", ctx)
        assert result is None

    async def test_existing_specialists_work_unchanged(self):
        """Import and assess_task still works — no breakage from the extension."""
        from src.agents.specialists.social_media import SocialMediaSpecialist
        from src.agents.specialists.finance import FinanceSpecialist
        from src.agents.specialists.scheduling import SchedulingSpecialist
        from src.agents.executive_assistant import BusinessContext

        ctx = BusinessContext(business_name="Test Biz")

        social = SocialMediaSpecialist()
        assert social.domain == "social_media"
        assessment = social.assess_task("post on instagram", ctx)
        assert assessment.confidence > 0

        finance = FinanceSpecialist()
        assert finance.domain == "finance"

        sched = SchedulingSpecialist()
        assert sched.domain == "scheduling"

    async def test_delegation_registry_still_routes(self):
        """DelegationRegistry routing is unaffected by the extension."""
        from src.agents.base.specialist import DelegationRegistry
        from src.agents.specialists.social_media import SocialMediaSpecialist
        from src.agents.executive_assistant import BusinessContext

        registry = DelegationRegistry(confidence_threshold=0.3)
        registry.register(SocialMediaSpecialist())
        ctx = BusinessContext(business_name="Test")
        match = registry.route("check my instagram engagement", ctx)
        assert match is not None
        assert match.specialist.domain == "social_media"
