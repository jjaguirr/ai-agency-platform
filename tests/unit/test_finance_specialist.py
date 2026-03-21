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


# --- Portfolio valuation via StockPriceClient seam --------------------------

class StubStockClient:
    """Test double conforming to StockPriceClient by shape only — no
    inheritance, no import of the protocol. Structural typing proves
    the seam works without coupling the stub to finance.py."""

    def __init__(self, prices: dict[str, float] | None = None, call_log: list | None = None):
        self._prices = prices or {}
        self._calls = call_log  # optional spy

    async def fetch(self, tickers: list[str]) -> dict[str, float]:
        if self._calls is not None:
            self._calls.append(list(tickers))
        return {t: self._prices[t] for t in tickers if t in self._prices}


class TestPortfolioAssessment:
    """'What's my portfolio worth?' must route to finance on lexical
    signals alone — portfolio/holdings are unambiguous finance terms."""

    @pytest.fixture
    def bare_ctx(self):
        return BusinessContext(business_name="Unknown Co")

    @pytest.mark.parametrize("msg", [
        "what's my portfolio worth right now?",
        "how are my stock holdings doing?",
        "give me a valuation on my shares",
    ])
    def test_portfolio_queries_route(self, bare_ctx, msg):
        fs = FinanceSpecialist()
        a = fs.assess_task(msg, bare_ctx)
        assert a.confidence >= 0.6, f"{msg!r} scored {a.confidence:.2f}"
        assert not a.is_strategic

    def test_should_i_sell_is_strategic(self, retail_ctx):
        """'should I sell my AAPL?' is advisory — EA keeps it.

        Uses retail_ctx (consistent with TestAssessStrategic) — a customer
        who owns stocks will have finance context signals. The guarantee:
        even at high confidence, the strategic flag keeps finance from
        claiming sell/buy decisions."""
        fs = FinanceSpecialist()
        a = fs.assess_task("should I sell my AAPL shares?", retail_ctx)
        assert a.confidence >= 0.4
        assert a.is_strategic


class TestPortfolioValuation:
    """Holdings come from domain_memories (customer data, EA-fetched).
    Prices come from the injected client (public data, specialist-fetched).
    The seam is the constructor — specialist never sees httpx."""

    @pytest.fixture
    def holdings_memories(self):
        return [
            {"content": "Bought 100 shares of AAPL at $150 back in January", "score": 0.95},
            {"content": "Picked up 50 MSFT last quarter", "score": 0.9},
            {"content": "Office rent $1,200 paid Feb 1", "score": 0.7},  # noise — must be ignored
        ]

    @pytest.mark.asyncio
    async def test_valuation_arithmetic(self, retail_ctx, holdings_memories):
        """Holdings × quotes = valuation. Non-holdings memories ignored."""
        client = StubStockClient({"AAPL": 200.0, "MSFT": 400.0})
        fs = FinanceSpecialist(stock_client=client)

        task = SpecialistTask(
            description="what's my portfolio worth?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=holdings_memories,
        )
        result = await fs.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        p = result.payload
        # 100 × $200 + 50 × $400 = $40,000
        assert p["total_value"] == 40000.0
        assert p["positions"] == [
            {"ticker": "AAPL", "shares": 100, "price": 200.0, "value": 20000.0},
            {"ticker": "MSFT", "shares": 50, "price": 400.0, "value": 20000.0},
        ]
        assert p["memories_consulted"] == 3  # looked at all, parsed 2 holdings
        # Summary states the total, not just "here's your portfolio"
        assert "$40,000.00" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_fetches_only_parsed_tickers(self, retail_ctx, holdings_memories):
        """Seam contract: specialist passes exactly the tickers it parsed,
        nothing more. No wildcard fetches, no hard-coded universe."""
        calls = []
        client = StubStockClient({"AAPL": 200.0, "MSFT": 400.0}, call_log=calls)
        fs = FinanceSpecialist(stock_client=client)

        await fs.execute_task(SpecialistTask(
            description="what's my portfolio worth?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=holdings_memories,
        ))

        assert len(calls) == 1
        assert sorted(calls[0]) == ["AAPL", "MSFT"]

    @pytest.mark.asyncio
    async def test_no_client_degrades_gracefully(self, retail_ctx, holdings_memories):
        """stock_client=None (default) → return holdings WITHOUT prices.
        Still COMPLETED — the customer gets their position list."""
        fs = FinanceSpecialist()  # no client injected

        result = await fs.execute_task(SpecialistTask(
            description="what's my portfolio worth?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=holdings_memories,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        p = result.payload
        assert p["total_value"] is None
        assert p["quotes_unavailable"] is True
        # Holdings still parsed and returned
        positions = {pos["ticker"]: pos["shares"] for pos in p["positions"]}
        assert positions == {"AAPL": 100, "MSFT": 50}
        # Summary tells the customer WHY there's no valuation
        assert "quote" in result.summary_for_ea.lower() or \
               "price" in result.summary_for_ea.lower()

    @pytest.mark.asyncio
    async def test_client_returns_empty_degrades_gracefully(self, retail_ctx, holdings_memories):
        """Seam contract says: raise nothing, return {} on failure.
        Specialist must handle empty quotes (API down) same as no client."""
        client = StubStockClient({})  # returns {} for any fetch
        fs = FinanceSpecialist(stock_client=client)

        result = await fs.execute_task(SpecialistTask(
            description="what's my portfolio worth?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=holdings_memories,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["total_value"] is None
        assert result.payload["quotes_unavailable"] is True

    @pytest.mark.asyncio
    async def test_partial_quotes_still_reports_what_it_has(self, retail_ctx, holdings_memories):
        """One ticker has a price, one doesn't (delisted? bad symbol?).
        Report the priced positions, flag the unpriced ones."""
        client = StubStockClient({"AAPL": 200.0})  # no MSFT price
        fs = FinanceSpecialist(stock_client=client)

        result = await fs.execute_task(SpecialistTask(
            description="what's my portfolio worth?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=holdings_memories,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        p = result.payload
        # Total reflects only what we could price
        assert p["total_value"] == 20000.0  # just the 100 AAPL
        assert p["unpriced_tickers"] == ["MSFT"]
        # Positions list includes both, with price=None for the unpriced one
        positions = {pos["ticker"]: pos for pos in p["positions"]}
        assert positions["AAPL"]["price"] == 200.0
        assert positions["MSFT"]["price"] is None

    @pytest.mark.asyncio
    async def test_no_holdings_in_memories(self, retail_ctx):
        """Portfolio query but no holdings on record → completed with
        empty positions, not NEEDS_CLARIFICATION (customer might just
        not have told us yet)."""
        client = StubStockClient({"AAPL": 200.0})
        fs = FinanceSpecialist(stock_client=client)

        result = await fs.execute_task(SpecialistTask(
            description="what's my portfolio worth?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[
                {"content": "Office rent $1,200", "score": 0.7},  # no holdings
            ],
        ))

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["positions"] == []
        assert result.payload["total_value"] == 0.0

    @pytest.mark.asyncio
    async def test_cash_flow_query_does_not_hit_client(self, retail_ctx):
        """Isolation: non-portfolio queries don't touch the stock client.
        Proves _is_portfolio_query gating works."""
        calls = []
        client = StubStockClient({}, call_log=calls)
        fs = FinanceSpecialist(stock_client=client)

        await fs.execute_task(SpecialistTask(
            description="what's my cash flow looking like?",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        ))

        assert calls == []  # client never invoked

    def test_no_httpx_import_in_finance(self):
        """Architectural assertion: finance.py depends on the contract,
        not the transport. grep for httpx → find nothing."""
        import src.agents.specialists.finance as finance_module
        import inspect
        source = inspect.getsource(finance_module)
        assert "httpx" not in source
        assert "aiohttp" not in source
        assert "requests" not in source


# --- Proactive V2: anomaly detection hook -----------------------------------
# The specialist optionally takes a ProactiveStateStore. When present,
# every completed expense entry records the amount into the transaction
# baseline, and if the amount exceeds 2× that baseline a domain event is
# staged. The heartbeat's DomainEventBehavior drains the queue on its
# next tick and routes the notification through the noise gate.
#
# The hook is side-channel only — it never changes the SpecialistResult.
# A Redis outage degrades to "no anomaly detection," not "can't track
# expenses."

import fakeredis.aioredis
from src.proactive.state import ProactiveStateStore


@pytest.fixture
def proactive_state():
    redis = fakeredis.aioredis.FakeRedis()
    return ProactiveStateStore(redis)


def _expense_task(description: str, ctx, cid: str = "cust_anomaly") -> SpecialistTask:
    return SpecialistTask(
        description=description,
        customer_id=cid,
        business_context=ctx,
        domain_memories=[],
    )


class TestAnomalyStaging:

    @pytest.mark.asyncio
    async def test_no_state_store_is_harmless(self, retail_ctx):
        """No proactive_state injected → nothing staged, nothing breaks.
        Current construction sites all pass no store, so this is the
        backward-compat contract."""
        fs = FinanceSpecialist()  # no proactive_state kwarg
        result = await fs.execute_task(
            _expense_task("track $9,999 payment to Acme Corp", retail_ctx),
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 9999.0

    @pytest.mark.asyncio
    async def test_expense_above_2x_baseline_stages_event(
        self, proactive_state, retail_ctx,
    ):
        cid = "cust_anomaly"
        # Seed baseline: 3 transactions averaging $100
        for _ in range(3):
            await proactive_state.record_transaction(cid, 100.0)

        fs = FinanceSpecialist(proactive_state=proactive_state)
        result = await fs.execute_task(
            _expense_task("track $250 payment to Acme Corp", retail_ctx, cid),
        )

        # The expense itself still completes normally — anomaly detection
        # is a side channel.
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 250.0

        events = await proactive_state.drain_domain_events(cid)
        assert len(events) == 1
        ev = events[0]
        assert ev["type"] == "finance_anomaly"
        assert ev["amount"] == 250.0
        assert ev["baseline"] == pytest.approx(100.0)
        # Category flows through so DomainEventBehavior can build a
        # meaningful cooldown key.
        assert "category" in ev

    @pytest.mark.asyncio
    async def test_expense_below_threshold_stages_nothing(
        self, proactive_state, retail_ctx,
    ):
        cid = "cust_anomaly"
        for _ in range(3):
            await proactive_state.record_transaction(cid, 100.0)

        fs = FinanceSpecialist(proactive_state=proactive_state)
        await fs.execute_task(
            _expense_task("track $150 payment to Acme Corp", retail_ctx, cid),
        )

        # 1.5× baseline → not anomalous
        assert await proactive_state.drain_domain_events(cid) == []

    @pytest.mark.asyncio
    async def test_no_baseline_yet_stages_nothing(
        self, proactive_state, retail_ctx,
    ):
        """Baseline needs ≥3 samples. A customer's very first expense
        mustn't trigger an anomaly against an empty history — everything
        looks huge compared to zero."""
        cid = "cust_fresh"
        fs = FinanceSpecialist(proactive_state=proactive_state)
        await fs.execute_task(
            _expense_task("track $5,000 payment to Acme Corp", retail_ctx, cid),
        )
        assert await proactive_state.drain_domain_events(cid) == []

    @pytest.mark.asyncio
    async def test_completed_expense_records_transaction(
        self, proactive_state, retail_ctx,
    ):
        """Every completed expense feeds the baseline, anomalous or not.
        Three normal expenses → baseline becomes available."""
        cid = "cust_building"
        fs = FinanceSpecialist(proactive_state=proactive_state)

        assert await proactive_state.get_transaction_baseline(cid) is None

        for amt in (100, 110, 90):
            await fs.execute_task(
                _expense_task(f"track ${amt} payment to Acme Corp", retail_ctx, cid),
            )

        baseline = await proactive_state.get_transaction_baseline(cid)
        assert baseline == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_clarification_result_does_not_record(
        self, proactive_state, retail_ctx,
    ):
        """NEEDS_CLARIFICATION → no amount extracted → nothing to record,
        nothing to flag. Proves the hook is guarded on COMPLETED status."""
        cid = "cust_vague"
        fs = FinanceSpecialist(proactive_state=proactive_state)
        result = await fs.execute_task(
            _expense_task("I spent some money on stuff", retail_ctx, cid),
        )
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert await proactive_state.get_transaction_baseline(cid) is None
        assert await proactive_state.drain_domain_events(cid) == []

    @pytest.mark.asyncio
    async def test_state_failure_does_not_break_expense_tracking(
        self, retail_ctx,
    ):
        """The proactive hook is best-effort. A dead Redis must not turn
        a working expense tracker into a broken one."""
        class BrokenStore:
            async def record_transaction(self, *a, **kw):
                raise ConnectionError("redis down")
            async def get_transaction_baseline(self, *a, **kw):
                raise ConnectionError("redis down")
            async def add_domain_event(self, *a, **kw):
                raise ConnectionError("redis down")

        fs = FinanceSpecialist(proactive_state=BrokenStore())
        result = await fs.execute_task(
            _expense_task("track $100 payment to Acme Corp", retail_ctx),
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 100.0

    @pytest.mark.asyncio
    async def test_summary_query_does_not_record(
        self, proactive_state, retail_ctx,
    ):
        """Summary queries mention dollar amounts but aren't new
        transactions. Recording them would poison the baseline."""
        cid = "cust_summary"
        fs = FinanceSpecialist(proactive_state=proactive_state)
        await fs.execute_task(SpecialistTask(
            description="how much did I spend on marketing last month?",
            customer_id=cid,
            business_context=retail_ctx,
            domain_memories=[{"content": "$500 Facebook ads"}],
        ))
        # No transaction recorded — baseline stays empty.
        assert await proactive_state.get_transaction_baseline(cid) is None

    @pytest.mark.asyncio
    async def test_events_isolated_per_customer(
        self, proactive_state, retail_ctx,
    ):
        for _ in range(3):
            await proactive_state.record_transaction("cust_a", 100.0)
            await proactive_state.record_transaction("cust_b", 100.0)

        fs = FinanceSpecialist(proactive_state=proactive_state)
        await fs.execute_task(
            _expense_task("track $300 payment to Acme Corp", retail_ctx, "cust_a"),
        )

        assert len(await proactive_state.drain_domain_events("cust_a")) == 1
        assert await proactive_state.drain_domain_events("cust_b") == []
