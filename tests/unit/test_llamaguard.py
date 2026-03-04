"""Unit tests for LlamaGuard safety integration."""
import pytest


class TestLlamaGuard:
    def test_bypass_mode(self):
        """In dev mode, LlamaGuard should pass all content."""
        pytest.skip("Requires LlamaGuard service")

    def test_content_classification(self):
        pytest.skip("Requires LlamaGuard service")

    def test_policy_enforcement(self):
        pytest.skip("Requires LlamaGuard service")
