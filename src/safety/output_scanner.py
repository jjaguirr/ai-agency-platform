"""
OutputScanner — redact leak patterns in EA responses before delivery.

Runs on every outbound response. Redacts and proceeds — never blocks.
The customer still gets a reply; it has [REDACTED] where the leak was.
Every redaction logs at WARNING with the correlation ID so ops can
trace back to the request that produced the leak.

Pattern order matters: stack traces are redacted first (they consume
everything from the Traceback header to end-of-string, which may
swallow other matches — that's fine, the whole block is a leak). Then
the narrow patterns run on what remains.
"""
from __future__ import annotations

import logging
import re
from typing import List

from .models import RedactionResult

logger = logging.getLogger(__name__)

_REDACTED = "[REDACTED]"

# Customer ID pattern — mirrors _CUSTOMER_ID_PATTERN in src/api/schemas.py:22.
# Used to find tokens that *look* like customer IDs so we can check them
# against the current customer. The pattern there is an anchored full-
# string match; here we want to find occurrences mid-text, so we require
# a cust_ prefix (the de-facto naming convention in this codebase — see
# tests/unit/api/conftest.py:29, auth tests, etc.) and word boundaries.
# Without the cust_ anchor a regex this broad would match most words.
_CUSTOMER_ID_TOKEN = re.compile(r"\bcust_[a-z0-9_-]{1,44}\b")

# Internal Redis key patterns. The prefixes are the ones actually used
# in this codebase: src/agents/executive_assistant.py ("conv:"),
# src/proactive/state.py ("proactive:"), and this safety layer itself
# ("audit:", "ratelimit:"). Matching requires prefix + colon + at least
# one key-character, which excludes "3:30pm" (digit prefix not in set)
# and URLs (protocol before the colon doesn't match any prefix).
_INTERNAL_KEY = re.compile(
    r"\b(?:conv|proactive|audit|ratelimit):[a-zA-Z0-9:_-]+"
)

# Python traceback header. Once we see this, everything from here to
# the end of the response is redacted — tracebacks are multi-line and
# the whole thing is a leak.
_TRACEBACK_HEADER = re.compile(r"Traceback \(most recent call last\):")

# Exception repr: FooError: ... followed by something file-line-ish.
# The "at line" / "in file" / quoted path suffix is what distinguishes
# a Python repr from prose like "there was an error in the invoice."
_EXCEPTION_REPR = re.compile(
    r"\b[A-Z]\w*Error:\s+[^.\n]*"
    r"(?:at\s+line\s+\d+|in\s+file|\"[/\\][^\"]*\"|'\w+')"
)

# Raw dict/JSON repr containing internal-looking keys. We only redact
# if the structure contains one of these field names — a legitimate
# business-domain dict ({"amount": 500, "vendor": "Acme"}) is fine.
# The pattern matches from the opening brace through the closing brace
# non-greedily, but only fires if a suspicious key appears inside.
_SUSPICIOUS_KEYS = (
    "customer_id", "conv_key", "conversation_id", "redis",
    "_id", "db_key", "session_key",
)
_RAW_STRUCTURE = re.compile(
    r"\{[^{}]*?(?:" + "|".join(re.escape(k) for k in _SUSPICIOUS_KEYS) + r")[^{}]*\}",
    re.IGNORECASE,
)


class OutputScanner:
    """Stateless — patterns are module-level constants."""

    __slots__ = ()

    def scan(self, response: str, customer_id: str) -> RedactionResult:
        if not response:
            return RedactionResult(clean_text=response, redacted_patterns=[])

        clean = response
        fired: List[str] = []

        # --- Stack traces first ---------------------------------------------
        # These consume to end-of-string, so do them before narrower
        # patterns that might otherwise find matches inside the traceback.
        m = _TRACEBACK_HEADER.search(clean)
        if m:
            clean = clean[:m.start()] + _REDACTED
            fired.append("stack_trace")

        # --- Cross-tenant IDs -----------------------------------------------
        # Search on the original response, not the cleaned one — if a
        # foreign ID was inside the traceback we already redacted, we
        # still want to record that cross_tenant fired (the audit trail
        # should show both categories).
        foreign_ids = [
            tok for tok in _CUSTOMER_ID_TOKEN.findall(response)
            if tok != customer_id
        ]
        if foreign_ids:
            fired.append("cross_tenant")
            for fid in set(foreign_ids):
                clean = clean.replace(fid, _REDACTED)

        # --- Internal keys --------------------------------------------------
        if _INTERNAL_KEY.search(response):
            fired.append("internal_key")
            clean = _INTERNAL_KEY.sub(_REDACTED, clean)

        # --- Exception reprs ------------------------------------------------
        if _EXCEPTION_REPR.search(response):
            fired.append("exception_repr")
            clean = _EXCEPTION_REPR.sub(_REDACTED, clean)

        # --- Raw structures with internal keys ------------------------------
        if _RAW_STRUCTURE.search(response):
            fired.append("raw_structure")
            clean = _RAW_STRUCTURE.sub(_REDACTED, clean)

        if fired:
            self._log_redaction(customer_id, fired)

        return RedactionResult(clean_text=clean, redacted_patterns=fired)

    @staticmethod
    def _log_redaction(customer_id: str, patterns: List[str]) -> None:
        # correlation_id is injected into every LogRecord by the
        # factory installed in src/api/middleware.py:23-42. We don't
        # need to pass it explicitly — it's on the record.
        logger.warning(
            "Output redaction fired for customer=%s patterns=%s",
            customer_id,
            ",".join(patterns),
            extra={"customer_id": customer_id},
        )
