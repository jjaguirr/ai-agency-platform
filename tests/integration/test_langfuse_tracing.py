"""Integration tests for LangFuse observability."""
import pytest


@pytest.mark.integration
class TestLangFuseTracing:
    def test_trace_creation(self):
        pytest.skip("Requires LangFuse service")

    def test_span_recording(self):
        pytest.skip("Requires LangFuse service")

    def test_evaluation_scoring(self):
        pytest.skip("Requires LangFuse service")
