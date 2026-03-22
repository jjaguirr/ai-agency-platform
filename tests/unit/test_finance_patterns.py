"""
Unit tests for FinanceSpecialist pattern awareness.

The specialist already tracks transactions; these tests cover the pattern
layer on top: per-category running averages, anomaly mentions in the
response (not just the proactive side channel), budget tracking, and
period comparisons.

Pattern state lives in ProactiveStateStore (Redis); we use fakeredis.
"""
from __future__ import annotations

import pytest
import fakeredis.aioredis

from src.agents.specialists.finance import FinanceSpecialist
from src.agents.base.specialist import SpecialistTask, SpecialistStatus
from src.agents.executive_assistant import BusinessContext
from src.proactive.state import ProactiveStateStore


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(redis):
    return ProactiveStateStore(redis)


@pytest.fixture
def specialist(store):
    return FinanceSpecialist(proactive_state=store)


@pytest.fixture
def ctx():
    return BusinessContext(
        business_name="Acme Co",
        industry="consulting",
        current_tools=["QuickBooks"],
    )


def _task(desc: str, *, customer_id="c1", memories=None, prior_turns=None, ctx=None):
    return SpecialistTask(
        description=desc,
        customer_id=customer_id,
        business_context=ctx or BusinessContext(business_name="Acme Co"),
        domain_memories=memories or [],
        prior_turns=prior_turns or [],
    )


# --- Per-category running averages ------------------------------------------

class TestCategoryAverages:
    @pytest.mark.asyncio
    async def test_category_baseline_tracked_separately(self, store):
        """Software and marketing shouldn't share a baseline — a $50
        subscription isn't anomalous against $2000 ad spends."""
        for amt in (50.0, 55.0, 45.0):
            await store.record_category_transaction("c1", "software", amt)
        for amt in (2000.0, 1800.0, 2200.0):
            await store.record_category_transaction("c1", "marketing", amt)

        sw_avg = await store.get_category_baseline("c1", "software")
        mk_avg = await store.get_category_baseline("c1", "marketing")

        assert 45 <= sw_avg <= 55
        assert 1800 <= mk_avg <= 2200

    @pytest.mark.asyncio
    async def test_category_baseline_needs_min_samples(self, store):
        """Same 3-sample minimum as the global baseline."""
        await store.record_category_transaction("c1", "rent", 1200.0)
        assert await store.get_category_baseline("c1", "rent") is None

    @pytest.mark.asyncio
    async def test_anomaly_mentioned_in_response(self, specialist, store, ctx):
        """When a new expense is >2× the category average, the specialist
        mentions it in summary_for_ea — not just the proactive channel."""
        for amt in (200.0, 180.0, 220.0):
            await store.record_category_transaction("c1", "software", amt)

        result = await specialist.execute_task(_task(
            "track $800 for Adobe software subscription",
            customer_id="c1", ctx=ctx,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        text = result.summary_for_ea.lower()
        assert "higher than" in text or "usual" in text or "typical" in text

    @pytest.mark.asyncio
    async def test_normal_expense_no_anomaly_mention(
        self, specialist, store, ctx
    ):
        for amt in (200.0, 180.0, 220.0):
            await store.record_category_transaction("c1", "software", amt)

        result = await specialist.execute_task(_task(
            "track $210 for Figma software subscription",
            customer_id="c1", ctx=ctx,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        text = result.summary_for_ea.lower()
        assert "higher than" not in text


# --- Budget tracking --------------------------------------------------------

class TestBudgetTracking:
    @pytest.mark.asyncio
    async def test_budget_set_and_retrieved(self, store):
        await store.set_budget("c1", "marketing", 3000.0)
        b = await store.get_budget("c1", "marketing")
        assert b == 3000.0

    @pytest.mark.asyncio
    async def test_budget_mentioned_in_summary(self, specialist, store, ctx):
        """'You've spent $X of your $Y marketing budget this month.'"""
        await store.set_budget("c1", "marketing", 3000.0)
        # Spend-to-date comes from period totals.
        await store.record_period_spend("c1", "marketing", "2026-03", 2400.0)

        result = await specialist.execute_task(_task(
            "how much have I spent on marketing?",
            customer_id="c1", ctx=ctx,
            memories=[
                {"content": "paid $1200 for Facebook ads"},
                {"content": "paid $1200 for Google ads marketing"},
            ],
        ))

        assert result.status == SpecialistStatus.COMPLETED
        text = result.summary_for_ea
        assert "$3,000" in text or "3000" in text
        assert "budget" in text.lower()

    @pytest.mark.asyncio
    async def test_no_budget_no_mention(self, specialist, store, ctx):
        result = await specialist.execute_task(_task(
            "how much have I spent on marketing?",
            customer_id="c1", ctx=ctx,
            memories=[{"content": "paid $500 for ads"}],
        ))
        assert "budget" not in result.summary_for_ea.lower()


# --- Period comparisons -----------------------------------------------------

class TestPeriodComparison:
    @pytest.mark.asyncio
    async def test_period_spend_stored(self, store):
        await store.record_period_spend("c1", "marketing", "2026-02", 2000.0)
        await store.record_period_spend("c1", "marketing", "2026-03", 2300.0)

        feb = await store.get_period_spend("c1", "marketing", "2026-02")
        mar = await store.get_period_spend("c1", "marketing", "2026-03")
        assert feb == 2000.0
        assert mar == 2300.0

    @pytest.mark.asyncio
    async def test_summary_includes_period_comparison(
        self, specialist, store, ctx
    ):
        """'Marketing spend is up 15% from last month.'"""
        await store.record_period_spend("c1", "marketing", "2026-02", 2000.0)
        await store.record_period_spend("c1", "marketing", "2026-03", 2300.0)

        result = await specialist.execute_task(_task(
            "how much did I spend on marketing this month?",
            customer_id="c1", ctx=ctx,
            memories=[
                {"content": "paid $1200 for Facebook ads"},
                {"content": "paid $1100 for Google ads marketing"},
            ],
        ))

        text = result.summary_for_ea.lower()
        assert any(m in text for m in ("up", "down", "from last", "vs last"))


# --- Tenant isolation -------------------------------------------------------

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_category_stats_isolated_per_customer(self, store):
        for amt in (100.0, 100.0, 100.0):
            await store.record_category_transaction("c1", "software", amt)
        for amt in (500.0, 500.0, 500.0):
            await store.record_category_transaction("c2", "software", amt)

        assert await store.get_category_baseline("c1", "software") == 100.0
        assert await store.get_category_baseline("c2", "software") == 500.0

    @pytest.mark.asyncio
    async def test_budgets_isolated_per_customer(self, store):
        await store.set_budget("c1", "marketing", 1000.0)
        await store.set_budget("c2", "marketing", 5000.0)
        assert await store.get_budget("c1", "marketing") == 1000.0
        assert await store.get_budget("c2", "marketing") == 5000.0
