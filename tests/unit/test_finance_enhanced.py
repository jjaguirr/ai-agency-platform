"""
Tests for finance specialist enhancements: pattern awareness.

- Running averages: mention deviations ("higher than usual")
- Budget tracking: reference budget limits
- Period comparisons: include vs baseline
- All enhancements degrade gracefully without interaction_context
"""
import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock

from src.agents.base.specialist import SpecialistTask, SpecialistStatus
from src.agents.context import InteractionContext, FinanceSnapshot, CustomerPreferences
from src.agents.executive_assistant import BusinessContext
from src.agents.specialists.finance import FinanceSpecialist
from src.proactive.state import ProactiveStateStore


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def specialist(store):
    return FinanceSpecialist(proactive_state=store)


@pytest.fixture
def ctx():
    return BusinessContext(
        business_name="Sparkle & Shine",
        industry="jewelry",
        current_tools=["QuickBooks"],
    )


CUSTOMER_ID = "cust_fin_test"


def _task(description, ctx, *, interaction_context=None, memories=None):
    return SpecialistTask(
        description=description,
        customer_id=CUSTOMER_ID,
        business_context=ctx,
        domain_memories=memories or [],
        interaction_context=interaction_context,
    )


# --- ProactiveStateStore: budget methods ------------------------------------

class TestBudgetStorage:
    @pytest.mark.asyncio
    async def test_set_and_get_budget(self, store):
        await store.set_budget(CUSTOMER_ID, "marketing", 3000.0)
        result = await store.get_budget(CUSTOMER_ID, "marketing")
        assert result == 3000.0

    @pytest.mark.asyncio
    async def test_get_budget_returns_none_when_not_set(self, store):
        result = await store.get_budget(CUSTOMER_ID, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_budgets(self, store):
        await store.set_budget(CUSTOMER_ID, "marketing", 3000.0)
        await store.set_budget(CUSTOMER_ID, "software", 500.0)
        budgets = await store.get_all_budgets(CUSTOMER_ID)
        assert budgets == {"marketing": 3000.0, "software": 500.0}

    @pytest.mark.asyncio
    async def test_get_all_budgets_empty(self, store):
        budgets = await store.get_all_budgets(CUSTOMER_ID)
        assert budgets == {}


# --- Expense entry: deviation notes -----------------------------------------

class TestExpenseDeviation:
    @pytest.mark.asyncio
    async def test_notes_deviation_when_above_baseline(self, specialist, ctx, store):
        """Amount > 2x baseline → summary mentions 'higher than usual'."""
        # Build a baseline: 4 transactions at $200
        for _ in range(4):
            await store.record_transaction(CUSTOMER_ID, 200.0)

        ic = InteractionContext(
            finance_snapshot=FinanceSnapshot(transaction_baseline=200.0),
        )
        task = _task("track $500 to Acme Corp for marketing", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "higher than your usual" in result.summary_for_ea.lower()

    @pytest.mark.asyncio
    async def test_no_deviation_note_within_normal_range(self, specialist, ctx, store):
        """Amount within normal range → no deviation note."""
        for _ in range(4):
            await store.record_transaction(CUSTOMER_ID, 200.0)

        ic = InteractionContext(
            finance_snapshot=FinanceSnapshot(transaction_baseline=200.0),
        )
        task = _task("track $250 to Acme Corp for marketing", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "higher than" not in result.summary_for_ea.lower()

    @pytest.mark.asyncio
    async def test_no_deviation_note_without_context(self, specialist, ctx):
        """No interaction_context → existing behavior, no crash."""
        task = _task("track $5000 to Acme Corp for marketing", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "higher than" not in result.summary_for_ea.lower()


# --- Expense entry: budget tracking -----------------------------------------

class TestBudgetTracking:
    @pytest.mark.asyncio
    async def test_mentions_budget_remaining(self, specialist, ctx, store):
        """Budget set for category → response mentions remaining budget."""
        await store.set_budget(CUSTOMER_ID, "marketing", 3000.0)

        ic = InteractionContext(
            finance_snapshot=FinanceSnapshot(
                budget_status={"marketing": {"limit": 3000.0, "spent": 2400.0}},
            ),
        )
        task = _task("track $200 to Acme Corp for marketing", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        summary_lower = result.summary_for_ea.lower()
        assert "budget" in summary_lower
        # Should mention the spent amount and the limit
        assert "$3,000" in result.summary_for_ea or "$2,600" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_budget_exceeded_warning(self, specialist, ctx, store):
        """Expense pushes past budget limit → 'over your budget' warning."""
        await store.set_budget(CUSTOMER_ID, "marketing", 500.0)

        ic = InteractionContext(
            finance_snapshot=FinanceSnapshot(
                budget_status={"marketing": {"limit": 500.0, "spent": 450.0}},
            ),
        )
        task = _task("track $200 to Acme Corp for marketing", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "over" in result.summary_for_ea.lower()

    @pytest.mark.asyncio
    async def test_no_budget_mention_without_budget_set(self, specialist, ctx):
        """No budget configured → no budget mention."""
        ic = InteractionContext(
            finance_snapshot=FinanceSnapshot(),
        )
        task = _task("track $200 to Acme Corp for marketing", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "budget" not in result.summary_for_ea.lower()


# --- Summary: baseline comparison ------------------------------------------

class TestSummaryComparison:
    @pytest.mark.asyncio
    async def test_summary_includes_baseline_context(self, specialist, ctx):
        """When baseline available, summary mentions comparison."""
        ic = InteractionContext(
            finance_snapshot=FinanceSnapshot(transaction_baseline=300.0),
        )
        memories = [
            {"content": "Tracked $400 for marketing ads"},
            {"content": "Tracked $200 for software subscription"},
        ]
        task = _task("how much did I spend?", ctx, interaction_context=ic, memories=memories)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        # Should contain baseline comparison with dollar amounts
        summary_lower = result.summary_for_ea.lower()
        assert "baseline" in summary_lower or "average" in summary_lower
        # Must reference the baseline figure from context
        assert "$300" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_summary_no_baseline_note_without_context(self, specialist, ctx):
        """No interaction_context → no baseline mention in summary."""
        memories = [
            {"content": "Tracked $400 for marketing ads"},
        ]
        task = _task("how much did I spend?", ctx, memories=memories)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "baseline" not in result.summary_for_ea.lower()
        assert "average" not in result.summary_for_ea.lower()
        # Should still produce a useful spending summary
        assert "$400" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_deviation_at_exactly_2x_does_not_trigger(self, specialist, ctx, store):
        """Amount == 2x baseline → threshold is >2x, so no note."""
        for _ in range(4):
            await store.record_transaction(CUSTOMER_ID, 200.0)

        ic = InteractionContext(
            finance_snapshot=FinanceSnapshot(transaction_baseline=200.0),
        )
        task = _task("track $400 to Acme Corp for marketing", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "higher than your usual" not in result.summary_for_ea.lower()
