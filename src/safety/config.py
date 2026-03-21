"""
Safety layer configuration.

Same dataclass + .from_env() pattern as RedisConfig in src/utils/config.py.
All limits are configurable so ops can tune without a code change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class SafetyConfig:
    # --- Input limits -------------------------------------------------------
    # Messages longer than this are rejected with 422 before reaching the EA.
    # WhatsApp has its own limit (~4096 for Twilio body) but the API doesn't.
    max_message_length: int = 4000

    # --- Injection thresholds ----------------------------------------------
    # PromptGuard risk_score is [0, 1]. HIGH → safe-fallback response,
    # MEDIUM → strip + proceed, LOW → pass through unchanged.
    injection_high_threshold: float = 0.7
    injection_medium_threshold: float = 0.3

    # --- Rate limits --------------------------------------------------------
    # Per-customer: sliding-ish fixed window via INCR+EXPIRE. Exceeding
    # either returns 429 with Retry-After. Global protects the process —
    # exceeding returns 503.
    rate_per_minute: int = 30
    rate_per_day: int = 500
    rate_global_per_second: int = 200

    # --- Output splitting ---------------------------------------------------
    # Twilio's documented max body length for WhatsApp is 1600 characters.
    # Responses exceeding this get split at sentence boundaries.
    whatsapp_max_chars: int = 1600

    # --- Audit --------------------------------------------------------------
    # LTRIM cap — audit lists are per-customer, but a noisy tenant
    # shouldn't grow Redis unbounded. Oldest events fall off the front.
    audit_max_events: int = 10_000

    # --- Safe fallback ------------------------------------------------------
    # What the EA says when a HIGH-risk injection is detected. Generic,
    # reveals nothing about what was detected or why.
    safe_fallback_response: str = (
        "I can help you with scheduling, finances, and business operations. "
        "What would you like to do?"
    )

    @classmethod
    def from_env(cls) -> "SafetyConfig":
        return cls(
            max_message_length=_int_env("SAFETY_MAX_MESSAGE_LENGTH", 4000),
            injection_high_threshold=_float_env("SAFETY_INJECTION_HIGH", 0.7),
            injection_medium_threshold=_float_env("SAFETY_INJECTION_MEDIUM", 0.3),
            rate_per_minute=_int_env("SAFETY_RATE_PER_MINUTE", 30),
            rate_per_day=_int_env("SAFETY_RATE_PER_DAY", 500),
            rate_global_per_second=_int_env("SAFETY_RATE_GLOBAL_PER_SECOND", 200),
            whatsapp_max_chars=_int_env("SAFETY_WHATSAPP_MAX_CHARS", 1600),
            audit_max_events=_int_env("SAFETY_AUDIT_MAX_EVENTS", 10_000),
        )
