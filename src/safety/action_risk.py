"""Action risk classification.

Classifies specialist actions as LOW, MEDIUM, or HIGH risk based on
domain and action description. HIGH-risk actions require explicit
customer confirmation before execution.
"""
from __future__ import annotations

import re
from enum import Enum


class ActionRisk(str, Enum):
    """Risk level for specialist actions.

    LOW: read-only or query operations — no side effects.
    MEDIUM: state-changing but limited-blast-radius (create, schedule, post).
    HIGH: destructive or high-impact (delete, financial transfer, refund).
          Requires explicit customer confirmation before execution.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Patterns that indicate read-only / query operations (always LOW)
_READ_PATTERNS = re.compile(
    r"\b(?:show|view|check|list|get|look|see|display|find|search|status|balance|metrics|engagement)\b",
    re.IGNORECASE,
)

# Patterns that indicate destructive / high-impact operations (HIGH)
_HIGH_RISK_PATTERNS = re.compile(
    r"\b(?:delete|remove|cancel\s+(?:all|multiple)|transfer|send\s+(?:money|payment)|pay\s+\$|refund|drop|destroy)\b",
    re.IGNORECASE,
)

# Patterns that indicate state-changing but limited-blast-radius operations (MEDIUM)
_MEDIUM_RISK_PATTERNS = re.compile(
    r"\b(?:create|schedule|publish|post|update|modify|change|activate|set|send)\b",
    re.IGNORECASE,
)


def classify_action_risk(domain: str, description: str) -> ActionRisk:
    """Classify the risk level of a specialist action.

    *domain* is accepted for future domain-specific rules (e.g. finance
    actions could be scored more conservatively) but is currently unused —
    classification is purely description-based.

    Evaluation order ensures safe defaults: read-only patterns are checked
    first (→ LOW), then high-risk destructive patterns (→ HIGH), then
    state-changing patterns (→ MEDIUM). If nothing matches, defaults to LOW.
    A description that matches both read and high-risk patterns (e.g.
    "check balance then delete account") is classified HIGH because the
    read-only branch requires no high-risk match.
    """
    # Read-only operations are always safe
    if _READ_PATTERNS.search(description) and not _HIGH_RISK_PATTERNS.search(description):
        return ActionRisk.LOW

    # Destructive / high-impact
    if _HIGH_RISK_PATTERNS.search(description):
        return ActionRisk.HIGH

    # State-changing with limited blast radius
    if _MEDIUM_RISK_PATTERNS.search(description):
        return ActionRisk.MEDIUM

    return ActionRisk.LOW
