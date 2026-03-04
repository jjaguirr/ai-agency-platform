"""E2E tests for workflow creation from conversation."""
import pytest


@pytest.mark.e2e
class TestWorkflowCreation:
    def test_social_media_automation_workflow(self):
        pytest.skip("Requires full service stack")

    def test_email_followup_workflow(self):
        pytest.skip("Requires full service stack")

    def test_invoice_generation_workflow(self):
        pytest.skip("Requires full service stack")
