"""Configuration for the conversation intelligence layer."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int_env(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float_env(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


@dataclass(frozen=True)
class IntelligenceConfig:
    # Summarization
    summary_idle_threshold_minutes: int = 30
    summary_max_messages: int = 50

    # Quality signals
    escalation_phrases: tuple[str, ...] = (
        "talk to a human",
        "speak to someone",
        "real person",
        "this isn't working",
        "frustrated",
        "cancel my account",
        "useless",
        "terrible",
        "worst",
    )
    long_conversation_threshold_multiplier: float = 1.5

    # Sweep
    sweep_batch_size: int = 10

    @classmethod
    def from_env(cls) -> IntelligenceConfig:
        return cls(
            summary_idle_threshold_minutes=_int_env("INTEL_SUMMARY_IDLE_MINUTES", 30),
            summary_max_messages=_int_env("INTEL_SUMMARY_MAX_MESSAGES", 50),
            long_conversation_threshold_multiplier=_float_env(
                "INTEL_LONG_THRESHOLD_MULTIPLIER", 1.5,
            ),
            sweep_batch_size=_int_env("INTEL_SWEEP_BATCH_SIZE", 10),
        )
