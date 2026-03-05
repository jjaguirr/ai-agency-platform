"""
Social Media specialist agent.

External platform integrations are mocked. The operational/strategic boundary
lives in assess_task — "check my engagement" delegates, "should I spend more
on ads" stays with the EA.
"""
from __future__ import annotations

import logging
import re
from typing import List, TYPE_CHECKING

from src.agents.base.specialist import (
    SpecialistAgent,
    SpecialistTask,
    SpecialistResult,
    SpecialistStatus,
    TaskAssessment,
)

if TYPE_CHECKING:
    from src.agents.executive_assistant import BusinessContext

logger = logging.getLogger(__name__)

_KNOWN_PLATFORMS = {
    "Instagram", "Facebook", "Twitter", "LinkedIn", "TikTok", "Pinterest", "YouTube",
}

# Substring matching — "post" covers "posts"/"posting". Overlaps kept out
# to avoid double-counting.
_STRONG_PHRASES = ["social media", "social ads", "content calendar"]
_WEAK_PHRASES = [
    "engagement", "followers", "hashtag", "post",
    "likes", "comments", "reach", "impressions",
]

# Advisory/business-judgment markers.
_STRATEGIC_PATTERNS = [
    r"\bshould i\b",
    r"\bis it worth\b",
    r"\bworth it\b",
    r"\bdoes .+ make sense\b",
    r"\bmake sense for\b",
    r"\bgood budget\b",
    r"\bhow much (should|to) (i )?(spend|invest|budget)\b",
    r"\binvest more\b",
    r"\bor stick with\b",
    r"\bfocus on .+ or\b",
    r"\bhir(e|ing)\b",
]


class SocialMediaSpecialist(SpecialistAgent):

    @property
    def domain(self) -> str:
        return "social_media"

    # --- Assessment ---------------------------------------------------------

    def assess_task(self, task_description: str, context: "BusinessContext") -> TaskAssessment:
        text = task_description.lower()

        confidence = 0.0
        for platform in _KNOWN_PLATFORMS:
            if platform.lower() in text:
                confidence += 0.45
        for phrase in _STRONG_PHRASES:
            if phrase in text:
                confidence += 0.35
        for phrase in _WEAK_PHRASES:
            if phrase in text:
                confidence += 0.25

        # Gate so "what's my cash flow" from a social-heavy customer stays at 0.
        if confidence > 0:
            if self._customer_platforms(context):
                confidence += 0.2
            if any("social" in p.lower() for p in (context.pain_points or [])):
                confidence += 0.15

        confidence = min(0.9, confidence)

        # Gate so "should I hire an accountant" doesn't flag as strategic-social.
        is_strategic = False
        if confidence >= 0.4:
            is_strategic = any(re.search(p, text) for p in _STRATEGIC_PATTERNS)

        return TaskAssessment(confidence=confidence, is_strategic=is_strategic)

    # --- Execution ----------------------------------------------------------

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        platforms = self._resolve_platforms(task)

        if not platforms:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={},
                confidence=0.3,
                clarification_question=(
                    "Which platform would you like me to check — "
                    "Instagram, Facebook, LinkedIn, or another?"
                ),
            )

        analysis = self._mock_platform_analysis(platforms, task)

        summary = self._build_summary(analysis, task.business_context)

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=analysis,
            confidence=0.8,
            summary_for_ea=summary,
        )

    # --- Internals ----------------------------------------------------------

    def _customer_platforms(self, context: "BusinessContext") -> List[str]:
        tools = context.current_tools or []
        return [t for t in tools if t in _KNOWN_PLATFORMS]

    def _resolve_platforms(self, task: SpecialistTask) -> List[str]:
        """Figure out which platforms this task is about.

        Priority: explicit mention in current message → explicit mention in
        prior_turns (multi-turn clarification) → customer's known tools.
        Returning [] triggers NEEDS_CLARIFICATION.
        """
        mentioned = [p for p in _KNOWN_PLATFORMS if p.lower() in task.description.lower()]
        if mentioned:
            return mentioned

        for turn in task.prior_turns:
            found = [p for p in _KNOWN_PLATFORMS if p.lower() in turn["content"].lower()]
            if found:
                return found

        return self._customer_platforms(task.business_context)

    def _mock_platform_analysis(self, platforms: List[str], task: SpecialistTask) -> dict:
        # Hash-derived so tests are stable without being obviously fake constants.
        seed = abs(hash(task.customer_id + task.description)) % 1000
        engagement_rate = 0.02 + (seed % 50) / 1000  # 2.0% – 6.9%

        top_post_hint = None
        for mem in task.domain_memories:
            content = mem.get("content", "")
            if any(w in content.lower() for w in ["post", "likes", "engagement", "launch"]):
                top_post_hint = content
                break

        return {
            "platforms": platforms,
            "engagement_rate": round(engagement_rate, 4),
            "follower_delta_7d": seed % 200 - 50,  # -50 to +149
            "top_post_hint": top_post_hint,
            "memories_consulted": len(task.domain_memories),
            "period": "last_7_days",
        }

    def _build_summary(self, analysis: dict, context: "BusinessContext") -> str:
        platforms = ", ".join(analysis["platforms"])
        rate_pct = analysis["engagement_rate"] * 100
        delta = analysis["follower_delta_7d"]
        delta_str = f"+{delta}" if delta >= 0 else str(delta)

        parts = [
            f"{platforms} engagement is at {rate_pct:.1f}% over the last 7 days",
            f"with {delta_str} followers",
        ]
        if analysis.get("top_post_hint"):
            parts.append(f"— your standout content: {analysis['top_post_hint']}")

        return " ".join(parts) + "."
