"""E2E tests for memory persistence across sessions."""
import pytest


@pytest.mark.e2e
class TestMemoryPersistence:
    def test_business_context_survives_restart(self):
        pytest.skip("Requires full service stack")

    def test_conversation_history_retrieval(self):
        pytest.skip("Requires full service stack")
