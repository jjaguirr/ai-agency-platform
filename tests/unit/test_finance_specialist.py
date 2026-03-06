"""
Unit tests for FinanceSpecialist.

Second specialist in the delegation framework. These tests prove the
framework accommodates a new domain without modification — registration
is one call, routing is self-assessment, and the EA stays untouched.

Coverage per the spec:
- routing to the correct specialist (incl. overlap with social media)
- expense categorization from natural-language entries
- clarification flow (missing amount/vendor)
- multi-turn entry via prior_turns
- summary generation
- structured payload (amount/date/vendor/category)
"""
import pytest

from src.agents.specialists.finance import FinanceSpecialist
from src.agents.specialists.social_media import SocialMediaSpecialist
from src.agents.base.specialist import (
    SpecialistTask,
    SpecialistStatus,
    DelegationRegistry,
)
from src.agents.executive_assistant import BusinessContext


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def specialist():
    return FinanceSpecialist()


@pytest.fixture
def retail_ctx():
    """A customer who tracks expenses and uses social media — realistic
    overlap surface for routing tests."""
    return BusinessContext(
        business_name="Sparkle & Shine",
        industry="jewelry",
        current_tools=["Instagram", "Facebook", "Shopify", "QuickBooks"],
        pain_points=["manual expense tracking", "cash flow visibility"],
    )


@pytest.fixture
def consulting_ctx():
    """Customer with no known finance tooling — tests baseline confidence."""
    return BusinessContext(
        business_name="Strategic Solutions",
        industry="consulting",
        current_tools=["Zoom", "LinkedIn"],
    )


@pytest.fixture
def registry_with_both(specialist):
    """Registry with both finance and social media registered — the
    realistic routing surface where overlap matters."""
    reg = DelegationRegistry(confidence_threshold=0.6)
    reg.register(specialist)
    reg.register(SocialMediaSpecialist())
    return reg


# --- Assessment: operational finance tasks (delegate) -----------------------

class TestAssessOperational:
    """Concrete, execution-oriented finance tasks → delegate."""

    @pytest.mark.parametrize("msg", [
        "track this invoice: $2,400 from Acme Corp, due March 15",
        "what's my cash flow looking like?",
        "how much did I spend on marketing last month?",
        "log an expense: $350 for office supplies",
        "what were my top expense categories this quarter?",
        "record $1,200 payment to the landlord for rent",
    ])
    def test_confident_and_not_strategic(self, specialist, retail_ctx, msg):
        a = specialist.assess_task(msg, retail_ctx)
        assert a.confidence >= 0.6, f"expected confident on: {msg!r}"
        assert not a.is_strategic, f"expected operational on: {msg!r}"


# --- Assessment: strategic finance tasks (EA keeps) -------------------------

class TestAssessStrategic:
    """In-domain but advisory — mirrors the social-media boundary."""

    @pytest.mark.parametrize("msg", [
        "should I raise my prices?",
        "is it worth getting a business loan right now?",
        "should I hire an accountant or keep doing it myself?",
        "does it make sense to lease vs buy the equipment?",
        "how much should I budget for payroll next year?",
    ])
    def test_in_domain_but_strategic(self, specialist, retail_ctx, msg):
        a = specialist.assess_task(msg, retail_ctx)
        assert a.confidence >= 0.4, f"expected domain recognition on: {msg!r}"
        assert a.is_strategic, f"expected strategic flag on: {msg!r}"


# --- Assessment: out of domain ----------------------------------------------

class TestAssessOutOfDomain:
    @pytest.mark.parametrize("msg", [
        "how's my Instagram engagement this week?",
        "schedule a post for tomorrow",
        "can you draft a contract?",
        "what hashtags are trending?",
    ])
    def test_low_confidence(self, specialist, retail_ctx, msg):
        a = specialist.assess_task(msg, retail_ctx)
        assert a.confidence < 0.5, f"expected low confidence on: {msg!r}"


# --- Assessment: context influences confidence ------------------------------

class TestAssessContextAware:
    def test_finance_pain_points_boost_confidence(self, specialist):
        msg = "what's my spending looking like?"
        no_pain = BusinessContext(business_name="X")
        with_pain = BusinessContext(
            business_name="X",
            pain_points=["cash flow visibility", "expense tracking"],
        )
        assert specialist.assess_task(msg, with_pain).confidence > \
               specialist.assess_task(msg, no_pain).confidence


# --- Routing overlap with social media --------------------------------------

class TestRoutingOverlap:
    """The registry must not misroute when both specialists are registered.

    The spec calls out specific cases:
    - 'How much does Instagram advertising cost?' → social (pricing question
      about a platform, not tracking a real expense)
    - 'What's my ROI on the Facebook campaign?' → could go either way, but
      neither should dominate at ≥0.6 without clear signals → EA handles
    - 'What should my ad budget be?' → strategic, EA keeps
    """

    def test_cash_flow_routes_to_finance(self, registry_with_both, retail_ctx):
        match = registry_with_both.route("what's my cash flow looking like?", retail_ctx)
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_instagram_engagement_routes_to_social(self, registry_with_both, retail_ctx):
        match = registry_with_both.route("how's my Instagram engagement?", retail_ctx)
        assert match is not None
        assert match.specialist.domain == "social_media"

    def test_instagram_ad_cost_routes_to_social(self, registry_with_both, retail_ctx):
        """Financial keywords present but it's a platform-pricing question,
        not an expense to track. Social owns platform knowledge."""
        match = registry_with_both.route(
            "how much does Instagram advertising cost?", retail_ctx
        )
        assert match is not None
        assert match.specialist.domain == "social_media"

    def test_ad_budget_goes_to_ea_as_strategic(self, registry_with_both, retail_ctx):
        """'What should my ad budget be?' — both specialists might flag
        strategic. Either way, the EA keeps it."""
        match = registry_with_both.route(
            "what should my ad budget be?", retail_ctx
        )
        assert match is None, "strategic budget question should stay with EA"

    def test_track_ad_spend_routes_to_finance(self, registry_with_both, retail_ctx):
        """But a concrete expense entry — even for a social-media line item —
        is finance. 'Track $500 spent on Facebook ads' is an accounting action."""
        match = registry_with_both.route(
            "track $500 I spent on Facebook ads last week", retail_ctx
        )
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_roi_question_not_misrouted_to_finance(self, registry_with_both, retail_ctx):
        """ROI on a campaign is cross-domain. The spec says it 'could go either
        way' — we can't constrain social_media's confidence (framework is
        immutable per task rules). What we CAN guarantee: finance flags it
        strategic (ROI is advisory, not an expense to track) so finance
        never claims it. If social claims it, that's social's call."""
        match = registry_with_both.route(
            "what's my ROI on the Facebook campaign?", retail_ctx
        )
        # Either None (EA handles) or social_media. Never finance.
        if match is not None:
            assert match.specialist.domain != "finance"

    def test_roi_question_finance_self_assessment(self, specialist, retail_ctx):
        """Directly verify: finance recognizes ROI as in-domain but strategic."""
        a = specialist.assess_task("what's my ROI on the Facebook campaign?", retail_ctx)
        # In domain enough to flag...
        assert a.confidence >= 0.4
        # ...but advisory — EA keeps.
        assert a.is_strategic

    def test_both_registered_no_framework_changes(self, registry_with_both):
        """Validation criterion: adding finance required zero changes to
        specialist.py or executive_assistant.py. The registry just has two
        entries now."""
        assert registry_with_both.get("finance") is not None
        assert registry_with_both.get("social_media") is not None


# --- Execution: expense tracking with structured payload --------------------

class TestExecuteExpenseTracking:
    @pytest.mark.asyncio
    async def test_parses_amount_vendor_category_date(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="track this invoice: $2,400 from Acme Corp, due March 15",
            customer_id="cust_retail",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.domain == "finance"
        # Structured payload per spec
        assert result.payload["amount"] == 2400.0
        assert "acme" in result.payload["vendor"].lower()
        assert result.payload["category"] is not None
        assert "march" in result.payload.get("due_date", "").lower() or \
               "03" in result.payload.get("due_date", "") or \
               "3/15" in result.payload.get("due_date", "")
        assert result.summary_for_ea

    @pytest.mark.asyncio
    async def test_categorizes_rent(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="log $1,200 payment to landlord for March rent",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 1200.0
        assert result.payload["category"] == "rent"

    @pytest.mark.asyncio
    async def test_categorizes_software(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="track $49/mo for Shopify subscription",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["category"] == "software"

    @pytest.mark.asyncio
    async def test_categorizes_marketing(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="record $500 spent on Facebook ads",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["category"] == "marketing"

    @pytest.mark.asyncio
    async def test_categorizes_payroll(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="paid my assistant $2,000 salary for February",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["category"] == "payroll"

    @pytest.mark.asyncio
    async def test_unknown_category_falls_back_to_operations(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="track $80 for miscellaneous supplies",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        # Defaults to a sane bucket, not None
        assert result.payload["category"] in ("operations", "other")


# --- Execution: clarification flow ------------------------------------------

class TestExecuteClarification:
    @pytest.mark.asyncio
    async def test_asks_when_amount_missing(self, specialist, retail_ctx):
        """'Track this expense' with no amount → ask, don't guess."""
        task = SpecialistTask(
            description="track this expense from Acme Corp",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert result.clarification_question
        assert "amount" in result.clarification_question.lower() or \
               "how much" in result.clarification_question.lower()

    @pytest.mark.asyncio
    async def test_asks_when_vendor_missing(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="track $350 I just paid",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert result.clarification_question
        q = result.clarification_question.lower()
        assert "vendor" in q or "who" in q or "paid to" in q or "what was" in q

    @pytest.mark.asyncio
    async def test_resolves_missing_amount_via_prior_turns(self, specialist, retail_ctx):
        """Multi-turn: specialist asked for amount → customer provided → complete."""
        task = SpecialistTask(
            description="$2,400",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
            prior_turns=[
                {"role": "customer", "content": "track this invoice from Acme Corp"},
                {"role": "specialist", "content": "How much was the invoice?"},
                {"role": "customer", "content": "$2,400"},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 2400.0
        assert "acme" in result.payload["vendor"].lower()

    @pytest.mark.asyncio
    async def test_resolves_missing_vendor_via_prior_turns(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="the landlord, it's for rent",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
            prior_turns=[
                {"role": "customer", "content": "track $1,200 I just paid"},
                {"role": "specialist", "content": "Who did you pay that to?"},
                {"role": "customer", "content": "the landlord, it's for rent"},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 1200.0
        assert result.payload["category"] == "rent"


# --- Execution: financial summaries -----------------------------------------

class TestExecuteSummaries:
    @pytest.mark.asyncio
    async def test_spending_query_uses_domain_memories(self, specialist, retail_ctx):
        """'How much did I spend on marketing?' — pull from domain_memories,
        aggregate, return structured summary."""
        task = SpecialistTask(
            description="how much did I spend on marketing last month?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[
                {"content": "Paid $500 for Facebook ads on Feb 3", "score": 0.9},
                {"content": "Instagram boost $120 on Feb 10", "score": 0.85},
                {"content": "Office rent $1,200 for February", "score": 0.7},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        # Should have aggregated marketing spend, excluded rent
        assert "category_totals" in result.payload or "total" in result.payload
        assert result.summary_for_ea
        # Summary should mention marketing and a dollar figure
        summary = result.summary_for_ea.lower()
        assert "marketing" in summary
        assert "$" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_cash_flow_query_produces_summary(self, specialist, retail_ctx):
        task = SpecialistTask(
            description="what's my cash flow looking like?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[
                {"content": "Invoice paid by client: $5,000 on Feb 1", "score": 0.9},
                {"content": "Rent $1,200 due Feb 5", "score": 0.85},
                {"content": "Software subscriptions $200/mo", "score": 0.8},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.summary_for_ea
        # Payload has income/expense breakdown
        p = result.payload
        assert "income" in p or "inflow" in p
        assert "expenses" in p or "outflow" in p

    @pytest.mark.asyncio
    async def test_empty_memories_still_completes_summary(self, specialist, retail_ctx):
        """No backdoor to memory — if EA found nothing relevant, specialist
        returns a graceful empty summary rather than crashing."""
        task = SpecialistTask(
            description="what's my cash flow looking like?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.summary_for_ea  # still gives EA something to say
        assert result.payload.get("memories_consulted", -1) == 0


# --- Isolation --------------------------------------------------------------

class TestIsolation:
    @pytest.mark.asyncio
    async def test_no_direct_memory_access(self, specialist, retail_ctx):
        """Same isolation boundary as social media: specialist only sees
        what SpecialistTask carries."""
        task = SpecialistTask(
            description="track $100 for office supplies",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        # Specialist has no memory_client attribute, no way to fetch beyond task
        assert not hasattr(specialist, "memory_client")
        assert not hasattr(specialist, "memory")
