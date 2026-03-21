"""
PromptGuard — heuristic prompt-injection detection.

Deterministic regex scanner. No I/O, no LLM calls, no network. Runs on
every inbound message before the EA sees it, so it must be fast (<5ms)
and biased toward false-negatives: a normal business message flagged
HIGH means the customer gets a useless fallback instead of actual help.

Each pattern category contributes a weight. risk_score is the sum of
matched weights, clamped to [0, 1]. One category alone lands in
MEDIUM at most; HIGH requires stacking — a message that trips two or
more independent detection categories is almost certainly adversarial.

The patterns are deliberately narrow. "Ignore previous instructions"
matches; "ignore the noise in the data" does not. "You are now in
admin mode" matches; "you are my favorite" does not. The word boundary
and required-context-word choices in each regex are what keep the
false-positive rate low — see tests/unit/safety/test_prompt_guard.py
TestBusinessLanguagePassesClean for the pinned phrases.
"""
from __future__ import annotations

import re
from typing import List, Pattern, Tuple

from .models import InjectionScan, RiskLevel


# --- Pattern definitions ----------------------------------------------------
# Each category is a list of precompiled regexes. A category fires if ANY
# of its regexes match. Multiple matches within one category still count
# as one weight contribution (we're measuring breadth of attack, not
# repetition). Spans from every individual match are collected so the
# pipeline can strip them at MEDIUM risk.

_CATEGORIES: List[Tuple[str, float, List[Pattern[str]]]] = [
    (
        "instruction_override",
        0.40,
        [
            # "ignore [all|any|previous|prior|above|your]* instructions"
            # The required instructions/prompt/rules anchor is what
            # keeps "ignore the noise" from matching. We allow up to two
            # optional qualifier words between "ignore" and the anchor
            # so both "ignore previous instructions" and "ignore all
            # instructions" match — but "ignore the noise in the data"
            # does not (noise is not an anchor noun).
            re.compile(
                r"\bignore\s+"
                r"(?:(?:all|any|the|previous|prior|above|earlier|your)\s+){0,2}"
                r"(?:instructions?|prompts?|rules?|directives?)\b",
                re.IGNORECASE,
            ),
            # "disregard [the|all] instructions" — same anchor requirement.
            # Negative lookahead for "from" blocks "disregard instructions
            # from the client" (business language).
            re.compile(
                r"\bdisregard\s+(?:the\s+|all\s+|any\s+|previous\s+)?"
                r"(?:instructions?|rules?|prompts?)\b"
                r"(?!\s+from\b)",
                re.IGNORECASE,
            ),
            # "forget {everything,all} [you were told | prior context]"
            # Requires "everything/all" — "forget about that project"
            # doesn't match.
            re.compile(
                r"\bforget\s+(?:everything|all)\b"
                r"(?:\s+(?:you\s+(?:were\s+)?(?:told|know)|prior|previous|above))?",
                re.IGNORECASE,
            ),
            # "new instructions:" — the colon makes this an imperative
            # header, not "the new instructions arrived" (prose).
            re.compile(
                r"\bnew\s+instructions?\s*:",
                re.IGNORECASE,
            ),
        ],
    ),
    (
        "role_manipulation",
        0.35,
        [
            # "you are now ..." — the "now" is the tell. "You are my
            # favorite" has no "now"; "you are now in admin mode" does.
            # After "now" we accept either an article OR a bare
            # privileged-role noun ("you are now root").
            re.compile(
                r"\byou\s+are\s+now\s+"
                r"(?:a\b|an\b|in\b|the\b"
                r"|admin(?:istrator)?\b|root\b|developer\b|system\b"
                r"|unrestricted\b|dan\b|jailbr\w+)",
                re.IGNORECASE,
            ),
            # "switch to X mode" — requires literal "mode" at the end.
            # "switch to the finance topic" doesn't match.
            re.compile(
                r"\bswitch\s+to\s+\w+(?:\s+\w+)?\s+mode\b",
                re.IGNORECASE,
            ),
            # "act as [if you are|were] {a,an}? {admin,root,developer,...}"
            # Closed set of privileged-role nouns. "Acting as a consultant"
            # isn't in the set. "(?<!\w)" instead of \b so "acting" (with
            # the -ing suffix) doesn't satisfy the boundary before "act".
            re.compile(
                r"(?<![\w])act\s+as\s+"
                r"(?:if\s+you\s+(?:are|were)\s+)?"
                r"(?:a\s+|an\s+)?"
                r"(?:admin(?:istrator)?|root|developer|system|unrestricted|dan|jailbr\w+)\b",
                re.IGNORECASE,
            ),
            # "pretend {you are | to be}" — broad, but "pretend" in a
            # business message is rare enough that this is safe.
            re.compile(
                r"\bpretend\s+(?:you\s+are|to\s+be)\b",
                re.IGNORECASE,
            ),
        ],
    ),
    (
        "prompt_extraction",
        0.35,
        [
            # "{repeat,print,show,reveal,output} {your,the} [system] {prompt,instructions,rules}"
            # Requires the possessive/article AND the target noun.
            # "Show me the rules of the contest" → "rules of" not "rules$"
            # so we add a negative lookahead for "of".
            re.compile(
                r"\b(?:repeat|print|show|reveal|output|display)\s+"
                r"(?:me\s+)?(?:your|the)\s+"
                r"(?:system\s+|initial\s+|original\s+)?"
                r"(?:prompt|instructions?|rules?|directives?)\b"
                r"(?!\s+(?:of|for|about)\b)",
                re.IGNORECASE,
            ),
            # "what {are your | were you given} {instructions,rules}"
            # Negative lookahead excludes "rates" and similar business nouns.
            re.compile(
                r"\bwhat\s+(?:are\s+your|were\s+you\s+given(?:\s+as)?)\s+"
                r"(?:instructions?|rules?|system\s+prompt)\b",
                re.IGNORECASE,
            ),
        ],
    ),
    (
        "delimiter_injection",
        0.30,
        [
            # XML-ish role tags: <system>, </instructions>, <assistant>
            re.compile(
                r"</?\s*(?:system|instructions?|assistant|user)\s*>",
                re.IGNORECASE,
            ),
            # Llama-style: [INST], [/INST], [SYS]
            re.compile(
                r"\[/?\s*(?:INST|SYS|SYSTEM)\s*\]",
                re.IGNORECASE,
            ),
            # Markdown-fence-ish system headers: ### system: ...
            # Colon required — a plain "### System Overview" heading in
            # a legitimate doc won't match.
            re.compile(
                r"#{2,}\s*(?:system|instructions?)\s*:",
                re.IGNORECASE,
            ),
        ],
    ),
]

# Default thresholds — SafetyConfig can override. Exposed here so the
# guard is usable standalone (tests don't construct a full config).
_DEFAULT_MEDIUM = 0.3
_DEFAULT_HIGH = 0.7


class PromptGuard:
    """Scan inbound messages for prompt-injection patterns.

    Stateless. Patterns are module-level constants (compiled once at
    import). Constructing a guard is free — the instance just carries
    the thresholds.
    """

    __slots__ = ("_medium_threshold", "_high_threshold")

    def __init__(
        self,
        *,
        medium_threshold: float = _DEFAULT_MEDIUM,
        high_threshold: float = _DEFAULT_HIGH,
    ) -> None:
        self._medium_threshold = medium_threshold
        self._high_threshold = high_threshold

    def scan(self, message: str) -> InjectionScan:
        if not message or not message.strip():
            return InjectionScan.clean()

        matched_categories: List[str] = []
        spans: List[Tuple[int, int]] = []
        score = 0.0

        for category, weight, patterns in _CATEGORIES:
            category_hit = False
            for pat in patterns:
                for m in pat.finditer(message):
                    spans.append(m.span())
                    category_hit = True
            if category_hit:
                matched_categories.append(category)
                score += weight

        score = min(1.0, score)

        if score >= self._high_threshold:
            level = RiskLevel.HIGH
        elif score >= self._medium_threshold:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return InjectionScan(
            risk_score=score,
            risk_level=level,
            patterns=matched_categories,
            spans=spans,
        )
