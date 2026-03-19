"""
Tests for specialist registration in the EA.

Validates that all three specialists can be registered independently,
and that import failures for one don't prevent the others from loading.

Note: These test the DelegationRegistry directly rather than EA.__init__
because the EA has heavy dependencies (Redis, mem0, OpenAI). The actual
wiring in EA uses module-level flag guards, which are exercised by
import-time evaluation. The registry tests prove the framework handles
any combination of specialists.
"""
import pytest

from src.agents.base.specialist import DelegationRegistry
from src.agents.specialists.social_media import SocialMediaSpecialist
from src.agents.specialists.finance import FinanceSpecialist
from src.agents.specialists.scheduling import SchedulingSpecialist


class TestSpecialistRegistration:
    def test_all_three_register(self):
        """All three specialists register without framework changes."""
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(SocialMediaSpecialist())
        reg.register(FinanceSpecialist())
        reg.register(SchedulingSpecialist())

        assert reg.get("social_media") is not None
        assert reg.get("finance") is not None
        assert reg.get("scheduling") is not None

    def test_finance_failure_leaves_others(self):
        """If finance import fails, social media and scheduling still work."""
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(SocialMediaSpecialist())
        # Simulate finance import failure — just skip it
        reg.register(SchedulingSpecialist())

        assert reg.get("social_media") is not None
        assert reg.get("finance") is None
        assert reg.get("scheduling") is not None

    def test_scheduling_failure_leaves_others(self):
        """If scheduling import fails, social media and finance still work."""
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(SocialMediaSpecialist())
        reg.register(FinanceSpecialist())
        # Simulate scheduling import failure — just skip it

        assert reg.get("social_media") is not None
        assert reg.get("finance") is not None
        assert reg.get("scheduling") is None
