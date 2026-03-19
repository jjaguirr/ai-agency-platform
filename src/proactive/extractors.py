"""Follow-up extraction — regex-based commitment language parser."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

_DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
    "fri": 4, "sat": 5, "sun": 6,
}

# Patterns that match commitment + deadline
_PATTERNS = [
    # "remind me to X on/by/before Y"
    re.compile(
        r"remind\s+me\s+to\s+(.+?)\s+(?:on|by|before)\s+(.+?)$",
        re.IGNORECASE,
    ),
    # "remind me to X tomorrow"
    re.compile(
        r"remind\s+me\s+to\s+(.+?)\s+(tomorrow)$",
        re.IGNORECASE,
    ),
    # "I'll / I will / I need to / I have to X by/before/on Y"
    re.compile(
        r"I['\u2019]?(?:ll|[\s]+will|[\s]+need\s+to|[\s]+have\s+to)\s+(.+?)\s+(?:by|before|on)\s+(.+?)$",
        re.IGNORECASE,
    ),
    # "verb X by/before/on Y" — with action verbs
    re.compile(
        r"((?:send|submit|deliver|call|email|follow\s+up|finish|complete|prepare|draft|review|check|schedule)\s+.+?)\s+(?:by|before|on)\s+(.+?)$",
        re.IGNORECASE,
    ),
]


@dataclass
class FollowUp:
    id: str
    commitment: str
    deadline: datetime
    source_message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "commitment": self.commitment,
            "deadline": self.deadline.isoformat(),
            "source_message": self.source_message,
            "created_at": self.created_at.isoformat(),
        }


def _resolve_date(text: str, reference: datetime) -> Optional[datetime]:
    """Resolve a natural-language date reference to a datetime."""
    text = text.strip().rstrip(".!?,;").lower()

    if text == "tomorrow":
        d = reference + timedelta(days=1)
        return d.replace(hour=9, minute=0, second=0, microsecond=0)

    if text in ("end of day", "eod", "today"):
        return reference.replace(hour=17, minute=0, second=0, microsecond=0)

    if text in ("end of week", "eow"):
        days_until_friday = (4 - reference.weekday()) % 7 or 7
        d = reference + timedelta(days=days_until_friday)
        return d.replace(hour=17, minute=0, second=0, microsecond=0)

    # "next Monday", "next week"
    next_match = re.match(r"next\s+(\w+)", text)
    if next_match:
        word = next_match.group(1).lower()
        if word == "week":
            d = reference + timedelta(days=(7 - reference.weekday()))
            return d.replace(hour=9, minute=0, second=0, microsecond=0)
        if word in _DAY_NAMES:
            target_dow = _DAY_NAMES[word]
            days_ahead = (target_dow - reference.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # "next X" means next week's X
            d = reference + timedelta(days=days_ahead)
            return d.replace(hour=9, minute=0, second=0, microsecond=0)

    # Plain day name: "Friday", "Monday"
    for name, dow in _DAY_NAMES.items():
        if text == name:
            days_ahead = (dow - reference.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # If today is Friday and they say "Friday", mean next one
            d = reference + timedelta(days=days_ahead)
            return d.replace(hour=9, minute=0, second=0, microsecond=0)

    return None


class FollowUpExtractor:
    def extract(self, message: str, reference_time: datetime) -> List[FollowUp]:
        if not message.strip():
            return []

        results: list[FollowUp] = []
        seen_commitments: set[str] = set()

        for pattern in _PATTERNS:
            for match in pattern.finditer(message):
                commitment = match.group(1).strip()
                date_text = match.group(2).strip()
                deadline = _resolve_date(date_text, reference_time)
                if deadline is None:
                    continue
                # Deduplicate by commitment text
                norm = commitment.lower()
                if norm in seen_commitments:
                    continue
                seen_commitments.add(norm)
                results.append(FollowUp(
                    id=f"fu_{uuid.uuid4().hex[:12]}",
                    commitment=commitment,
                    deadline=deadline,
                    source_message=message,
                ))

        return results
