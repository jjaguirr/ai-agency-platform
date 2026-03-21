"""Input sanitization pipeline.

Orchestrates content type validation, length checking, and prompt
injection scanning. Synchronous, no I/O — designed to run in middleware.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import SafetyConfig
from .prompt_guard import PromptGuard, PromptGuardResult


@dataclass
class InputCheckResult:
    """Outcome of running a message through the input pipeline.

    allowed: True if the message can proceed to the EA.
    rejection_reason: customer-facing explanation (safe language, no
        internal details). None when allowed.
    rejection_code: machine-readable code for audit/metrics. One of
        "unsupported_content_type", "input_too_long", "high_injection_risk".
    prompt_guard_result: always populated when the pipeline reaches the
        injection check (i.e. text content that passes length). None when
        the pipeline short-circuits on content type or length.
    """
    allowed: bool
    rejection_reason: Optional[str] = None
    rejection_code: Optional[str] = None
    prompt_guard_result: Optional[PromptGuardResult] = None


class InputPipeline:
    """Orchestrates input checks in fail-fast order.

    Check order: content type → length → prompt injection. Each step
    short-circuits on failure so later (more expensive) checks are
    skipped. Synchronous, no I/O — safe to call from ASGI middleware.
    """

    def __init__(self, *, config: SafetyConfig, prompt_guard: PromptGuard):
        self._config = config
        self._guard = prompt_guard

    def check(self, text: str, *, content_type: str = "text") -> InputCheckResult:
        """Run all input checks against *text*.

        The rejection_reason for injection is deliberately vague — it
        redirects the user to legitimate actions rather than revealing
        that injection was detected.
        """
        # 1. Content type
        if content_type != "text":
            return InputCheckResult(
                allowed=False,
                rejection_reason="I can only process text messages right now.",
                rejection_code="unsupported_content_type",
            )

        # 2. Length
        if len(text) > self._config.max_input_length:
            return InputCheckResult(
                allowed=False,
                rejection_reason=(
                    f"Message exceeds maximum length of {self._config.max_input_length} characters."
                ),
                rejection_code="input_too_long",
            )

        # 3. Prompt injection
        guard_result = self._guard.scan(text)
        if guard_result.injection_risk >= self._config.injection_high_threshold:
            return InputCheckResult(
                allowed=False,
                rejection_reason=(
                    "I can help you with scheduling, finances, and business operations. "
                    "What would you like to do?"
                ),
                rejection_code="high_injection_risk",
                prompt_guard_result=guard_result,
            )

        return InputCheckResult(
            allowed=True,
            prompt_guard_result=guard_result,
        )
