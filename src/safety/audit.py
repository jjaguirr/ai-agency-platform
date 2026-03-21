"""Redis-backed audit event stream.

Append-only audit log stored as a Redis list per customer.
Follows the Redis patterns in src/proactive/state.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Categories of safety-relevant events.

    Each value maps to a specific layer in the request flow:

    SafetyMiddleware (input):
        INJECTION_DETECTED   — prompt injection score >= medium threshold
                               (logged for both blocked and allowed-through)
        INPUT_REJECTED       — non-injection rejection (length, content type)

    Route handlers (output):
        PII_REDACTION        — OutputPipeline redacted sensitive data from
                               the EA's response before sending to customer

    EA confirmation flow:
        HIGH_RISK_ACTION_REQUESTED  — specialist returned NEEDS_CONFIRMATION
        HIGH_RISK_ACTION_CONFIRMED  — customer approved a HIGH-risk action
        HIGH_RISK_ACTION_DECLINED   — customer declined (or ambiguous response)

    Auth layer:
        AUTH_FAILURE         — invalid or missing JWT token
    """
    INJECTION_DETECTED = "injection_detected"
    HIGH_RISK_ACTION_REQUESTED = "high_risk_action_requested"
    HIGH_RISK_ACTION_CONFIRMED = "high_risk_action_confirmed"
    HIGH_RISK_ACTION_DECLINED = "high_risk_action_declined"
    PII_REDACTION = "pii_redaction"
    INPUT_REJECTED = "input_rejected"
    AUTH_FAILURE = "auth_failure"


@dataclass
class AuditEvent:
    """A single audit record to be appended to a customer's event stream.

    event_type: which safety event occurred (see AuditEventType).
    customer_id: the customer this event belongs to. Events are stored
        in per-customer Redis lists for tenant isolation.
    details: freeform context dict — contents vary by event type (e.g.
        {"rejection_code": "input_too_long", "message_length": 4500}
        for INPUT_REJECTED).
    correlation_id: request correlation ID from CorrelationMiddleware,
        if available. Allows tracing an audit event back to a specific
        HTTP request in logs. None for events outside the request path.
    timestamp: ISO 8601 UTC. Auto-populated by to_dict() if not set.
    """
    event_type: AuditEventType
    customer_id: str
    details: dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "event_type": self.event_type.value,
            "correlation_id": self.correlation_id,
            "customer_id": self.customer_id,
            "details": self.details,
        }


def _key(customer_id: str) -> str:
    """Redis key for a customer's audit stream: ``audit:{customer_id}``."""
    return f"audit:{customer_id}"


class AuditLogger:
    """Append-only audit event stream backed by Redis lists.

    Each customer gets their own list (``audit:{customer_id}``). Events
    are appended via RPUSH and read via LRANGE, giving chronological
    ordering for free. The TTL is refreshed on every write so active
    customers never lose their audit trail.
    """

    def __init__(self, redis_client: Any, *, ttl: int = 2_592_000):
        """*ttl*: seconds before the Redis key expires (default 30 days).
        Override via SafetyConfig.audit_ttl_seconds / SAFETY_AUDIT_TTL."""
        self._r = redis_client
        self._ttl = ttl

    async def log(self, event: AuditEvent) -> None:
        """Append *event* to the customer's audit stream.

        Resets the key TTL on every write — the 30-day window slides
        forward with activity so recent customers keep full history.
        """
        key = _key(event.customer_id)
        data = event.to_dict()
        await self._r.rpush(key, json.dumps(data))
        await self._r.expire(key, self._ttl)

    async def list_events(
        self,
        customer_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return audit events for *customer_id* in chronological order.

        Uses Redis LRANGE for O(offset+limit) pagination. Returns an
        empty list if the customer has no events or *offset* is past
        the end.
        """
        key = _key(customer_id)
        end = offset + limit - 1
        raw = await self._r.lrange(key, offset, end)
        events = []
        for item in raw:
            if isinstance(item, bytes):
                item = item.decode()
            events.append(json.loads(item))
        return events
