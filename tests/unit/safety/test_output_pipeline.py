"""Tests for OutputPipeline — PII leak prevention + message splitting."""
import pytest

from src.safety.output_pipeline import OutputPipeline


@pytest.fixture
def pipeline():
    return OutputPipeline()


class TestCrossTenantRedaction:
    def test_other_customer_id_redacted(self, pipeline):
        text = "I found data for cust_other_tenant in the system"
        result = pipeline.sanitize(text, customer_id="cust_mine")
        assert "cust_other_tenant" not in result.text
        assert "[REDACTED]" in result.text
        assert len(result.redactions) > 0

    def test_own_customer_id_not_redacted(self, pipeline):
        text = "Your account cust_mine is active"
        result = pipeline.sanitize(text, customer_id="cust_mine")
        assert "cust_mine" in result.text
        assert result.redactions == []

    def test_multiple_foreign_ids_redacted(self, pipeline):
        text = "Found cust_alice and cust_bob in the database"
        result = pipeline.sanitize(text, customer_id="cust_mine")
        assert "cust_alice" not in result.text
        assert "cust_bob" not in result.text
        assert result.text.count("[REDACTED]") == 2


class TestRedisKeyRedaction:
    @pytest.mark.parametrize("key", [
        "proactive:cust_abc:cooldown:xyz",
        "conv:abc123-def456",
        "audit:cust_test:events",
        "rate:min:cust_test:20260320",
    ])
    def test_redis_keys_redacted(self, pipeline, key):
        text = f"Found key {key} in the cache"
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert key not in result.text
        assert "[REDACTED]" in result.text
        assert len(result.redactions) > 0


class TestStackTraceRedaction:
    def test_python_traceback_redacted(self, pipeline):
        text = (
            "Here is the result:\n"
            'Traceback (most recent call last):\n'
            '  File "/src/agents/ea.py", line 42, in handle\n'
            '    raise ValueError("oops")\n'
            'ValueError: oops'
        )
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert "Traceback" not in result.text
        assert "[REDACTED]" in result.text

    def test_internal_error_class_redacted(self, pipeline):
        text = "redis.exceptions.ConnectionError: Connection refused"
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert "redis.exceptions" not in result.text
        assert "[REDACTED]" in result.text

    def test_asyncpg_error_redacted(self, pipeline):
        text = "asyncpg.PostgresError: relation does not exist"
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert "asyncpg." not in result.text


class TestRawDataRedaction:
    def test_python_dict_repr_redacted(self, pipeline):
        text = "Result: {'customer_id': 'cust_other', 'password': 'secret123'}"
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert "password" not in result.text
        assert "[REDACTED]" in result.text

    def test_json_with_internal_ids_redacted(self, pipeline):
        text = 'Debug: {"conversation_id": "abc-123", "redis_key": "conv:abc"}'
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert "conv:abc" not in result.text
        assert "[REDACTED]" in result.text
        assert len(result.redactions) > 0
        # The redis key pattern should be the one that matched
        assert any("redis_key" in r for r in result.redactions)


class TestCleanOutputPassesThrough:
    def test_normal_response_unchanged(self, pipeline):
        text = "Your meeting is scheduled for tomorrow at 2pm. I'll send a reminder."
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert result.text == text
        assert result.redactions == []

    def test_business_content_unchanged(self, pipeline):
        text = "Your invoice for $500 has been sent to Acme Corp. Payment is due in 30 days."
        result = pipeline.sanitize(text, customer_id="cust_test")
        assert result.text == text
        assert result.redactions == []


class TestWhatsAppSplitting:
    def test_short_message_no_split(self, pipeline):
        text = "Hello, your meeting is tomorrow."
        parts = pipeline.split_for_channel(text, channel="whatsapp", max_length=1600)
        assert parts == [text]

    def test_splits_at_sentence_boundary(self, pipeline):
        sentences = [f"This is a longer sentence number {i} with extra words for padding." for i in range(80)]
        text = " ".join(sentences)
        assert len(text) > 1600
        parts = pipeline.split_for_channel(text, channel="whatsapp", max_length=1600)
        assert all(len(p) <= 1600 for p in parts)
        assert len(parts) > 1
        # Rejoin should reconstruct original
        assert " ".join(parts) == text

    def test_no_split_for_api_channel(self, pipeline):
        text = "a" * 5000
        parts = pipeline.split_for_channel(text, channel="chat", max_length=1600)
        assert parts == [text]

    def test_splits_at_space_when_no_sentence_boundary(self, pipeline):
        # One long sentence with no periods
        text = "word " * 400  # ~2000 chars
        text = text.strip()
        parts = pipeline.split_for_channel(text, channel="whatsapp", max_length=1600)
        assert all(len(p) <= 1600 for p in parts)
        # No mid-word splits
        for part in parts:
            assert not part.startswith(" ")
            assert not part.endswith(" ") or part == parts[-1]

    def test_hard_split_as_last_resort(self, pipeline):
        # Single very long word with no spaces
        text = "a" * 3200
        parts = pipeline.split_for_channel(text, channel="whatsapp", max_length=1600)
        assert all(len(p) <= 1600 for p in parts)
        assert len(parts) == 2
        assert "".join(parts) == text

    def test_preserves_all_content(self, pipeline):
        sentences = [f"This is sentence {i} with some content." for i in range(40)]
        text = " ".join(sentences)
        parts = pipeline.split_for_channel(text, channel="whatsapp", max_length=1600)
        reassembled = " ".join(parts)
        assert reassembled == text

    def test_empty_text(self, pipeline):
        parts = pipeline.split_for_channel("", channel="whatsapp", max_length=1600)
        assert parts == [""]

    def test_exactly_at_limit(self, pipeline):
        text = "a" * 1600
        parts = pipeline.split_for_channel(text, channel="whatsapp", max_length=1600)
        assert parts == [text]
