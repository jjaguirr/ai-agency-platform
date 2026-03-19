"""Proactive trigger data types and Priority enum."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, Optional


class Priority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class ProactiveTrigger:
    domain: str
    trigger_type: str
    priority: Priority
    title: str
    payload: Dict[str, Any]
    suggested_message: str
    cooldown_key: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "trigger_type": self.trigger_type,
            "priority": self.priority.name,
            "title": self.title,
            "payload": self.payload,
            "suggested_message": self.suggested_message,
            "cooldown_key": self.cooldown_key,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ProactiveTrigger:
        return cls(
            domain=d["domain"],
            trigger_type=d["trigger_type"],
            priority=Priority[d["priority"]],
            title=d["title"],
            payload=d.get("payload", {}),
            suggested_message=d["suggested_message"],
            cooldown_key=d.get("cooldown_key"),
            created_at=datetime.fromisoformat(d["created_at"]),
        )
