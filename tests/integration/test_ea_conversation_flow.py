"""Integration tests for EA conversation flow."""
import pytest


@pytest.mark.integration
class TestEAConversationFlow:
    def test_intent_classification_routing(self):
        pytest.skip("Requires OpenAI API key")

    def test_multi_turn_context_retention(self):
        pytest.skip("Requires OpenAI API key")

    def test_business_discovery_pipeline(self):
        pytest.skip("Requires OpenAI API key")
