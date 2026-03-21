"""Heuristic prompt injection scanner.

Deterministic, no LLM calls, < 5ms per scan. Scans inbound messages for
known injection patterns and returns a risk score with matched categories.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PromptGuardResult:
    """Result of a prompt injection scan.

    injection_risk: 0.0–1.0 aggregate score. Sum of the highest-weight
        match per category, clamped. <0.3 = clean, 0.3–0.7 = suspicious
        (logged, not blocked), >=0.7 = high risk (blocked by InputPipeline).
    injection_patterns: sorted list of matched category names, e.g.
        ["delimiter_injection", "instruction_override"].
    """
    injection_risk: float = 0.0
    injection_patterns: list[str] = field(default_factory=list)


# Each entry: (category_name, compiled_regex, weight).
# Score = sum of max weight per category, clamped to [0, 1].
#
# Weights reflect how confidently the pattern indicates an actual attack
# vs. accidental phrasing. Token-level patterns (delimiter_injection with
# special tokens like <|endoftext|>) get 0.40 because they never appear
# in legitimate business messages. Instruction overrides get 0.35 because
# phrases like "ignore previous" are rare but possible in benign context.
# System prompt extraction gets 0.25–0.30 because "what are your rules"
# can be an innocent question about business policies.
_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    # --- instruction_override ---
    ("instruction_override", re.compile(
        r"ignore\s+(all\s+)?previous\s+(instructions|prompts|rules)",
        re.IGNORECASE,
    ), 0.35),
    ("instruction_override", re.compile(
        r"disregard\s+(all\s+)?(prior|previous|above)\s+(instructions|prompts|rules|context)",
        re.IGNORECASE,
    ), 0.35),
    ("instruction_override", re.compile(
        r"(?:new|override|replace)\s+instructions\s*:",
        re.IGNORECASE,
    ), 0.30),
    ("instruction_override", re.compile(
        r"forget\s+(your|all|previous)\s+(instructions|rules|prompts)",
        re.IGNORECASE,
    ), 0.35),
    ("instruction_override", re.compile(
        r"ignore\s+(all\s+)?(?:prior|above)\s+(?:prompts|text|context)",
        re.IGNORECASE,
    ), 0.30),

    # --- role_manipulation ---
    ("role_manipulation", re.compile(
        r"you\s+are\s+now\s+(?:a\s+)?(?!here|ready|connected)",
        re.IGNORECASE,
    ), 0.30),
    ("role_manipulation", re.compile(
        r"pretend\s+(?:you\s+are|to\s+be)\b",
        re.IGNORECASE,
    ), 0.30),
    ("role_manipulation", re.compile(
        r"(?:as\s+an?\s+)?(?:admin(?:istrator)?|root|superuser)\s*[,:]?\s*(?:show|give|list|reveal|display)",
        re.IGNORECASE,
    ), 0.35),
    ("role_manipulation", re.compile(
        r"switch\s+to\s+(?:developer|admin|debug|unrestricted|god)\s+mode",
        re.IGNORECASE,
    ), 0.35),
    ("role_manipulation", re.compile(
        r"you'?re\s+now\s+(?:in\s+)?(?:unrestricted|jailbreak|DAN|evil)",
        re.IGNORECASE,
    ), 0.35),

    # --- system_prompt_extraction ---
    ("system_prompt_extraction", re.compile(
        r"(?:print|show|display|reveal|output|repeat)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions|rules)",
        re.IGNORECASE,
    ), 0.30),
    ("system_prompt_extraction", re.compile(
        r"what\s+are\s+your\s+(?:initial\s+)?(?:instructions|rules|directives|guidelines)",
        re.IGNORECASE,
    ), 0.30),
    ("system_prompt_extraction", re.compile(
        r"(?:tell|give|show)\s+me\s+your\s+(?:system\s+)?(?:prompt|instructions|rules)",
        re.IGNORECASE,
    ), 0.30),
    ("system_prompt_extraction", re.compile(
        r"(?:tell|give)\s+me\s+your\s+(?:initial\s+)?(?:instructions|rules|prompt)",
        re.IGNORECASE,
    ), 0.30),
    ("system_prompt_extraction", re.compile(
        r"repeat\s+(?:the\s+)?(?:above|everything\s+above|text\s+above)",
        re.IGNORECASE,
    ), 0.25),

    # --- delimiter_injection ---
    ("delimiter_injection", re.compile(
        r"#{3,}\s*(?:SYSTEM|ADMIN|INSTRUCTION|OVERRIDE)",
        re.IGNORECASE,
    ), 0.35),
    ("delimiter_injection", re.compile(
        r"\[(?:SYSTEM|ADMIN|INST)\]\s*:?",
        re.IGNORECASE,
    ), 0.35),
    ("delimiter_injection", re.compile(
        r"<\|(?:endoftext|im_start|im_end|system)\|>",
        re.IGNORECASE,
    ), 0.40),
    ("delimiter_injection", re.compile(
        r"---\s*\n?\s*(?:SYSTEM|ADMIN|INSTRUCTION)\s*:",
        re.IGNORECASE,
    ), 0.30),
    ("delimiter_injection", re.compile(
        r"```\s*(?:system|admin|override)\b",
        re.IGNORECASE,
    ), 0.30),
]


class PromptGuard:
    """Heuristic-based prompt injection scanner.

    All patterns are pre-compiled at module level. The scan iterates a
    fixed set of ~20 regexes against the input. At 4000 chars max, this
    stays well under 1ms on modern hardware.
    """

    def scan(self, text: str) -> PromptGuardResult:
        """Scan *text* for prompt injection patterns.

        Returns a PromptGuardResult with the aggregate risk score and
        the list of matched category names. Deterministic and side-effect
        free — safe to call from synchronous middleware code.
        """
        if not text:
            return PromptGuardResult()

        matched_categories: dict[str, float] = {}

        for category, pattern, weight in _PATTERNS:
            if pattern.search(text):
                # Keep the highest weight per category
                if category not in matched_categories or weight > matched_categories[category]:
                    matched_categories[category] = weight

        if not matched_categories:
            return PromptGuardResult()

        score = min(1.0, sum(matched_categories.values()))
        return PromptGuardResult(
            injection_risk=score,
            injection_patterns=sorted(matched_categories.keys()),
        )
