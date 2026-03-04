"""E2E tests for customer onboarding flow."""
import pytest


@pytest.mark.e2e
class TestCustomerOnboarding:
    def test_full_onboarding_flow(self):
        """Customer signs up, EA introduces itself, discovers business, creates first automation."""
        pytest.skip("Requires full service stack")

    def test_onboarding_under_60_seconds(self):
        pytest.skip("Requires full service stack")
