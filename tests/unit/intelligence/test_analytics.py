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

        assert result["overview"]["total_conversations"] == 10
        assert result["overview"]["total_delegations"] == 25
        assert result["overview"]["avg_messages_per_conversation"] == 8.5


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

        # Verify customer_id is in every query call
        for call in conn.fetchrow.await_args_list:
            args = call[0]
            assert "cust_a" in args, f"customer_id missing from query args: {args}"


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

        assert result["overview"]["total_conversations"] == 0
        assert result["overview"]["avg_messages_per_conversation"] == 0.0
        assert result["topics"]["breakdown"] == []
        assert result["specialist_performance"] == []
        assert result["trends"]["conversations_by_day"] == []
