"""Unit tests for the Social Media specialist."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.executive_assistant import BusinessContext, ConversationIntent
from src.agents.specialists.base import SpecialistTask, DelegationStatus


@pytest.fixture
def specialist():
    from src.agents.specialists.social_media import SocialMediaSpecialist
    return SocialMediaSpecialist(llm=None)


@pytest.fixture
def specialist_with_llm():
    from src.agents.specialists.social_media import SocialMediaSpecialist

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(content="1. Post behind-the-scenes video\n2. Share a customer story")
    )
    return SocialMediaSpecialist(llm=llm), llm


def make_task(description: str, clarifications=None, business_name="Sparkle Jewelry"):
    return SpecialistTask(
        task_description=description,
        customer_id="cust_1",
        conversation_id="conv_1",
        business_context=BusinessContext(
            business_name=business_name,
            industry="jewelry",
            current_tools=["Instagram", "Buffer"],
        ),
        domain_memories=[
            {"content": "Posts about new collections perform well", "metadata": {"category": "social_media"}},
        ],
        prior_clarifications=clarifications or {},
    )


# ---------------------------------------------------------------------------
# can_handle — routing scorer
# ---------------------------------------------------------------------------

class TestCanHandle:
    def test_high_score_for_instagram_scheduling(self, specialist):
        score = specialist.can_handle(
            "schedule an instagram post for tomorrow",
            ConversationIntent.TASK_DELEGATION,
        )
        assert score >= 0.7

    def test_high_score_for_engagement_question(self, specialist):
        score = specialist.can_handle(
            "how's my Instagram engagement doing?",
            ConversationIntent.BUSINESS_ASSISTANCE,
        )
        assert score >= 0.7

    def test_moderate_score_for_generic_post_mention(self, specialist):
        score = specialist.can_handle(
            "I need to post something",
            ConversationIntent.BUSINESS_ASSISTANCE,
        )
        assert 0.3 <= score < 0.7

    def test_low_score_for_finance_request(self, specialist):
        score = specialist.can_handle(
            "file my quarterly taxes",
            ConversationIntent.TASK_DELEGATION,
        )
        assert score < 0.3

    def test_zero_for_irrelevant_intent(self, specialist):
        # Workflow creation isn't a delegation intent — EA owns that path
        score = specialist.can_handle(
            "instagram post automation",
            ConversationIntent.WORKFLOW_CREATION,
        )
        assert score == 0.0

    def test_domain_and_categories_declared(self, specialist):
        assert specialist.domain == "social_media"
        assert "social_media" in specialist.memory_categories
        assert "current_tools" in specialist.memory_categories


# ---------------------------------------------------------------------------
# execute — metrics path
# ---------------------------------------------------------------------------

class TestMetricsPath:
    @pytest.mark.asyncio
    async def test_metrics_request_returns_completed_with_data(self, specialist):
        task = make_task("how's my Instagram doing?")
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.COMPLETED
        assert result.confidence >= 0.8
        assert result.structured_data is not None
        assert "instagram" in result.structured_data.get("platform", "").lower()
        # content should summarize, not be a raw data dump
        assert result.content is not None
        assert len(result.content) > 20

    @pytest.mark.asyncio
    async def test_metrics_detects_platform_from_task(self, specialist):
        task = make_task("show me facebook engagement stats")
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.COMPLETED
        assert "facebook" in result.structured_data.get("platform", "").lower()


# ---------------------------------------------------------------------------
# execute — scheduling path with multi-turn clarification
# ---------------------------------------------------------------------------

class TestSchedulingPath:
    @pytest.mark.asyncio
    async def test_scheduling_without_platform_asks_clarification(self, specialist):
        task = make_task("schedule a post about our new collection for tomorrow at 9am")
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.NEEDS_CLARIFICATION
        assert result.clarification_question is not None
        assert "platform" in result.clarification_question.lower()

    @pytest.mark.asyncio
    async def test_scheduling_with_platform_in_task_completes(self, specialist):
        task = make_task("schedule a post on Instagram about our new collection tomorrow 9am")
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.COMPLETED
        assert result.confidence >= 0.7
        assert result.structured_data is not None
        assert result.structured_data.get("platform", "").lower() == "instagram"
        assert "scheduled" in result.content.lower()

    @pytest.mark.asyncio
    async def test_scheduling_resumed_with_clarification_completes(self, specialist):
        # Turn 1 asked for platform; turn 2 provides it via prior_clarifications
        task = make_task(
            "schedule a post about our new collection for tomorrow at 9am",
            clarifications={"Which platform should I post to?": "Instagram"},
        )
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.COMPLETED
        assert result.structured_data.get("platform", "").lower() == "instagram"


# ---------------------------------------------------------------------------
# execute — content suggestions path (uses LLM)
# ---------------------------------------------------------------------------

class TestContentSuggestionsPath:
    @pytest.mark.asyncio
    async def test_content_suggestions_calls_llm(self, specialist_with_llm):
        specialist, llm = specialist_with_llm
        task = make_task("what should I post this week?")
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.COMPLETED
        llm.ainvoke.assert_awaited_once()
        assert result.content is not None

    @pytest.mark.asyncio
    async def test_content_prompt_includes_business_context(self, specialist_with_llm):
        specialist, llm = specialist_with_llm
        task = make_task("give me content ideas", business_name="Sparkle Jewelry")
        await specialist.execute(task)

        # Inspect the prompt sent to the LLM
        call_args = llm.ainvoke.await_args
        prompt_messages = call_args[0][0]
        prompt_text = " ".join(
            m.content for m in prompt_messages if hasattr(m, "content")
        )
        assert "Sparkle Jewelry" in prompt_text
        assert "jewelry" in prompt_text.lower()  # industry

    @pytest.mark.asyncio
    async def test_content_prompt_includes_domain_memories(self, specialist_with_llm):
        specialist, llm = specialist_with_llm
        task = make_task("what should I post?")
        await specialist.execute(task)

        call_args = llm.ainvoke.await_args
        prompt_text = " ".join(
            m.content for m in call_args[0][0] if hasattr(m, "content")
        )
        assert "new collections perform well" in prompt_text

    @pytest.mark.asyncio
    async def test_content_without_llm_fails_gracefully(self, specialist):
        # specialist fixture has llm=None
        task = make_task("what should I post this week?")
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.FAILED
        assert result.error is not None


# ---------------------------------------------------------------------------
# execute — unrecognized fallback
# ---------------------------------------------------------------------------

class TestUnrecognizedPath:
    @pytest.mark.asyncio
    async def test_unrelated_task_fails_with_low_confidence(self, specialist):
        task = make_task("reconcile my bank statements")
        result = await specialist.execute(task)

        assert result.status == DelegationStatus.FAILED
        assert result.confidence == 0.0
