"""
Unit tests for SocialMediaSpecialist.

The assessment tests are the heart of this — they pin down the boundary
between "delegate" and "EA keeps it" for the domain where that boundary
is fuzziest.
"""
import pytest

from src.agents.specialists.social_media import SocialMediaSpecialist
from src.agents.base.specialist import SpecialistTask, SpecialistStatus
from src.agents.executive_assistant import BusinessContext


@pytest.fixture
def specialist():
    return SocialMediaSpecialist()


@pytest.fixture
def jewelry_ctx():
    return BusinessContext(
        business_name="Sparkle & Shine",
        industry="jewelry",
        current_tools=["Instagram", "Facebook", "Shopify"],
        pain_points=["manual social media"],
    )


@pytest.fixture
def consulting_ctx():
    return BusinessContext(
        business_name="Strategic Solutions",
        industry="consulting",
        current_tools=["Zoom", "LinkedIn"],
    )


# --- Assessment: operational tasks (delegate) -------------------------------

class TestAssessOperational:
    """Tasks that are concrete, execution-oriented, in-domain → delegate."""

    @pytest.mark.parametrize("msg", [
        "how's my Instagram doing?",
        "check my social media engagement this week",
        "what are my top performing posts?",
        "schedule a post for tomorrow about the new collection",
        "how many followers did I gain on Facebook?",
        "what hashtags are trending in jewelry right now",
    ])
    def test_confident_and_not_strategic(self, specialist, jewelry_ctx, msg):
        a = specialist.assess_task(msg, jewelry_ctx)
        assert a.confidence >= 0.6, f"expected confident on: {msg!r}"
        assert not a.is_strategic, f"expected operational on: {msg!r}"


# --- Assessment: strategic tasks (EA keeps) ---------------------------------

class TestAssessStrategic:
    """In-domain but advisory/business-judgment → EA keeps.

    This is the boundary the spec calls out explicitly: 'how's my Instagram
    doing' vs 'should I invest more in Instagram ads'.
    """

    @pytest.mark.parametrize("msg", [
        "should I invest more in Instagram ads?",
        "is it worth hiring a social media manager?",
        "should I focus on TikTok or stick with Instagram?",
        "does social media even make sense for my business?",
        "what's a good budget for social ads?",
    ])
    def test_in_domain_but_strategic(self, specialist, jewelry_ctx, msg):
        a = specialist.assess_task(msg, jewelry_ctx)
        # confident it's social media...
        assert a.confidence >= 0.5, f"expected domain recognition on: {msg!r}"
        # ...but flags it for EA judgment
        assert a.is_strategic, f"expected strategic flag on: {msg!r}"


# --- Assessment: out of domain (low confidence) -----------------------------

class TestAssessOutOfDomain:
    @pytest.mark.parametrize("msg", [
        "what's my cash flow looking like?",
        "can you help me draft a contract?",
        "I need to schedule a meeting with my accountant",
        "what's the weather tomorrow?",
    ])
    def test_low_confidence(self, specialist, jewelry_ctx, msg):
        a = specialist.assess_task(msg, jewelry_ctx)
        assert a.confidence < 0.5, f"expected low confidence on: {msg!r}"


# --- Assessment: business context influences confidence ---------------------

class TestAssessContextAware:
    def test_boosts_confidence_when_customer_uses_social_tools(self, specialist):
        msg = "check how my posts are doing"
        no_tools = BusinessContext(business_name="X", current_tools=[])
        with_tools = BusinessContext(business_name="X", current_tools=["Instagram", "Facebook"])

        assert specialist.assess_task(msg, with_tools).confidence > \
               specialist.assess_task(msg, no_tools).confidence


# --- Execution: completed ---------------------------------------------------

class TestExecuteCompleted:
    @pytest.mark.asyncio
    async def test_engagement_check_returns_structured_payload(self, specialist, jewelry_ctx):
        task = SpecialistTask(
            description="how's my Instagram engagement this week?",
            customer_id="cust_jewelry",
            business_context=jewelry_ctx,
            domain_memories=[
                {"content": "Customer posts product photos daily at 9am", "score": 0.9},
                {"content": "Instagram is their primary channel", "score": 0.85},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.domain == "social_media"
        assert "engagement_rate" in result.payload
        assert "platforms" in result.payload
        assert result.summary_for_ea  # gives EA something to work with
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_uses_domain_memories_in_response(self, specialist, jewelry_ctx):
        """The specialist should actually use the context the EA scoped for it."""
        task = SpecialistTask(
            description="what are my top posts?",
            customer_id="cust_jewelry",
            business_context=jewelry_ctx,
            domain_memories=[
                {"content": "Product launch post got 500 likes last month", "score": 0.95},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        # Payload should reflect memory was consulted
        assert result.payload.get("memories_consulted", 0) == 1

    @pytest.mark.asyncio
    async def test_scopes_platforms_to_customer_tools(self, specialist, consulting_ctx):
        """Customer only uses LinkedIn → don't report on Instagram."""
        task = SpecialistTask(
            description="check my engagement",
            customer_id="cust_consulting",
            business_context=consulting_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        platforms = result.payload.get("platforms", [])
        assert "LinkedIn" in platforms
        assert "Instagram" not in platforms


# --- Execution: needs clarification -----------------------------------------

class TestExecuteClarification:
    @pytest.mark.asyncio
    async def test_asks_when_platform_ambiguous_and_no_tools_known(self, specialist):
        """Customer asks about 'my posts' but we don't know which platform."""
        ctx = BusinessContext(business_name="New Biz", current_tools=[])
        task = SpecialistTask(
            description="check my posts",
            customer_id="cust_new",
            business_context=ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert result.clarification_question
        assert "platform" in result.clarification_question.lower()

    @pytest.mark.asyncio
    async def test_resolves_clarification_with_prior_turns(self, specialist):
        """Multi-turn: specialist asked, customer answered, now complete."""
        ctx = BusinessContext(business_name="New Biz", current_tools=[])
        task = SpecialistTask(
            description="Instagram and Facebook please",
            customer_id="cust_new",
            business_context=ctx,
            domain_memories=[],
            prior_turns=[
                {"role": "specialist", "content": "Which platforms should I check?"},
                {"role": "customer", "content": "Instagram and Facebook please"},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        platforms = result.payload.get("platforms", [])
        assert "Instagram" in platforms
        assert "Facebook" in platforms


# --- Isolation ---------------------------------------------------------------

class TestIsolation:
    @pytest.mark.asyncio
    async def test_only_sees_what_task_carries(self, specialist, jewelry_ctx):
        """Specialist has no backdoor to memory — only sees domain_memories.
        Empty memories → payload reflects zero consulted, no crash."""
        task = SpecialistTask(
            description="how's engagement?",
            customer_id="cust_x",
            business_context=jewelry_ctx,
            domain_memories=[],  # EA found nothing relevant
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload.get("memories_consulted", 0) == 0
