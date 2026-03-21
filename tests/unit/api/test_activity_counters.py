"""
Daily activity counters — thin Redis wrapper for the dashboard's
"today at a glance" numbers.

Same pattern as ProactiveStateStore.increment_daily_count: per-customer,
per-metric, per-day keys with a 48h TTL. We don't own proactive triggers
(ProactiveStateStore does) so the endpoint reads those from there; this
module covers messages and delegations.
"""
from datetime import date

import pytest
import fakeredis.aioredis


@pytest.fixture
def r():
    return fakeredis.aioredis.FakeRedis()


# --- incr_messages ----------------------------------------------------------

class TestIncrMessages:
    @pytest.mark.asyncio
    async def test_first_increment_yields_one(self, r):
        from src.api.activity_counters import incr_messages, get_today
        await incr_messages(r, "cust_a")
        today = await get_today(r, "cust_a")
        assert today["messages"] == 1

    @pytest.mark.asyncio
    async def test_accumulates(self, r):
        from src.api.activity_counters import incr_messages, get_today
        for _ in range(5):
            await incr_messages(r, "cust_a")
        assert (await get_today(r, "cust_a"))["messages"] == 5

    @pytest.mark.asyncio
    async def test_tenant_isolated(self, r):
        """A's traffic doesn't bump B's counter."""
        from src.api.activity_counters import incr_messages, get_today
        await incr_messages(r, "cust_a")
        await incr_messages(r, "cust_a")
        await incr_messages(r, "cust_b")
        assert (await get_today(r, "cust_a"))["messages"] == 2
        assert (await get_today(r, "cust_b"))["messages"] == 1

    @pytest.mark.asyncio
    async def test_sets_ttl(self, r):
        """48h TTL — keys expire on their own, no cleanup job needed.
        Covers timezone variance (today might be tomorrow UTC) and gives
        the dashboard a grace window across the date boundary."""
        from src.api.activity_counters import incr_messages
        await incr_messages(r, "cust_a")
        key = f"activity:cust_a:messages:{date.today().isoformat()}"
        ttl = await r.ttl(key)
        assert 0 < ttl <= 48 * 3600


# --- incr_delegation --------------------------------------------------------

class TestIncrDelegation:
    @pytest.mark.asyncio
    async def test_per_domain(self, r):
        from src.api.activity_counters import incr_delegation, get_today
        await incr_delegation(r, "cust_a", "finance")
        await incr_delegation(r, "cust_a", "finance")
        await incr_delegation(r, "cust_a", "scheduling")
        d = (await get_today(r, "cust_a"))["delegations"]
        assert d["finance"] == 2
        assert d["scheduling"] == 1

    @pytest.mark.asyncio
    async def test_unseen_domain_absent(self, r):
        """Domains nobody delegated to today don't appear — the
        dashboard treats missing-key as zero, no need to pad."""
        from src.api.activity_counters import incr_delegation, get_today
        await incr_delegation(r, "cust_a", "finance")
        d = (await get_today(r, "cust_a"))["delegations"]
        assert "social_media" not in d

    @pytest.mark.asyncio
    async def test_sets_ttl(self, r):
        from src.api.activity_counters import incr_delegation
        await incr_delegation(r, "cust_a", "workflows")
        key = f"activity:cust_a:delegation:workflows:{date.today().isoformat()}"
        ttl = await r.ttl(key)
        assert 0 < ttl <= 48 * 3600


# --- get_today --------------------------------------------------------------

class TestGetToday:
    @pytest.mark.asyncio
    async def test_empty_state_returns_zeros(self, r):
        """Fresh customer, no traffic yet — well-defined zeros, not
        KeyError or None."""
        from src.api.activity_counters import get_today
        today = await get_today(r, "cust_new")
        assert today["messages"] == 0
        assert today["delegations"] == {}

    @pytest.mark.asyncio
    async def test_failure_returns_zeros(self, r):
        """Redis down → zeros. The activity endpoint is a dashboard
        nicety; it doesn't get to 500 the whole page over counter
        unavailability."""
        from unittest.mock import AsyncMock
        from src.api.activity_counters import get_today
        broken = AsyncMock()
        broken.get = AsyncMock(side_effect=ConnectionError("redis gone"))
        broken.mget = AsyncMock(side_effect=ConnectionError("redis gone"))
        today = await get_today(broken, "cust_a")
        assert today["messages"] == 0
        assert today["delegations"] == {}
