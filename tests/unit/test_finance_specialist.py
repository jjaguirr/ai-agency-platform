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


# --- Assessment: lexical floor (no context boost) ---------------------------

class TestAssessLexicalFloor:
    """Routing must work for a customer with no finance tooling or pain
    points — otherwise the specialist only routes for customers the EA
    already knows are finance-interested, which defeats the point."""

    @pytest.fixture
    def bare_ctx(self):
        return BusinessContext(business_name="Unknown Co")

    @pytest.mark.parametrize("msg", [
        "track this invoice: $2,400 from Acme Corp",
        "what's my cash flow looking like?",
        "log a payroll expense: $2,000",
    ])
    def test_unambiguous_phrases_route_without_context(self, specialist, bare_ctx, msg):
        """These contain domain terms that have no non-finance meaning.
        One should be enough to clear the threshold."""
        a = specialist.assess_task(msg, bare_ctx)
        assert a.confidence >= 0.6, (
            f"{msg!r} scored {a.confidence:.2f} with zero context — "
            "unambiguous finance phrases should route on their own"
        )
        assert not a.is_strategic

    def test_softer_phrases_need_context(self, specialist, bare_ctx):
        """'spend' alone is common in non-finance contexts. It's fine for
        this to fall short without context — documents the boundary."""
        a = specialist.assess_task("what did I spend recently?", bare_ctx)
        assert a.confidence < 0.6


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

    def test_confidence_capped_at_point_nine(self, specialist, retail_ctx):
        """Stacking every signal shouldn't yield certainty — the cap
        leaves room for the EA to second-guess."""
        a = specialist.assess_task(
            "track this invoice expense $5,000 cash flow payment",
            retail_ctx,
        )
        assert a.confidence == 0.9


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

    def test_roi_question_finance_self_assessment(self, specialist, retail_ctx):
        """ROI on a campaign is cross-domain; the spec says it 'could go
        either way'. Finance's contract: recognize it as in-domain but
        flag it strategic so finance never claims it via the registry.
        Whether social_media claims it is social_media's decision."""
        a = specialist.assess_task("what's my ROI on the Facebook campaign?", retail_ctx)
        assert a.confidence >= 0.4   # in domain enough to trip the strategic gate
        assert a.is_strategic         # advisory — EA keeps

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
        # Structured payload per spec — exact values, not just presence
        assert result.payload["amount"] == 2400.0
        assert "acme" in result.payload["vendor"].lower()
        assert result.payload["category"] == "operations"  # no category keyword → default
        assert result.payload["due_date"] == "March 15"
        # Summary echoes the amount and vendor
        assert "$2,400.00" in result.summary_for_ea
        assert "Acme" in result.summary_for_ea

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
        """Input deliberately avoids every category keyword so we actually
        exercise the default, not an operations rule match."""
        task = SpecialistTask(
            description="track $80 paid to Widgets Unlimited",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["category"] == "operations"
        assert result.payload["vendor"] == "Widgets Unlimited"


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
        assert result.clarification_question == "How much was the amount?"

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
        q = result.clarification_question.lower()
        # Must ask for both the payee AND make clear a name is wanted —
        # not accept any question containing "who" somewhere.
        assert "who" in q
        assert "vendor" in q or "payee" in q
        # Partial state preserved so the follow-up doesn't re-ask for amount
        assert result.payload["amount"] == 350.0

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
        # Exact arithmetic: $500 + $120 = $620. Rent ($1,200) MUST be excluded.
        p = result.payload
        assert p["total"] == 620.0
        assert p["entry_count"] == 2
        assert p["category_totals"] == {"marketing": 620.0}
        assert "rent" not in p["category_totals"]
        assert p["memories_consulted"] == 3  # looked at all three, filtered one
        # Summary reports the computed figure, not just any dollar sign
        assert "$620.00" in result.summary_for_ea
        assert "marketing" in result.summary_for_ea.lower()

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
        # Exact arithmetic. 'paid by client' → income; rent + subscriptions → expenses.
        p = result.payload
        assert p["income"] == 5000.0
        assert p["expenses"] == 1400.0  # 1200 + 200
        assert p["net"] == 3600.0
        # Category breakdown on the expense side only
        assert p["category_totals"] == {"rent": 1200.0, "software": 200.0}
        # Summary reports the net, not just any figure
        assert "$3,600.00" in result.summary_for_ea

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
        # Zeros, not missing keys — schema stays stable regardless of data
        assert result.payload["income"] == 0.0
        assert result.payload["expenses"] == 0.0
        assert result.payload["net"] == 0.0
        assert result.payload["memories_consulted"] == 0
        # Still gives EA a sentence to relay (not empty string)
        assert result.summary_for_ea


# --- Income classification (sign-flip defense) ------------------------------

class TestIncomeClassification:
    """The income/expense classifier decides the SIGN of every figure in a
    cash-flow summary. A misclassification is a 2× error in the net.
    These tests pin the payment-method and ambiguous-deposit traps."""

    async def _cashflow(self, specialist, retail_ctx, memories):
        task = SpecialistTask(
            description="what's my cash flow looking like?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=memories,
        )
        return await specialist.execute_task(task)

    @pytest.mark.asyncio
    async def test_paid_by_payment_method_is_expense(self, specialist, retail_ctx):
        """'paid by credit card' names a payment instrument, not a payer.
        Naive substring match on 'paid by' would count this as income —
        a $1,000 swing on the net."""
        result = await self._cashflow(specialist, retail_ctx, [
            {"content": "Paid by credit card: $500 for supplies", "score": 0.9},
        ])
        p = result.payload
        assert p["income"] == 0.0
        assert p["expenses"] == 500.0
        assert p["net"] == -500.0

    @pytest.mark.asyncio
    async def test_paid_by_external_party_is_income(self, specialist, retail_ctx):
        """Contrast: 'paid by client' IS an inflow. The discriminator is
        what follows 'paid by' — a party vs an instrument."""
        result = await self._cashflow(specialist, retail_ctx, [
            {"content": "Invoice paid by client: $5,000 on Feb 1", "score": 0.9},
        ])
        p = result.payload
        assert p["income"] == 5000.0
        assert p["expenses"] == 0.0

    @pytest.mark.asyncio
    async def test_bare_deposit_is_expense(self, specialist, retail_ctx):
        """'deposit to landlord' is a security deposit — an outflow.
        Bare 'deposit' is ambiguous; conservative default is expense."""
        result = await self._cashflow(specialist, retail_ctx, [
            {"content": "Made a $1,000 deposit to landlord for the lease", "score": 0.85},
        ])
        p = result.payload
        assert p["income"] == 0.0
        assert p["expenses"] == 1000.0
        assert p["category_totals"] == {"rent": 1000.0}

    @pytest.mark.asyncio
    async def test_directional_deposit_is_income(self, specialist, retail_ctx):
        """'deposit from customer' has direction — that's explicit inflow."""
        result = await self._cashflow(specialist, retail_ctx, [
            {"content": "Deposit from wholesale customer: $2,500", "score": 0.9},
        ])
        p = result.payload
        assert p["income"] == 2500.0
        assert p["expenses"] == 0.0

    @pytest.mark.asyncio
    async def test_got_paid_is_income(self, specialist, retail_ctx):
        """'got paid' is unambiguous inflow phrasing."""
        result = await self._cashflow(specialist, retail_ctx, [
            {"content": "Got paid $3,000 for the March project", "score": 0.9},
        ])
        p = result.payload
        assert p["income"] == 3000.0
        assert p["expenses"] == 0.0

    @pytest.mark.asyncio
    async def test_mixed_corpus_correct_net(self, specialist, retail_ctx):
        """End-to-end: a realistic mix of income, expenses with payment-method
        mentions, and an ambiguous deposit. The net must be correct."""
        result = await self._cashflow(specialist, retail_ctx, [
            {"content": "Invoice paid by client: $4,000", "score": 0.9},      # income
            {"content": "Paid by card: $250 for office supplies", "score": 0.8},  # expense (trap)
            {"content": "Security deposit $1,500 for new office", "score": 0.8},  # expense (trap)
            {"content": "Payment from retainer client: $2,000", "score": 0.9},    # income
            {"content": "Payroll $3,000 this month", "score": 0.85},          # expense
        ])
        p = result.payload
        assert p["income"] == 6000.0    # 4000 + 2000
        assert p["expenses"] == 4750.0  # 250 + 1500 + 3000
        assert p["net"] == 1250.0


# --- Parsing boundaries -----------------------------------------------------

class TestParsingBoundaries:
    """Document parser edge cases so behavior is intentional, not accidental."""

    @pytest.mark.asyncio
    async def test_dollar_sign_required_for_amount(self, specialist, retail_ctx):
        """Amounts must be $-prefixed. '350' alone is not parsed — prevents
        false positives on dates, counts, percentages. Deliberate constraint."""
        task = SpecialistTask(
            description="track the 350 from Acme Corp",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        # No amount recognized → asks for it
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert result.clarification_question == "How much was the amount?"

    @pytest.mark.asyncio
    async def test_first_amount_wins_when_multiple_present(self, specialist, retail_ctx):
        """Multiple dollar figures: parser takes the first. If this needs
        to change (e.g. 'two items: $100 and $200'), update both test
        and implementation intentionally."""
        task = SpecialistTask(
            description="track $150 to Acme Corp (was quoted $200 originally)",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 150.0  # first match, not 200
