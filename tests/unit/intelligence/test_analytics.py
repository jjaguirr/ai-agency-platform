"""Tests for AnalyticsService — aggregation queries for conversation intelligence."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.intelligence.analytics import AnalyticsService, compute_time_range


class TestComputeTimeRange:
    def test_24h(self):
        now = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
        start, end = compute_time_range("24h", now=now)
        assert end == now
        assert start == now - timedelta(hours=24)

    def test_7d(self):
        now = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
        start, end = compute_time_range("7d", now=now)
        assert end == now
        assert start == now - timedelta(days=7)

    def test_30d(self):
        now = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
        start, end = compute_time_range("30d", now=now)
        assert end == now
        assert start == now - timedelta(days=30)

    def test_custom(self):
        start, end = compute_time_range(
            "custom",
            start="2026-03-01T00:00:00Z",
            end="2026-03-21T00:00:00Z",
        )
        assert start == datetime(2026, 3, 1, tzinfo=timezone.utc)
        assert end == datetime(2026, 3, 21, tzinfo=timezone.utc)

    def test_custom_missing_dates_raises(self):
        with pytest.raises(ValueError, match="start and end"):
            compute_time_range("custom")


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


class TestAnalyticsServiceOverview:
    async def test_returns_structured_overview(self, mock_pool):
        pool, conn = mock_pool
        # overview query
        conn.fetchrow = AsyncMock(return_value={
            "total_conversations": 10,
            "total_delegations": 25,
            "avg_messages": 8.5,
            "escalation_count": 2,
            "unresolved_count": 3,
        })
        conn.fetch = AsyncMock(return_value=[])

        svc = AnalyticsService(pool)
        result = await svc.get_analytics(
            customer_id="cust_a",
            start=datetime(2026, 3, 14, tzinfo=timezone.utc),
            end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )

        overview = result["overview"]
        assert overview["total_conversations"] == 10
        assert overview["total_delegations"] == 25
        assert overview["avg_messages_per_conversation"] == 8.5
        # Computed: escalation_count / total_conversations = 2/10
        assert overview["escalation_rate"] == pytest.approx(0.2)
        # Computed: unresolved_count / total_conversations = 3/10
        assert overview["unresolved_rate"] == pytest.approx(0.3)


class TestAnalyticsServiceTenantIsolation:
    async def test_queries_include_customer_id(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={
            "total_conversations": 0,
            "total_delegations": 0,
            "avg_messages": 0.0,
            "escalation_count": 0,
            "unresolved_count": 0,
        })
        conn.fetch = AsyncMock(return_value=[])

        svc = AnalyticsService(pool)
        await svc.get_analytics(
            customer_id="cust_a",
            start=datetime(2026, 3, 14, tzinfo=timezone.utc),
            end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )

        # Verify customer_id is in every fetchrow query
        for c in conn.fetchrow.await_args_list:
            assert "cust_a" in c[0], f"customer_id missing from fetchrow args: {c[0]}"
        # Verify customer_id is in every fetch query (topics, specialists, trends)
        for c in conn.fetch.await_args_list:
            assert "cust_a" in c[0], f"customer_id missing from fetch args: {c[0]}"


class TestAnalyticsServiceEmptyData:
    async def test_empty_data_returns_zeroes(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={
            "total_conversations": 0,
            "total_delegations": 0,
            "avg_messages": None,
            "escalation_count": 0,
            "unresolved_count": 0,
        })
        conn.fetch = AsyncMock(return_value=[])

        svc = AnalyticsService(pool)
        result = await svc.get_analytics(
            customer_id="cust_empty",
            start=datetime(2026, 3, 14, tzinfo=timezone.utc),
            end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )

        overview = result["overview"]
        assert overview["total_conversations"] == 0
        assert overview["avg_messages_per_conversation"] == 0.0
        # Zero-denominator guard: rates must be 0.0, not raise ZeroDivisionError
        assert overview["escalation_rate"] == 0.0
        assert overview["unresolved_rate"] == 0.0
        assert result["topics"]["breakdown"] == []
        assert result["specialist_performance"] == []
        assert result["trends"]["conversations_by_day"] == []


class TestAnalyticsServiceTopicBreakdown:
    async def test_computes_percentages(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={
            "total_conversations": 5,
            "total_delegations": 5,
            "avg_messages": 4.0,
            "escalation_count": 0,
            "unresolved_count": 0,
        })
        # _topic_breakdown is the first fetch call; subsequent fetches return []
        conn.fetch = AsyncMock(side_effect=[
            # topics: 3 finance, 2 scheduling = 60%/40%
            [{"domain": "finance", "cnt": 3}, {"domain": "scheduling", "cnt": 2}],
            [],  # specialist_performance
            [],  # conversation_trend
            [],  # delegation_trend
        ])

        svc = AnalyticsService(pool)
        result = await svc.get_analytics(
            customer_id="cust_a",
            start=datetime(2026, 3, 14, tzinfo=timezone.utc),
            end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )

        topics = result["topics"]["breakdown"]
        assert len(topics) == 2
        assert topics[0] == {"domain": "finance", "count": 3, "percentage": 60.0}
        assert topics[1] == {"domain": "scheduling", "count": 2, "percentage": 40.0}


class TestAnalyticsServiceSpecialistPerformance:
    async def test_computes_rates_and_averages(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={
            "total_conversations": 5,
            "total_delegations": 10,
            "avg_messages": 6.0,
            "escalation_count": 0,
            "unresolved_count": 0,
        })
        conn.fetch = AsyncMock(side_effect=[
            [],  # topics
            # specialist_performance: 8 delegations, 6 completed, avg 3.2 turns,
            # 2 confirmations, avg 120.5s resolution
            [{
                "specialist_domain": "finance",
                "delegation_count": 8,
                "completed": 6,
                "avg_turns": 3.2,
                "conf_requested": 2,
                "avg_resolution_seconds": 120.5,
            }],
            [],  # conversation_trend
            [],  # delegation_trend
        ])

        svc = AnalyticsService(pool)
        result = await svc.get_analytics(
            customer_id="cust_a",
            start=datetime(2026, 3, 14, tzinfo=timezone.utc),
            end=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )

        specs = result["specialist_performance"]
        assert len(specs) == 1
        s = specs[0]
        assert s["domain"] == "finance"
        assert s["delegation_count"] == 8
        # 6/8 * 100 = 75.0
        assert s["success_rate"] == pytest.approx(75.0)
        assert s["avg_turns"] == pytest.approx(3.2)
        # 2/8 * 100 = 25.0
        assert s["confirmation_rate"] == pytest.approx(25.0)
        assert s["avg_resolution_seconds"] == pytest.approx(120.5)
