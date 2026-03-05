"""
Social Media specialist — the first working delegate.

Handles three task shapes:
  • metrics       — "how's my Instagram doing?" → mocked engagement data
  • scheduling    — "post X on Y at Z" → mocked schedule confirmation,
                    asks for platform if not inferable
  • content ideas — "what should I post?" → LLM-generated on-brand suggestions

External platform APIs are mocked. Phase 2 proves the delegation contract
works end-to-end; real Instagram/Buffer integration is a separate concern.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from langchain_core.messages import HumanMessage

from .base import DelegationStatus, SpecialistAgent, SpecialistResult, SpecialistTask

logger = logging.getLogger(__name__)

# Keywords that signal social-media-ness. Weighted: platform names are
# strong signals, generic verbs are weak ones.
_PLATFORM_KEYWORDS = {
    "instagram": 0.45, "facebook": 0.45, "twitter": 0.45,
    "linkedin": 0.45, "tiktok": 0.45,
}
_STRONG_KEYWORDS = {
    "engagement": 0.3, "followers": 0.3, "hashtag": 0.3,
    "content calendar": 0.3, "social media": 0.35,
}
_WEAK_KEYWORDS = {
    "post": 0.35, "schedule": 0.15, "caption": 0.25, "story": 0.1,
}

# Intents the EA uses for requests that could be delegated. Anything else
# (workflow creation, business discovery) is the EA's own territory.
_DELEGABLE_INTENTS = {"task_delegation", "business_assistance"}


class SocialMediaSpecialist(SpecialistAgent):
    domain = "social_media"
    memory_categories = [
        "social_media",
        "current_tools",
        "daily_operations",
        "workflow_success",
    ]

    def can_handle(self, task_description: str, intent) -> float:
        # Intent gate: only score if the EA classified this as a delegable request.
        intent_val = getattr(intent, "value", None)
        if intent_val not in _DELEGABLE_INTENTS:
            return 0.0

        text = task_description.lower()
        score = 0.0
        for kw, w in _PLATFORM_KEYWORDS.items():
            if kw in text:
                score += w
        for kw, w in _STRONG_KEYWORDS.items():
            if kw in text:
                score += w
        for kw, w in _WEAK_KEYWORDS.items():
            if kw in text:
                score += w
        return min(score, 1.0)

    async def execute(self, task: SpecialistTask) -> SpecialistResult:
        text = task.task_description.lower()

        # Route by task shape. Order matters:
        #   metrics first — "how's my Instagram doing" shouldn't match "post"
        #   content before scheduling — "what should I post" is a suggestion
        #     request, but "what " contains "at " and would trip the loose
        #     scheduling heuristic
        if self._is_metrics_request(text):
            return self._handle_metrics(task, text)

        if self._is_content_request(text):
            return await self._handle_content_suggestions(task)

        if self._is_scheduling_request(text):
            return self._handle_scheduling(task, text)

        return SpecialistResult(
            status=DelegationStatus.FAILED,
            confidence=0.0,
            error="Task doesn't match any social media capability",
        )

    # --- task shape detection -------------------------------------------------

    def _is_metrics_request(self, text: str) -> bool:
        metric_signals = ("how's", "how is", "how are", "stats", "analytics",
                          "engagement", "performing", "doing", "metrics")
        return any(s in text for s in metric_signals) and self._detect_platform(text)

    def _is_scheduling_request(self, text: str) -> bool:
        return "schedule" in text or ("post" in text and any(
            t in text for t in ("tomorrow", "today", "at ", "on ", "am", "pm")
        ))

    def _is_content_request(self, text: str) -> bool:
        return any(s in text for s in (
            "what should i post", "content idea", "what to post",
            "post idea", "give me content",
        ))

    def _detect_platform(self, text: str) -> Optional[str]:
        for platform in _PLATFORM_KEYWORDS:
            if platform in text:
                return platform
        return None

    # --- handlers -------------------------------------------------------------

    def _handle_metrics(self, task: SpecialistTask, text: str) -> SpecialistResult:
        platform = self._detect_platform(text) or "instagram"

        # Mocked metrics — real implementation would hit platform APIs
        # using credentials from the customer's MCP server.
        metrics = {
            "platform": platform,
            "period": "last_7_days",
            "followers": random.randint(800, 5000),
            "follower_change": random.randint(-20, 150),
            "engagement_rate": round(random.uniform(2.0, 8.5), 2),
            "top_post_reach": random.randint(500, 3000),
        }

        summary = (
            f"{platform.title()} over the last 7 days: "
            f"{metrics['followers']:,} followers "
            f"({'+' if metrics['follower_change'] >= 0 else ''}{metrics['follower_change']}), "
            f"{metrics['engagement_rate']}% engagement rate, "
            f"top post reached {metrics['top_post_reach']:,} people."
        )

        return SpecialistResult(
            status=DelegationStatus.COMPLETED,
            content=summary,
            confidence=0.9,
            structured_data=metrics,
        )

    def _handle_scheduling(self, task: SpecialistTask, text: str) -> SpecialistResult:
        platform = self._detect_platform(text)

        # Multi-turn resumption: if we already asked and got an answer,
        # pull the platform from prior_clarifications.
        if not platform and task.prior_clarifications:
            for answer in task.prior_clarifications.values():
                platform = self._detect_platform(answer.lower())
                if platform:
                    break

        if not platform:
            return SpecialistResult(
                status=DelegationStatus.NEEDS_CLARIFICATION,
                clarification_question="Which platform should I post to?",
            )

        # Mocked scheduling — real implementation would call Buffer/Later/etc.
        scheduled = {
            "platform": platform,
            "status": "scheduled",
            "scheduled_id": f"sched_{random.randint(10000, 99999)}",
        }

        return SpecialistResult(
            status=DelegationStatus.COMPLETED,
            content=f"Post scheduled for {platform.title()}.",
            confidence=0.85,
            structured_data=scheduled,
        )

    async def _handle_content_suggestions(self, task: SpecialistTask) -> SpecialistResult:
        if not self.llm:
            return SpecialistResult(
                status=DelegationStatus.FAILED,
                error="Content generation requires LLM; none configured",
            )

        ctx = task.business_context
        memory_snippets = "\n".join(
            f"- {m.get('content', '')}" for m in task.domain_memories[:5]
        ) or "(no prior social media learnings)"

        prompt = (
            f"Generate 3 social media post ideas for {ctx.business_name} "
            f"({ctx.industry}). Current tools: {', '.join(ctx.current_tools or [])}.\n\n"
            f"What we know works for them:\n{memory_snippets}\n\n"
            f"Request: {task.task_description}\n\n"
            f"Be specific to their brand. Return a numbered list."
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return SpecialistResult(
                status=DelegationStatus.COMPLETED,
                content=response.content,
                confidence=0.75,
            )
        except Exception as e:
            logger.error(f"Content suggestion LLM call failed: {e}")
            return SpecialistResult(
                status=DelegationStatus.FAILED,
                error=str(e),
            )
