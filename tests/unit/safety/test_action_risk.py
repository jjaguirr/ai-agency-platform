"""Tests for ActionRisk classification and NEEDS_CONFIRMATION status."""
import pytest


class TestActionRiskEnum:
    def test_values(self):
        from src.safety.action_risk import ActionRisk
        assert ActionRisk.LOW.value == "low"
        assert ActionRisk.MEDIUM.value == "medium"
        assert ActionRisk.HIGH.value == "high"


class TestNeedsConfirmationStatus:
    def test_enum_value_exists(self):
        from src.agents.base.specialist import SpecialistStatus
        assert SpecialistStatus.NEEDS_CONFIRMATION.value == "needs_confirmation"

    def test_serialization_roundtrip(self):
        from src.agents.base.specialist import SpecialistStatus, SpecialistResult
        result = SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="finance",
            payload={"action": "transfer", "amount": 500},
            confidence=0.9,
            summary_for_ea="Transfer $500 to vendor",
        )
        d = result.to_dict()
        assert d["status"] == "needs_confirmation"
        restored = SpecialistResult.from_dict(d)
        assert restored.status == SpecialistStatus.NEEDS_CONFIRMATION

    def test_existing_statuses_preserved(self):
        """Adding NEEDS_CONFIRMATION must not break existing statuses."""
        from src.agents.base.specialist import SpecialistStatus
        assert SpecialistStatus.COMPLETED.value == "completed"
        assert SpecialistStatus.NEEDS_CLARIFICATION.value == "needs_clarification"
        assert SpecialistStatus.FAILED.value == "failed"


class TestSpecialistResultActionFields:
    def test_action_risk_field(self):
        from src.agents.base.specialist import SpecialistResult, SpecialistStatus
        result = SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="finance",
            payload={},
            confidence=0.9,
            action_risk="high",
            pending_action={"type": "transfer", "amount": 500},
        )
        assert result.action_risk == "high"
        assert result.pending_action == {"type": "transfer", "amount": 500}

    def test_action_fields_default_none(self):
        from src.agents.base.specialist import SpecialistResult, SpecialistStatus
        result = SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain="scheduling",
            payload={},
            confidence=0.8,
        )
        assert result.action_risk is None
        assert result.pending_action is None

    def test_action_fields_serialized(self):
        from src.agents.base.specialist import SpecialistResult, SpecialistStatus
        result = SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="finance",
            payload={},
            confidence=0.9,
            action_risk="high",
            pending_action={"type": "delete_workflow"},
        )
        d = result.to_dict()
        assert d["action_risk"] == "high"
        assert d["pending_action"] == {"type": "delete_workflow"}

        restored = SpecialistResult.from_dict(d)
        assert restored.action_risk == "high"
        assert restored.pending_action == {"type": "delete_workflow"}


class TestClassifyActionRisk:
    @pytest.mark.parametrize("domain,description,expected", [
        ("finance", "transfer $500 to vendor", "high"),
        ("finance", "delete all invoices", "high"),
        ("finance", "show account balance", "low"),
        ("finance", "check payment status", "low"),
        ("scheduling", "cancel all events this week", "high"),
        ("scheduling", "view calendar for tomorrow", "low"),
        ("scheduling", "create a meeting with the team", "medium"),
        ("social_media", "publish post to Instagram", "medium"),
        ("social_media", "check engagement metrics", "low"),
        ("social_media", "delete all scheduled posts", "high"),
    ])
    def test_risk_classification(self, domain, description, expected):
        from src.safety.action_risk import classify_action_risk, ActionRisk
        risk = classify_action_risk(domain, description)
        assert risk == ActionRisk(expected)

    def test_unknown_domain_defaults_low(self):
        from src.safety.action_risk import classify_action_risk, ActionRisk
        risk = classify_action_risk("unknown", "do something")
        assert risk == ActionRisk.LOW

    def test_read_operations_always_low(self):
        from src.safety.action_risk import classify_action_risk, ActionRisk
        for domain in ("finance", "scheduling", "social_media"):
            risk = classify_action_risk(domain, "list all items")
            assert risk == ActionRisk.LOW
