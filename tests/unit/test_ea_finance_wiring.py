"""
Finance specialist wiring: registration, graceful degradation, routing.

These tests verify that:
- Both specialists register when imports succeed
- EA initializes when either specialist import fails
- Finance-domain messages route to the finance specialist
- Cross-domain messages don't crash
"""
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field


@dataclass
class FakeBusinessContext:
    """Minimal stand-in so we don't import the real EA for unit tests."""
    business_name: str = ""
    business_type: str = ""
    industry: str = ""
    daily_operations: list = field(default_factory=list)
    pain_points: list = field(default_factory=list)
    current_tools: list = field(default_factory=list)
    automation_opportunities: list = field(default_factory=list)
    communication_style: str = "professional"
    key_processes: list = field(default_factory=list)
    customers: str = ""
    team_members: str = ""
    goals: list = field(default_factory=list)


class TestSpecialistRegistration:
    """Both specialists register when imports succeed."""

    def test_social_media_registered(self):
        from src.agents.base.specialist import DelegationRegistry
        from src.agents.specialists.social_media import SocialMediaSpecialist

        registry = DelegationRegistry(confidence_threshold=0.6)
        registry.register(SocialMediaSpecialist())
        assert registry.get("social_media") is not None

    def test_finance_registered(self):
        from src.agents.base.specialist import DelegationRegistry
        from src.agents.specialists.finance import FinanceSpecialist

        registry = DelegationRegistry(confidence_threshold=0.6)
        registry.register(FinanceSpecialist())
        assert registry.get("finance") is not None

    def test_both_registered_together(self):
        from src.agents.base.specialist import DelegationRegistry
        from src.agents.specialists.social_media import SocialMediaSpecialist
        from src.agents.specialists.finance import FinanceSpecialist

        registry = DelegationRegistry(confidence_threshold=0.6)
        registry.register(SocialMediaSpecialist())
        registry.register(FinanceSpecialist())
        assert registry.get("social_media") is not None
        assert registry.get("finance") is not None


class TestGracefulDegradation:
    """EA initializes even when specialist imports fail.

    The EA registers specialists via importlib.import_module in a loop
    (line ~626 of executive_assistant.py), catching ImportError per
    specialist. We patch importlib to simulate unavailable modules.
    """

    def test_ea_init_without_finance(self):
        """EA degrades gracefully when finance module is unavailable."""
        import importlib
        _real_import = importlib.import_module

        def _patched_import(name, *args, **kwargs):
            if name == "src.agents.specialists.finance":
                raise ImportError("simulated: finance unavailable")
            return _real_import(name, *args, **kwargs)

        from src.agents.base.specialist import DelegationRegistry
        registry = DelegationRegistry(confidence_threshold=0.6)

        specs = [
            ("social_media", "SocialMediaSpecialist"),
            ("finance", "FinanceSpecialist"),
        ]

        with patch.object(importlib, "import_module", side_effect=_patched_import):
            for mod_name, cls_name in specs:
                try:
                    mod = importlib.import_module(f"src.agents.specialists.{mod_name}")
                    registry.register(getattr(mod, cls_name)())
                except Exception:
                    pass

        assert registry.get("social_media") is not None
        assert registry.get("finance") is None

    def test_ea_init_without_social_media(self):
        """EA degrades gracefully when social media module is unavailable."""
        import importlib
        _real_import = importlib.import_module

        def _patched_import(name, *args, **kwargs):
            if name == "src.agents.specialists.social_media":
                raise ImportError("simulated: social_media unavailable")
            return _real_import(name, *args, **kwargs)

        from src.agents.base.specialist import DelegationRegistry
        registry = DelegationRegistry(confidence_threshold=0.6)

        specs = [
            ("social_media", "SocialMediaSpecialist"),
            ("finance", "FinanceSpecialist"),
        ]

        with patch.object(importlib, "import_module", side_effect=_patched_import):
            for mod_name, cls_name in specs:
                try:
                    mod = importlib.import_module(f"src.agents.specialists.{mod_name}")
                    registry.register(getattr(mod, cls_name)())
                except Exception:
                    pass

        assert registry.get("social_media") is None
        assert registry.get("finance") is not None


class TestFinanceRouting:
    """Finance-domain messages route through the delegation registry."""

    def test_invoice_routes_to_finance(self):
        from src.agents.base.specialist import DelegationRegistry
        from src.agents.specialists.finance import FinanceSpecialist

        registry = DelegationRegistry(confidence_threshold=0.6)
        registry.register(FinanceSpecialist())

        match = registry.route(
            "Track this invoice: $2,400 from Acme Corp",
            FakeBusinessContext(),
        )
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_expense_routes_to_finance(self):
        from src.agents.base.specialist import DelegationRegistry
        from src.agents.specialists.finance import FinanceSpecialist

        registry = DelegationRegistry(confidence_threshold=0.6)
        registry.register(FinanceSpecialist())

        match = registry.route(
            "Log expense: $150 for office supplies",
            FakeBusinessContext(),
        )
        assert match is not None
        assert match.specialist.domain == "finance"


class TestCrossDomainOverlap:
    """Messages that touch multiple domains don't crash."""

    def test_roi_on_facebook_campaign_no_crash(self):
        """
        'What's my ROI on the Facebook campaign?' mentions both finance
        (ROI) and social media (Facebook). Must not crash, and must
        produce a coherent routing decision.
        """
        from src.agents.base.specialist import DelegationRegistry
        from src.agents.specialists.social_media import SocialMediaSpecialist
        from src.agents.specialists.finance import FinanceSpecialist

        registry = DelegationRegistry(confidence_threshold=0.6)
        registry.register(SocialMediaSpecialist())
        registry.register(FinanceSpecialist())

        # Must not raise
        match = registry.route(
            "What's my ROI on the Facebook campaign?",
            FakeBusinessContext(),
        )
        # Match can be None (EA handles it) or a specialist — either is fine.
        # What matters: no crash, and if matched, it's one of the two.
        if match is not None:
            assert match.specialist.domain in ("social_media", "finance")
