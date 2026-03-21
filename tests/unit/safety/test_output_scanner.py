"""
OutputScanner — redact PII/leak patterns in EA responses before delivery.

The EA has access to business context, domain memories, conversation
history across specialists. Bugs or LLM hallucinations could surface
internal identifiers in customer-facing text. The scanner is the last
line — it runs on every response, redacts matches, logs at WARNING.

Patterns it catches:
  - cross_tenant:   other customers' identifiers (cust_xxx != current)
  - internal_key:   Redis key patterns (conv:, proactive:, audit:)
  - stack_trace:    Python traceback signatures
  - exception_repr: FooError: ... with file/line context
  - raw_structure:  dict reprs containing internal-looking keys

Redact-and-proceed, never block. The customer still gets a response;
it just has [REDACTED] where the leak was.
"""
import logging

import pytest

from src.safety.output_scanner import OutputScanner


@pytest.fixture
def scanner():
    return OutputScanner()


# --- Cross-tenant identifier leak -------------------------------------------

class TestCrossTenant:
    def test_other_customer_id_redacted(self, scanner):
        # Current customer is cust_alice; response mentions cust_bob.
        result = scanner.scan(
            "I found a record for cust_bob in the system.",
            customer_id="cust_alice",
        )
        assert "cust_bob" not in result.clean_text
        assert "[REDACTED]" in result.clean_text
        assert "cross_tenant" in result.redacted_patterns

    def test_own_customer_id_preserved(self, scanner):
        # Mentioning your own ID is fine — not a cross-tenant leak.
        result = scanner.scan(
            "Your account cust_alice is active.",
            customer_id="cust_alice",
        )
        assert "cust_alice" in result.clean_text
        assert "cross_tenant" not in result.redacted_patterns

    def test_multiple_foreign_ids_all_redacted(self, scanner):
        result = scanner.scan(
            "Related: cust_bob and cust_charlie.",
            customer_id="cust_alice",
        )
        assert "cust_bob" not in result.clean_text
        assert "cust_charlie" not in result.clean_text
        assert result.clean_text.count("[REDACTED]") == 2

    def test_customer_id_shaped_word_not_matching_pattern(self, scanner):
        # The pattern is ^[a-z0-9][a-z0-9_-]{2,47}$ — "Customer" doesn't
        # fit (capital C, no numeric/underscore context). Generic words
        # must not trip.
        result = scanner.scan(
            "Customer service is available 24/7.",
            customer_id="cust_alice",
        )
        assert not result.was_redacted


# --- Internal Redis keys ----------------------------------------------------

class TestInternalKeys:
    @pytest.mark.parametrize("key", [
        "conv:abc-123-def",
        "proactive:cust_x:follow_ups",
        "audit:cust_y",
        "ratelimit:cust_z:min:12345",
    ])
    def test_redis_key_pattern_redacted(self, scanner, key):
        result = scanner.scan(f"Debug: checked {key} for data.", customer_id="c")
        assert key not in result.clean_text
        assert "[REDACTED]" in result.clean_text
        assert "internal_key" in result.redacted_patterns

    def test_colon_in_time_not_redacted(self, scanner):
        # "3:30pm" has a colon but isn't a Redis key pattern.
        result = scanner.scan(
            "Your meeting is at 3:30pm tomorrow.",
            customer_id="cust_alice",
        )
        assert "3:30pm" in result.clean_text
        assert not result.was_redacted

    def test_url_with_colon_not_redacted(self, scanner):
        result = scanner.scan(
            "See https://example.com/docs for details.",
            customer_id="cust_alice",
        )
        assert "https://example.com" in result.clean_text
        assert "internal_key" not in result.redacted_patterns


# --- Stack traces -----------------------------------------------------------

class TestStackTraces:
    def test_traceback_redacted_to_end(self, scanner):
        response = (
            "I tried but hit an error: Traceback (most recent call last):\n"
            '  File "/app/src/foo.py", line 42, in bar\n'
            "    raise ValueError('oops')\n"
            "ValueError: oops"
        )
        result = scanner.scan(response, customer_id="cust_alice")
        assert "Traceback" not in result.clean_text
        assert "/app/src/foo.py" not in result.clean_text
        assert "ValueError" not in result.clean_text
        assert "stack_trace" in result.redacted_patterns
        # Preamble before the traceback survives
        assert "I tried but hit an error:" in result.clean_text

    def test_no_traceback_no_redaction(self, scanner):
        result = scanner.scan(
            "I traced back the issue to last week's invoice.",
            customer_id="cust_alice",
        )
        assert not result.was_redacted
        # "traced back" ≠ "Traceback (most recent call last)"


# --- Exception reprs --------------------------------------------------------

class TestExceptionReprs:
    def test_error_with_file_context_redacted(self, scanner):
        result = scanner.scan(
            'Something broke: KeyError: \'customer_id\' at line 123',
            customer_id="cust_alice",
        )
        assert "KeyError" not in result.clean_text
        assert "exception_repr" in result.redacted_patterns

    def test_error_word_in_prose_not_redacted(self, scanner):
        # "error" as a normal word, no Python-repr shape.
        result = scanner.scan(
            "There was an error in the invoice amount.",
            customer_id="cust_alice",
        )
        assert "error" in result.clean_text
        assert not result.was_redacted


# --- Raw structure leaks ----------------------------------------------------

class TestRawStructure:
    def test_dict_repr_with_internal_keys_redacted(self, scanner):
        # The json.dumps fallback in executive_assistant.py:1407 can
        # produce this if summary_for_ea is None and the payload leaks.
        result = scanner.scan(
            "Here's what I found: {'customer_id': 'x', 'conv_key': 'y'}",
            customer_id="cust_alice",
        )
        assert "customer_id" not in result.clean_text
        assert "raw_structure" in result.redacted_patterns

    def test_dict_repr_with_business_keys_preserved(self, scanner):
        # A dict with purely business-domain keys might be intentional
        # formatting ("here's your invoice: {amount: 500, vendor: X}").
        # Only redact if it contains internal-looking keys.
        result = scanner.scan(
            "Invoice: {'amount': 500, 'vendor': 'Acme'}",
            customer_id="cust_alice",
        )
        assert "raw_structure" not in result.redacted_patterns
        assert "amount" in result.clean_text

    def test_json_without_suspicious_keys_preserved(self, scanner):
        result = scanner.scan(
            '{"title": "Q3 Review", "date": "2026-04-01"}',
            customer_id="cust_alice",
        )
        assert not result.was_redacted


# --- Clean responses --------------------------------------------------------

class TestCleanResponses:
    @pytest.mark.parametrize("msg", [
        "Your meeting is scheduled for tomorrow at 3pm.",
        "I've tracked the $500 invoice from Acme Corp.",
        "Your Q3 revenue is up 12% over last quarter.",
        "",
        "Hi! How can I help you today?",
    ])
    def test_normal_response_unchanged(self, scanner, msg):
        result = scanner.scan(msg, customer_id="cust_alice")
        assert result.clean_text == msg
        assert not result.was_redacted
        assert result.redacted_patterns == []


# --- Logging ----------------------------------------------------------------

class TestLogging:
    def test_redaction_logs_warning(self, scanner, caplog):
        with caplog.at_level(logging.WARNING, logger="src.safety.output_scanner"):
            scanner.scan("Leaked: conv:abc-123", customer_id="cust_alice")
        assert any(
            r.levelname == "WARNING" and "redact" in r.message.lower()
            for r in caplog.records
        )

    def test_clean_response_no_warning(self, scanner, caplog):
        with caplog.at_level(logging.WARNING, logger="src.safety.output_scanner"):
            scanner.scan("All good here.", customer_id="cust_alice")
        assert not any(r.levelname == "WARNING" for r in caplog.records)

    def test_warning_includes_customer_id(self, scanner, caplog):
        with caplog.at_level(logging.WARNING, logger="src.safety.output_scanner"):
            scanner.scan("conv:leak-key", customer_id="cust_alice")
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings
        # customer_id should be in the log record (as extra or in message)
        rec = warnings[0]
        assert "cust_alice" in rec.getMessage() or \
               getattr(rec, "customer_id", None) == "cust_alice"


# --- Combined patterns ------------------------------------------------------

class TestCombined:
    def test_multiple_pattern_types_all_redacted(self, scanner):
        response = (
            "Error for cust_bob: Traceback (most recent call last):\n"
            "  File stuff\n"
            "Also see conv:abc-123."
        )
        result = scanner.scan(response, customer_id="cust_alice")
        assert "cust_bob" not in result.clean_text
        assert "Traceback" not in result.clean_text
        # conv:abc-123 was inside the traceback section → already gone.
        # The category list should reflect what was found even if
        # one redaction swallowed another's span.
        assert "cross_tenant" in result.redacted_patterns
        assert "stack_trace" in result.redacted_patterns
