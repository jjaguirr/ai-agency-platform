"""
ProactiveTrigger — the unit the proactive system passes around.

A specialist's proactive_check returns one (or None), the gate evaluates
it, the outbound router delivers it. JSON-serializable so it can sit in
the Redis notifications queue between the heartbeat tick that produced
it and the HTTP pull that drains it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, Optional


class Priority(IntEnum):
    """Totally ordered. URGENT short-circuits the gate's soft filters
    (quiet hours, daily cap) — never cooldown, which is a correctness
    guard not a volume guard."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProactiveTrigger:
    domain: str
    trigger_type: str  # briefing | conflict | anomaly | follow_up | suggestion
    priority: Priority
    title: str
    payload: Dict[str, Any]
    suggested_message: str
    cooldown_key: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)

    # --- Serialisation -----------------------------------------------------
    # Triggers round-trip through Redis as JSON. Priority is serialised as
    # its int value (not name) so the ordering survives without a lookup
    # table. created_at is ISO-8601.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "trigger_type": self.trigger_type,
            "priority": int(self.priority),
            "title": self.title,
            "payload": self.payload,
            "suggested_message": self.suggested_message,
            "cooldown_key": self.cooldown_key,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProactiveTrigger":
        return cls(
            domain=d["domain"],
            trigger_type=d["trigger_type"],
            priority=Priority(d["priority"]),
            title=d["title"],
            payload=d.get("payload", {}),
            suggested_message=d["suggested_message"],
            cooldown_key=d.get("cooldown_key"),
            created_at=datetime.fromisoformat(d["created_at"]),
        )

    # --- Ordering ----------------------------------------------------------
    # Notifications endpoint contract: priority DESC, then created_at ASC.
    # Sort key is a tuple; Python's tuple ordering gives us the composite.
    # Negate priority for DESC within an ascending sort.

    @staticmethod
    def sort_key(t: "ProactiveTrigger") -> tuple:
        return (-int(t.priority), t.created_at)
