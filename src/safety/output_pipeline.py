"""Output sanitization pipeline.

Scans EA responses for sensitive data leaks (PII, internal IDs, stack traces)
and replaces with [REDACTED]. Also handles message splitting for WhatsApp.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SanitizeResult:
    """Result of output sanitization.

    text: the cleaned response, with sensitive content replaced by
        "[REDACTED]". Safe to send to the customer.
    redactions: list of what was redacted, e.g.
        ["cross_tenant_id:cust_other", "redis_key", "stack_trace"].
        Empty when nothing was redacted. Used by routes to decide
        whether to log a PII_REDACTION audit event.
    """
    text: str
    redactions: list[str] = field(default_factory=list)


# Patterns that indicate internal data leaks.
# Each: (description, compiled regex).
# "description" doubles as the redaction tag in SanitizeResult.redactions.
_LEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Redis key patterns
    ("redis_key", re.compile(
        r"(?:proactive|conv|audit|rate):[a-z0-9_:-]+",
    )),
    # Python traceback
    ("stack_trace", re.compile(
        r"Traceback \(most recent call last\).*?(?:\n\S|\Z)",
        re.DOTALL,
    )),
    # Internal Python error classes
    ("internal_error", re.compile(
        r"(?:redis\.exceptions|asyncpg|psycopg2|sqlalchemy\.exc)\.\w+:?[^\n]*",
    )),
    # Python dict repr with sensitive keys
    ("raw_dict", re.compile(
        r"\{[^}]*(?:'(?:password|secret|token|api_key|customer_id)'|\"(?:password|secret|token|api_key|customer_id)\")[^}]*\}",
    )),
]

# Customer ID pattern — used for cross-tenant detection
_CUSTOMER_ID_RE = re.compile(r"\bcust_[a-z0-9_-]+\b")


class OutputPipeline:
    """Scan EA responses and redact sensitive data."""

    def sanitize(self, text: str, *, customer_id: str) -> SanitizeResult:
        """Scan *text* for sensitive data and replace matches with [REDACTED].

        *customer_id* is the current customer — their own ID is allowed
        through (it's their data), but any other ``cust_*`` ID is treated
        as a cross-tenant leak.

        Side effect: logs at WARNING when redactions occur.
        """
        redactions: list[str] = []
        result = text

        # 1. Cross-tenant customer ID leak
        for match in _CUSTOMER_ID_RE.finditer(result):
            found_id = match.group()
            if found_id != customer_id:
                redactions.append(f"cross_tenant_id:{found_id}")

        if redactions:
            result = _CUSTOMER_ID_RE.sub(
                lambda m: m.group() if m.group() == customer_id else "[REDACTED]",
                result,
            )

        # 2. Internal data leak patterns
        for description, pattern in _LEAK_PATTERNS:
            matches = pattern.findall(result)
            if matches:
                redactions.extend(f"{description}" for _ in matches)
                result = pattern.sub("[REDACTED]", result)

        if redactions:
            logger.warning(
                "PII/data leak redacted: %d patterns found",
                len(redactions),
            )

        return SanitizeResult(text=result, redactions=redactions)

    def split_for_channel(
        self, text: str, *, channel: str, max_length: int = 1600,
    ) -> list[str]:
        """Split response for channel limits. Only WhatsApp gets split."""
        if channel != "whatsapp" or len(text) <= max_length:
            return [text]

        parts: list[str] = []
        remaining = text

        while len(remaining) > max_length:
            chunk = remaining[:max_length]

            # Try sentence boundary (. ! ? followed by space)
            split_idx = -1
            for sep in (". ", "! ", "? ", "\n"):
                idx = chunk.rfind(sep)
                if idx > 0 and idx > split_idx:
                    split_idx = idx + len(sep) - 1  # include the punctuation

            if split_idx > max_length // 2:
                # Good sentence boundary found in the back half
                parts.append(remaining[:split_idx + 1].rstrip())
                remaining = remaining[split_idx + 1:].lstrip()
                continue

            # Try space boundary
            space_idx = chunk.rfind(" ")
            if space_idx > 0:
                parts.append(remaining[:space_idx])
                remaining = remaining[space_idx + 1:]
                continue

            # Hard split — no spaces at all
            parts.append(remaining[:max_length])
            remaining = remaining[max_length:]

        if remaining:
            parts.append(remaining)

        return parts
