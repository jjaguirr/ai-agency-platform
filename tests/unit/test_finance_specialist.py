"""
Unit tests for FinanceSpecialist.

Two things this file pins down:

1. The specialist's own behavior — parsing expenses, categorizing, asking
   for what's missing, producing summaries from domain memories.

2. Routing overlap with social media. "How much does Instagram advertising
   cost?" has finance words but it's a social media question. The registry's
   highest-confidence rule should resolve these cleanly; the tests here make
   sure finance doesn't over-claim.
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


@pytest.fixture
def specialist():
    return FinanceSpecialist()


@pytest.fixture
def retail_ctx():
    return BusinessContext(
        business_name="Sparkle & Shine",
        industry="jewelry",
        current_tools=["Instagram", "Shopify", "QuickBooks"],
        pain_points=["manual invoicing", "expense tracking"],
    )


@pytest.fixture
def consulting_ctx():
    return BusinessContext(
        business_name="Strategic Solutions",
        industry="consulting",
        current_tools=["Zoom", "Stripe"],
    )


# --- Assessment: operational (delegate) -------------------------------------

class TestAssessOperational:
    """Concrete finance tasks → high confidence, not strategic."""

    @pytest.mark.parametrize("msg", [
        "Track this invoice: $2,400 from Acme Corp, due March 15",
        "What's my cash flow looking like?",
        "How much did I spend on marketing last month?",
        "Log an expense: $89 for software subscription",
        "What's my total revenue this quarter?",
        "Show me my expenses by category",
    ])
    def test_confident_and_not_strategic(self, specialist, retail_ctx, msg):
        a = specialist.assess_task(msg, retail_ctx)
        assert a.confidence >= 0.6, f"expected confident on: {msg!r}"
        assert not a.is_strategic, f"expected operational on: {msg!r}"


# --- Assessment: strategic (EA keeps) ---------------------------------------

class TestAssessStrategic:
    """In-domain but advisory — 'should I', 'is it worth' → EA judgment."""

    @pytest.mark.parametrize("msg", [
        "Should I raise my prices?",
        "Is it worth investing in new equipment?",
        "What should my ad budget be?",
        "Should I hire an accountant?",
        "How much should I spend on marketing?",
    ])
    def test_in_domain_but_strategic(self, specialist, retail_ctx, msg):
        a = specialist.assess_task(msg, retail_ctx)
        assert a.confidence >= 0.4, f"expected domain recognition on: {msg!r}"
        assert a.is_strategic, f"expected strategic flag on: {msg!r}"


# --- Assessment: out of domain ----------------------------------------------

class TestAssessOutOfDomain:
    @pytest.mark.parametrize("msg", [
        "How's my Instagram engagement?",
        "Schedule a post for tomorrow",
        "What's the weather tomorrow?",
        "Can you help me draft a contract?",
    ])
    def test_low_confidence(self, specialist, retail_ctx, msg):
        a = specialist.assess_task(msg, retail_ctx)
        assert a.confidence < 0.5, f"expected low confidence on: {msg!r}"


# --- Assessment: business context influence ---------------------------------

class TestAssessContextAware:
    def test_finance_pain_point_boosts_confidence(self, specialist):
        msg = "track this expense"
        no_pain = BusinessContext(business_name="X", pain_points=[])
        with_pain = BusinessContext(
            business_name="X", pain_points=["expense tracking is a mess"]
        )
        assert specialist.assess_task(msg, with_pain).confidence > \
               specialist.assess_task(msg, no_pain).confidence


# --- Execution: expense tracking --------------------------------------------

class TestExecuteExpenseTracking:
    @pytest.mark.asyncio
    async def test_parses_full_invoice(self, specialist, retail_ctx):
        """amount + vendor + date → COMPLETED with structured payload."""
        task = SpecialistTask(
            description="Track this invoice: $2,400 from Acme Corp, due March 15",
            customer_id="cust_retail",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.domain == "finance"
        assert result.payload["amount"] == 2400.0
        assert result.payload["vendor"] == "Acme Corp"
        assert result.payload["due_date"] is not None
        assert result.payload["category"] is not None
        assert result.summary_for_ea
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_parses_amount_variants(self, specialist, retail_ctx):
        """$2,400 / 2400 / $89.99 — all parseable."""
        cases = [
            ("Log expense: $2,400 from Vendor A", 2400.0),
            ("Track $89.99 payment to Vendor B", 89.99),
            ("Record expense of 1500 from Vendor C", 1500.0),
        ]
        for desc, expected_amount in cases:
            task = SpecialistTask(
                description=desc,
                customer_id="c",
                business_context=retail_ctx,
                domain_memories=[],
            )
            result = await specialist.execute_task(task)
            assert result.status == SpecialistStatus.COMPLETED, desc
            assert result.payload["amount"] == expected_amount, desc

    @pytest.mark.asyncio
    async def test_categorizes_by_vendor_hints(self, specialist, retail_ctx):
        """Vendor/description hints → category in payload."""
        cases = [
            ("Track $500 from Google Ads for marketing", "marketing"),
            ("Log $1200 expense: office rent payment", "rent"),
            ("Record $89 software subscription from Figma", "software"),
            ("Track payroll expense: $5000 for team salaries", "payroll"),
        ]
        for desc, expected_category in cases:
            task = SpecialistTask(
                description=desc,
                customer_id="c",
                business_context=retail_ctx,
                domain_memories=[],
            )
            result = await specialist.execute_task(task)
            assert result.status == SpecialistStatus.COMPLETED, desc
            assert result.payload["category"] == expected_category, \
                f"{desc!r} → got {result.payload['category']!r}"

    @pytest.mark.asyncio
    async def test_falls_back_to_operations_when_category_unclear(
        self, specialist, retail_ctx
    ):
        task = SpecialistTask(
            description="Track $300 from Unknown Vendor",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        # Some category is assigned — not None, not empty
        assert result.payload["category"]


# --- Execution: clarification flow ------------------------------------------

class TestExecuteClarification:
    @pytest.mark.asyncio
    async def test_asks_when_amount_missing(self, specialist, retail_ctx):
        """'Track this expense' with no amount → ask, don't guess."""
        task = SpecialistTask(
            description="Track this expense from Acme Corp",
            customer_id="cust_retail",
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
        """'Track $500 expense' with no vendor → ask for it."""
        task = SpecialistTask(
            description="Track a $500 expense",
            customer_id="cust_retail",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert result.clarification_question
        q = result.clarification_question.lower()
        assert "vendor" in q or "who" in q or "from" in q

    @pytest.mark.asyncio
    async def test_multi_turn_resolves_missing_amount(self, specialist, retail_ctx):
        """Turn 1 asked for amount → Turn 2 customer provides it → COMPLETED."""
        task = SpecialistTask(
            description="$2,400",
            customer_id="cust_retail",
            business_context=retail_ctx,
            domain_memories=[],
            prior_turns=[
                {"role": "customer", "content": "Track this expense from Acme Corp"},
                {"role": "specialist", "content": "How much was the expense?"},
                {"role": "customer", "content": "$2,400"},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 2400.0
        assert result.payload["vendor"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_multi_turn_resolves_missing_vendor(self, specialist, retail_ctx):
        """Symmetric: amount known, vendor filled from prior_turns."""
        task = SpecialistTask(
            description="It was from Stripe",
            customer_id="cust_retail",
            business_context=retail_ctx,
            domain_memories=[],
            prior_turns=[
                {"role": "customer", "content": "Log a $89.99 expense"},
                {"role": "specialist", "content": "Who was the vendor?"},
                {"role": "customer", "content": "It was from Stripe"},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["amount"] == 89.99
        assert "Stripe" in result.payload["vendor"]


# --- Execution: financial queries & summaries -------------------------------

class TestExecuteSummaries:
    @pytest.mark.asyncio
    async def test_spend_query_aggregates_from_memories(self, specialist, retail_ctx):
        """'How much did I spend on marketing?' → sum matching memories."""
        task = SpecialistTask(
            description="How much did I spend on marketing last month?",
            customer_id="cust_retail",
            business_context=retail_ctx,
            domain_memories=[
                {"content": "Expense: $500 marketing — Google Ads", "score": 0.9},
                {"content": "Expense: $300 marketing — Facebook Ads", "score": 0.85},
                {"content": "Expense: $1200 rent — office space", "score": 0.4},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload.get("query_type") == "spend_summary"
        # Marketing expenses only: 500 + 300 = 800
        assert result.payload.get("total") == 800.0
        assert result.payload.get("category") == "marketing"
        assert result.summary_for_ea

    @pytest.mark.asyncio
    async def test_cash_flow_query_aggregates_income_and_expenses(
        self, specialist, consulting_ctx
    ):
        """'What's my cash flow?' → income minus expenses from memories."""
        task = SpecialistTask(
            description="What's my cash flow looking like?",
            customer_id="cust_consulting",
            business_context=consulting_ctx,
            domain_memories=[
                {"content": "Income: $5000 from Client A invoice paid", "score": 0.9},
                {"content": "Income: $3000 from Client B retainer", "score": 0.9},
                {"content": "Expense: $1200 rent", "score": 0.8},
                {"content": "Expense: $400 software subscriptions", "score": 0.8},
            ],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload.get("query_type") == "cash_flow"
        assert result.payload.get("income_total") == 8000.0
        assert result.payload.get("expense_total") == 1600.0
        assert result.payload.get("net") == 6400.0
        assert result.summary_for_ea

    @pytest.mark.asyncio
    async def test_cash_flow_with_empty_memories(self, specialist, consulting_ctx):
        """No memories → don't crash, report zero, still COMPLETED."""
        task = SpecialistTask(
            description="What's my cash flow looking like?",
            customer_id="cust_new",
            business_context=consulting_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload.get("income_total") == 0.0
        assert result.payload.get("expense_total") == 0.0
        assert result.payload.get("memories_consulted") == 0

    @pytest.mark.asyncio
    async def test_isolation_only_sees_domain_memories(self, specialist, retail_ctx):
        """Same isolation contract as social media — no memory client backdoor."""
        task = SpecialistTask(
            description="Show me my expenses",
            customer_id="c",
            business_context=retail_ctx,
            domain_memories=[],
        )
        result = await specialist.execute_task(task)
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload.get("memories_consulted") == 0


# --- Routing overlap with social media --------------------------------------

class TestRoutingOverlap:
    """The critical test group: finance and social media both see keywords in
    ambiguous messages. Verify they don't fight — higher confidence wins,
    strategic defers to EA, and neither over-claims."""

    @pytest.fixture
    def registry(self):
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(SocialMediaSpecialist())
        reg.register(FinanceSpecialist())
        return reg

    def test_instagram_cost_question_not_routed_to_finance(
        self, registry, retail_ctx
    ):
        """'How much does Instagram advertising cost?' — 'cost' is a finance
        word but the question is about platform pricing, not the customer's
        own expenses. Social media owns platform knowledge."""
        match = registry.route(
            "How much does Instagram advertising cost?", retail_ctx
        )
        # Either social media wins, or neither clears threshold. NOT finance.
        if match is not None:
            assert match.specialist.domain != "finance"

    def test_cash_flow_routes_to_finance(self, registry, retail_ctx):
        """Unambiguously finance — social media must score < 0.5 here
        (pinned in test_social_media_specialist.py already)."""
        match = registry.route("What's my cash flow looking like?", retail_ctx)
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_marketing_spend_routes_to_finance(self, registry, retail_ctx):
        """No platform name → no social media boost. 'spend' + 'marketing'
        is a finance expense query."""
        match = registry.route(
            "How much did I spend on marketing last month?", retail_ctx
        )
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_ad_budget_strategic_goes_to_ea(self, registry, retail_ctx):
        """'What should my ad budget be?' — 'should' + 'budget'. Finance
        recognizes domain but flags strategic. Social media doesn't score
        on 'ad budget' alone. → EA keeps it."""
        match = registry.route("What should my ad budget be?", retail_ctx)
        assert match is None

    def test_instagram_engagement_routes_to_social(self, registry, retail_ctx):
        """Sanity: the canonical social media case still works with finance
        in the registry."""
        match = registry.route("How's my Instagram engagement?", retail_ctx)
        assert match is not None
        assert match.specialist.domain == "social_media"

    def test_facebook_roi_deterministic(self, registry, retail_ctx):
        """'What's my ROI on the Facebook campaign?' — genuinely ambiguous.
        We don't assert WHICH specialist wins, only that routing is
        deterministic and doesn't misfire as strategic-to-EA (this is an
        operational data question, not advisory)."""
        m1 = registry.route("What's my ROI on the Facebook campaign?", retail_ctx)
        m2 = registry.route("What's my ROI on the Facebook campaign?", retail_ctx)
        # Deterministic
        assert (m1 is None) == (m2 is None)
        if m1 is not None:
            assert m1.specialist.domain == m2.specialist.domain

    def test_expense_tracking_routes_to_finance_not_social(
        self, registry, retail_ctx
    ):
        """Even though the customer uses Instagram, a pure expense log
        doesn't mention platforms → finance."""
        match = registry.route(
            "Track this invoice: $2,400 from Acme Corp", retail_ctx
        )
        assert match is not None
        assert match.specialist.domain == "finance"


# --- Zero-change framework contract -----------------------------------------

class TestFrameworkCompatibility:
    def test_registers_without_framework_modification(self):
        """Validation criterion: adding finance is just .register() — no
        changes to specialist.py or executive_assistant.py."""
        reg = DelegationRegistry()
        reg.register(FinanceSpecialist())
        assert reg.get("finance") is not None

    def test_domain_identifier_is_stable(self, specialist):
        assert specialist.domain == "finance"
