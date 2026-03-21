"""Tests for finance anomaly proactive trigger — transaction tracking and detection."""
import pytest
from datetime import datetime, timezone

import fakeredis.aioredis

from src.proactive.state import ProactiveStateStore
from src.proactive.triggers import Priority
from src.agents.specialists.finance import FinanceSpecialist


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


CID = "cust_finance_test"


class TestTransactionTracking:
    async def test_record_transaction_stores_in_redis(self, store):
        await store.record_transaction(CID, 100.0, "operations")
        stats = await store.get_transaction_stats(CID)
        assert stats["count"] == 1
        assert stats["total"] == 100.0

    async def test_running_average_computed_correctly(self, store):
        await store.record_transaction(CID, 100.0, "operations")
        await store.record_transaction(CID, 200.0, "marketing")
        await store.record_transaction(CID, 300.0, "software")
        stats = await store.get_transaction_stats(CID)
        assert stats["count"] == 3
        assert stats["average"] == 200.0
        assert stats["total"] == 600.0

    async def test_empty_history_returns_zero_stats(self, store):
        stats = await store.get_transaction_stats(CID)
        assert stats["count"] == 0
        assert stats["average"] == 0.0
        assert stats["total"] == 0.0

    async def test_get_latest_transaction(self, store):
        await store.record_transaction(CID, 100.0, "rent")
        await store.record_transaction(CID, 500.0, "marketing")
        latest = await store.get_latest_transaction(CID)
        assert latest is not None
        assert latest["amount"] == 500.0
        assert latest["category"] == "marketing"


class TestFinanceAnomalyDetection:
    async def test_no_anomaly_when_normal_spending(self, store):
        specialist = FinanceSpecialist(state_store=store)
        # Build history
        for _ in range(5):
            await store.record_transaction(CID, 200.0, "operations")
        # Latest is normal
        await store.record_transaction(CID, 200.0, "operations")

        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is None

    async def test_anomaly_when_2x_average(self, store):
        specialist = FinanceSpecialist(state_store=store)
        # Build history of $200 average
        for _ in range(5):
            await store.record_transaction(CID, 200.0, "operations")
        # Spike: $500 > 2x $200 average
        await store.record_transaction(CID, 500.0, "operations")

        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is not None
        assert result.trigger_type == "finance_anomaly"
        assert result.priority == Priority.HIGH
        assert result.domain == "finance"

    async def test_anomaly_threshold_configurable(self, store):
        specialist = FinanceSpecialist(state_store=store, anomaly_threshold=3.0)
        for _ in range(5):
            await store.record_transaction(CID, 200.0, "operations")
        # $500 is 2.5x average — below 3x threshold
        await store.record_transaction(CID, 500.0, "operations")

        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is None

    async def test_trigger_includes_transaction_details(self, store):
        specialist = FinanceSpecialist(state_store=store)
        for _ in range(5):
            await store.record_transaction(CID, 100.0, "operations")
        await store.record_transaction(CID, 300.0, "marketing")

        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is not None
        assert result.payload["amount"] == 300.0
        # Average of [100, 100, 100, 100, 100, 300] = 133.33
        assert 130.0 < result.payload["average"] < 140.0
        assert result.payload["ratio"] > 2.0
        assert result.payload["category"] == "marketing"

    async def test_exactly_at_threshold_does_not_trigger(self, store):
        """Boundary: amount/average == 2.0 should NOT trigger (< threshold, not >=)."""
        specialist = FinanceSpecialist(state_store=store, anomaly_threshold=2.0)
        # 5 transactions of $100 → average = $100, then $200 → ratio = 200/average
        # Average of [100,100,100,100,100,200] = 116.67, ratio = 200/116.67 ≈ 1.71 < 2.0
        for _ in range(5):
            await store.record_transaction(CID, 100.0, "operations")
        await store.record_transaction(CID, 200.0, "operations")

        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is None

    async def test_just_above_threshold_triggers(self, store):
        """Amount that produces ratio just above 2.0x triggers."""
        specialist = FinanceSpecialist(state_store=store, anomaly_threshold=2.0)
        # 10 transactions of $100 → avg dominated by $100
        for _ in range(10):
            await store.record_transaction(CID, 100.0, "operations")
        # $300 with avg ~118.18 → ratio ~2.54 > 2.0
        await store.record_transaction(CID, 300.0, "operations")

        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is not None
        assert result.trigger_type == "finance_anomaly"

    async def test_no_trigger_without_history(self, store):
        specialist = FinanceSpecialist(state_store=store)
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is None

    async def test_no_trigger_with_single_transaction(self, store):
        specialist = FinanceSpecialist(state_store=store)
        await store.record_transaction(CID, 500.0, "operations")
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        # Need at least 2 transactions (1 for history, 1 current) to compare
        assert result is None

    async def test_no_state_store_returns_none(self):
        specialist = FinanceSpecialist()
        from src.agents.executive_assistant import BusinessContext
        result = await specialist.proactive_check(CID, BusinessContext())
        assert result is None
