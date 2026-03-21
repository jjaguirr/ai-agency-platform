"""
Data types for the safety layer.

Everything here is pure data — no I/O, no behavior beyond trivial
derivations. Enums use string values so they serialize cleanly into
Redis-stored JSON audit events without custom encoders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# --- Risk classification ----------------------------------------------------

class RiskLevel(Enum):
    """Input injection risk, derived from PromptGuard's numeric score."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionRisk(Enum):
    """Specialist action blast-radius classification.

    LOW    — read-only. Execute immediately, no mention.
    MEDIUM — reversible state change. Execute, include a "let me know if
             you'd like to change anything" note.
    HIGH   — hard to reverse or high-impact. Require explicit confirmation
             before executing; anything other than a clear yes cancels.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --- Input scanning ---------------------------------------------------------

@dataclass
class InjectionScan:
    """PromptGuard's verdict on one inbound message.

    risk_score is the sum of matched pattern weights, clamped to [0, 1].
    spans are (start, end) character offsets into the scanned message —
    used for MEDIUM-risk stripping so the pipeline can excise the
    suspicious segments and pass the remainder through.
    """
    risk_score: float
    risk_level: RiskLevel
    patterns: List[str]             # category names that matched
    spans: List[Tuple[int, int]]    # char offsets for stripping

    @classmethod
    def clean(cls) -> "InjectionScan":
        return cls(risk_score=0.0, risk_level=RiskLevel.LOW, patterns=[], spans=[])


@dataclass
class InputDecision:
    """What the pipeline tells the route to do with an inbound message.

    proceed=False means: skip the EA entirely, reply with safe_response.
    proceed=True means: call the EA with sanitized_message (which may be
    the original message unchanged, or the original with spans stripped).
    """
    proceed: bool
    sanitized_message: str
    scan: InjectionScan
    safe_response: Optional[str] = None


# --- Output scanning --------------------------------------------------------

@dataclass
class RedactionResult:
    """OutputScanner's verdict on one outbound response.

    clean_text is always safe to send — it's either the original (nothing
    matched) or the original with matches replaced by [REDACTED].
    """
    clean_text: str
    redacted_patterns: List[str]    # category names that fired

    @property
    def was_redacted(self) -> bool:
        return bool(self.redacted_patterns)


# --- Audit ------------------------------------------------------------------

class AuditEventType(Enum):
    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    HIGH_RISK_ACTION_REQUESTED = "high_risk_action_requested"
    HIGH_RISK_ACTION_CONFIRMED = "high_risk_action_confirmed"
    HIGH_RISK_ACTION_DECLINED = "high_risk_action_declined"
    PII_REDACTED = "pii_redacted"
    INPUT_REJECTED = "input_rejected"
    AUTH_FAILURE = "auth_failure"


@dataclass
class AuditEvent:
    """One entry in a customer's audit trail.

    details is event-specific. For injection events it carries
    {risk_score, patterns, message_hash} — never the raw message, which
    may contain PII. For redaction events it carries {patterns}. For
    confirmation events it carries {domain, action}.
    """
    timestamp: str                  # ISO 8601, UTC
    event_type: AuditEventType
    correlation_id: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "correlation_id": self.correlation_id,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AuditEvent":
        return cls(
            timestamp=d["timestamp"],
            event_type=AuditEventType(d["event_type"]),
            correlation_id=d.get("correlation_id", "-"),
            details=d.get("details", {}),
        )
