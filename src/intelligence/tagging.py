"""
Topic tags derived from delegation history.

The signal is already there: if the scheduling specialist ran, the
conversation touched scheduling. No inference needed. Domains map 1:1
to topic tags except `workflows` → `workflow` (dashboard vocabulary
uses the singular).
"""
from __future__ import annotations

from typing import Iterable, Optional


TOPIC_GENERAL = "general"

# Specialist domain → dashboard topic. Identity for everything except
# the plural mismatch. Unknown domains pass through unmapped — better
# a surprising tag than a dropped one.
_DOMAIN_TO_TOPIC = {
    "finance": "finance",
    "scheduling": "scheduling",
    "social_media": "social_media",
    "workflows": "workflow",
}


def tags_from_delegations(domains: Iterable[Optional[str]]) -> list[str]:
    topics = {
        _DOMAIN_TO_TOPIC.get(d, d)
        for d in domains
        if d is not None
    }
    if not topics:
        return [TOPIC_GENERAL]
    return sorted(topics)
