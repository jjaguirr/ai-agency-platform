"""Rule-based conversation quality signal detection.

No LLM needed — purely heuristic. Configured via IntelligenceConfig.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import IntelligenceConfig


@dataclass
class QualitySignals:
    escalation: bool = False
    escalation_phrases: list[str] = field(default_factory=list)
    unresolved: bool = False
    long: bool = False

    def to_dict(self) -> dict:
        return {
            "escalation": self.escalation,
            "escalation_phrases": self.escalation_phrases,
            "unresolved": self.unresolved,
            "long": self.long,
        }


class QualityAnalyzer:

    def __init__(self, config: IntelligenceConfig):
        self._phrases = config.escalation_phrases
        self._long_multiplier = config.long_conversation_threshold_multiplier

    def analyze(
        self,
        *,
        messages: list[dict[str, str]],
        delegation_statuses: list[str],
        avg_turns: Optional[float] = None,
    ) -> QualitySignals:
        escalation, phrases = self._check_escalation(messages)
        unresolved = self._check_unresolved(messages, delegation_statuses)
        long = self._check_long(messages, avg_turns)

        return QualitySignals(
            escalation=escalation,
            escalation_phrases=phrases,
            unresolved=unresolved,
            long=long,
        )

    def _check_escalation(
        self, messages: list[dict[str, str]],
    ) -> tuple[bool, list[str]]:
        found: list[str] = []
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content_lower = msg.get("content", "").lower()
            for phrase in self._phrases:
                if phrase in content_lower and phrase not in found:
                    found.append(phrase)
        return bool(found), found

    def _check_unresolved(
        self,
        messages: list[dict[str, str]],
        delegation_statuses: list[str],
    ) -> bool:
        if not messages:
            return True
        # Last message from user = customer left hanging
        if messages[-1].get("role") == "user":
            return True
        # No delegation completed successfully
        if delegation_statuses and "completed" not in delegation_statuses:
            return True
        return False

    def _check_long(
        self,
        messages: list[dict[str, str]],
        avg_turns: Optional[float],
    ) -> bool:
        if avg_turns is None or avg_turns <= 0:
            return False
        return len(messages) > avg_turns * self._long_multiplier
