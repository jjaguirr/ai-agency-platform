"""
SafetyPipeline — the one object routes call before and after the EA.

Lives on app.state. Two entry points:

  scan_input(message, customer_id)  → InputDecision
  scan_output(response, customer_id) → str

The decision object tells the route what to do. HIGH risk means skip
the EA entirely and reply with a canned fallback (proceed=False). MEDIUM
means excise the matched spans and pass the remainder through. LOW means
pass the original through untouched.

Length is checked before the guard runs — no point pattern-scanning a
message we're about to reject on size. Over-limit raises rather than
returns a decision because it's a client error (422), not a safety
intervention; the route's exception handler turns it into the standard
{type, detail} body.

Every safety-relevant outcome audits. Audit is best-effort: if the
AuditLogger is None (tests, or Redis unavailable at construction) the
pipeline still scans.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from src.api.errors import MessageTooLongError
from src.api.middleware import correlation_id

from .audit import AuditLogger, hash_message
from .config import SafetyConfig
from .models import (
    AuditEvent,
    AuditEventType,
    InjectionScan,
    InputDecision,
    RiskLevel,
)
from .output_scanner import OutputScanner
from .prompt_guard import PromptGuard


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_spans(message: str, spans: List[Tuple[int, int]]) -> str:
    """Excise character ranges from a string.

    Spans come from regex .finditer() across multiple patterns, so they
    may overlap or arrive out of order. Merge-then-cut is simpler than
    trying to excise each independently and tracking index shifts.
    """
    if not spans:
        return message

    # Merge overlapping / adjacent spans.
    merged: List[List[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    # Walk the keep-segments between merged spans.
    parts: List[str] = []
    cursor = 0
    for start, end in merged:
        parts.append(message[cursor:start])
        cursor = end
    parts.append(message[cursor:])

    # Normalize whitespace where excision left doubled spaces or gaps.
    # The EA should see "Hello there. Thanks!" not "Hello there.  . Thanks!"
    return re.sub(r"\s+", " ", "".join(parts)).strip()


class SafetyPipeline:
    def __init__(self, config: SafetyConfig, audit: Optional[AuditLogger]) -> None:
        self._config = config
        self._audit = audit
        self._guard = PromptGuard(
            medium_threshold=config.injection_medium_threshold,
            high_threshold=config.injection_high_threshold,
        )
        self._scanner = OutputScanner()

    @property
    def audit(self) -> Optional[AuditLogger]:
        """Exposed so the /v1/audit route can reach list_events()."""
        return self._audit

    # --- Input --------------------------------------------------------------

    async def scan_input(self, message: str, customer_id: str) -> InputDecision:
        # Length gate first. Over-limit is a client error, not an
        # injection signal — raise so the APIError handler responds 422.
        if len(message) > self._config.max_message_length:
            await self._log(customer_id, AuditEventType.INPUT_REJECTED, {
                "reason": "message_too_long",
                "length": len(message),
                "limit": self._config.max_message_length,
            })
            raise MessageTooLongError(
                length=len(message),
                limit=self._config.max_message_length,
            )

        scan = self._guard.scan(message)

        if scan.risk_level is RiskLevel.HIGH:
            await self._log_injection(customer_id, message, scan)
            return InputDecision(
                proceed=False,
                sanitized_message=message,  # unused when proceed=False
                scan=scan,
                safe_response=self._config.safe_fallback_response,
            )

        if scan.risk_level is RiskLevel.MEDIUM:
            await self._log_injection(customer_id, message, scan)
            return InputDecision(
                proceed=True,
                sanitized_message=_strip_spans(message, scan.spans),
                scan=scan,
            )

        # LOW — pass through. No audit; the vast majority of traffic
        # lands here and we'd drown the trail in noise.
        return InputDecision(
            proceed=True,
            sanitized_message=message,
            scan=scan,
        )

    # --- Output -------------------------------------------------------------

    async def scan_output(self, response: str, customer_id: str) -> str:
        result = self._scanner.scan(response, customer_id)
        if result.was_redacted:
            await self._log(customer_id, AuditEventType.PII_REDACTED, {
                "patterns": result.redacted_patterns,
            })
        return result.clean_text

    # --- Audit helpers ------------------------------------------------------

    async def _log_injection(
        self, customer_id: str, message: str, scan: InjectionScan,
    ) -> None:
        await self._log(customer_id, AuditEventType.PROMPT_INJECTION_DETECTED, {
            "risk_score": scan.risk_score,
            "risk_level": scan.risk_level.value,
            "patterns": scan.patterns,
            # Stable identifier for cross-system correlation without
            # putting the message itself — which may contain real PII
            # alongside the injection attempt — into the audit log.
            "message_hash": hash_message(message),
        })

    async def _log(
        self, customer_id: str, event_type: AuditEventType, details: dict,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.log(customer_id, AuditEvent(
            timestamp=_now_iso(),
            event_type=event_type,
            correlation_id=correlation_id.get() or "-",
            details=details,
        ))
