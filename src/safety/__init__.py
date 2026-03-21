"""
Safety layer: input/output scanning, audit, rate limiting, action gates.

The layer sits between untrusted input and EA processing, and between EA
output and customer delivery. Entry points:

  SafetyPipeline   — scan_input / scan_output, called from routes
  AuditLogger      — Redis-backed append-only event log
  RateLimitMiddleware — pure ASGI, runs before auth
  ActionRisk       — specialist action classification
"""
from .config import SafetyConfig
from .models import (
    ActionRisk,
    AuditEvent,
    AuditEventType,
    InjectionScan,
    InputDecision,
    RedactionResult,
    RiskLevel,
)

__all__ = [
    "ActionRisk",
    "AuditEvent",
    "AuditEventType",
    "InjectionScan",
    "InputDecision",
    "RedactionResult",
    "RiskLevel",
    "SafetyConfig",
]
