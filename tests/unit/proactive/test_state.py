"""Tests for ProactiveStateStore — Redis-backed proactive state."""
import json
import pytest
from datetime import datetime, timezone, timedelta

from src.proactive.state import ProactiveStateStore


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def store_factory(fake_redis):
    """Factory to create a new store instance against the same Redis."""
    def _make():
        return ProactiveStateStore(fake_redis)
    return _make


CID = "cust_test_abc"
CID_OTHER = "cust_other_xyz"


class TestCooldown:
    async def test_not_cooling_down_initially(self, store):
        assert not await store.is_cooling_down(CID, "briefing")

    async def test_record_cooldown_then_active(self, store):
        await store.record_cooldown(CID, "briefing", window_seconds=3600)
        assert await store.is_cooling_down(CID, "briefing")

    async def test_different_keys_independent(self, store):
        await store.record_cooldown(CID, "briefing", window_seconds=3600)
        assert not await store.is_cooling_down(CID, "anomaly")

    async def test_cooldown_uses_redis_ttl(self, fake_redis, store):
        await store.record_cooldown(CID, "briefing", window_seconds=60)
        key = f"proactive:{CID}:cooldown:briefing"
        ttl = await fake_redis.ttl(key)
        assert 0 < ttl <= 60


class TestLastBriefingTime:
    async def test_default_none(self, store):
        assert await store.get_last_briefing_time(CID) is None

    async def test_set_and_get(self, store):
        t = datetime(2026, 3, 19, 8, 0, tzinfo=timezone.utc)
        await store.set_last_briefing_time(CID, t)
        result = await store.get_last_briefing_time(CID)
        assert result == t


class TestLastInteractionTime:
    async def test_default_none(self, store):
        assert await store.get_last_interaction_time(CID) is None

    async def test_update_and_get(self, store):
        await store.update_last_interaction_time(CID)
        result = await store.get_last_interaction_time(CID)
        assert result is not None
        assert isinstance(result, datetime)


class TestFollowUps:
    async def test_empty_initially(self, store):
        assert await store.list_follow_ups(CID) == []

    async def test_add_and_list(self, store):
        fu = {"id": "fu_1", "commitment": "call John", "deadline": "2026-03-20T10:00:00+00:00"}
        await store.add_follow_up(CID, fu)
        result = await store.list_follow_ups(CID)
        assert len(result) == 1
        assert result[0]["commitment"] == "call John"

    async def test_add_multiple(self, store):
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        await store.add_follow_up(CID, {"id": "fu_2", "commitment": "send proposal"})
        result = await store.list_follow_ups(CID)
        assert len(result) == 2

    async def test_remove(self, store):
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        await store.add_follow_up(CID, {"id": "fu_2", "commitment": "send proposal"})
        await store.remove_follow_up(CID, "fu_1")
        result = await store.list_follow_ups(CID)
        assert len(result) == 1
        assert result[0]["id"] == "fu_2"

    async def test_remove_nonexistent_is_noop(self, store):
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        await store.remove_follow_up(CID, "fu_nonexistent")
        assert len(await store.list_follow_ups(CID)) == 1


class TestDailyCount:
    async def test_default_zero(self, store):
        assert await store.get_daily_count(CID) == 0

    async def test_increment(self, store):
        count = await store.increment_daily_count(CID)
        assert count == 1
        count = await store.increment_daily_count(CID)
        assert count == 2

    async def test_get_after_increment(self, store):
        await store.increment_daily_count(CID)
        await store.increment_daily_count(CID)
        assert await store.get_daily_count(CID) == 2


class TestPendingNotifications:
    async def test_empty_initially(self, store):
        assert await store.pop_pending_notifications(CID) == []

    async def test_add_and_pop(self, store):
        notif = {"id": "n_1", "message": "Good morning!", "priority": "MEDIUM"}
        await store.add_pending_notification(CID, notif)
        result = await store.pop_pending_notifications(CID)
        assert len(result) == 1
        assert result[0]["message"] == "Good morning!"

    async def test_pop_clears_notifications(self, store):
        await store.add_pending_notification(CID, {"id": "n_1", "message": "Hello"})
        await store.pop_pending_notifications(CID)
        assert await store.pop_pending_notifications(CID) == []

    async def test_multiple_notifications_preserved_order(self, store):
        await store.add_pending_notification(CID, {"id": "n_1", "message": "First"})
        await store.add_pending_notification(CID, {"id": "n_2", "message": "Second"})
        result = await store.pop_pending_notifications(CID)
        assert len(result) == 2
        assert result[0]["message"] == "First"
        assert result[1]["message"] == "Second"


class TestKeyPrefixAndIsolation:
    async def test_keys_use_proactive_prefix(self, fake_redis, store):
        await store.record_cooldown(CID, "test_key", window_seconds=60)
        keys = [k.decode() async for k in fake_redis.scan_iter("proactive:*")]
        assert any(k.startswith(f"proactive:{CID}:") for k in keys)

    async def test_customer_isolation(self, store):
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        assert await store.list_follow_ups(CID_OTHER) == []

    async def test_state_survives_store_reinstantiation(self, store_factory):
        store1 = store_factory()
        await store1.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        await store1.set_last_briefing_time(
            CID, datetime(2026, 3, 19, 8, 0, tzinfo=timezone.utc)
        )

        store2 = store_factory()
        follow_ups = await store2.list_follow_ups(CID)
        assert len(follow_ups) == 1
        briefing_time = await store2.get_last_briefing_time(CID)
        assert briefing_time is not None


# --- V2: Domain event staging ------------------------------------------------

class TestDomainEvents:
    """Specialists stage events at detection time; heartbeat drains on tick."""

    async def test_add_then_drain_roundtrip(self, store):
        await store.add_domain_event(CID, {
            "type": "finance_anomaly", "amount": 500.0, "baseline": 100.0,
        })
        events = await store.drain_domain_events(CID)
        assert len(events) == 1
        assert events[0]["type"] == "finance_anomaly"
        assert events[0]["amount"] == 500.0

    async def test_drain_is_destructive(self, store):
        await store.add_domain_event(CID, {"type": "x"})
        await store.drain_domain_events(CID)
        assert await store.drain_domain_events(CID) == []

    async def test_drain_empty_is_empty_list(self, store):
        assert await store.drain_domain_events(CID) == []

    async def test_preserves_fifo_order(self, store):
        await store.add_domain_event(CID, {"type": "a"})
        await store.add_domain_event(CID, {"type": "b"})
        await store.add_domain_event(CID, {"type": "c"})
        events = await store.drain_domain_events(CID)
        assert [e["type"] for e in events] == ["a", "b", "c"]

    async def test_isolated_per_customer(self, store):
        await store.add_domain_event(CID, {"type": "mine"})
        await store.add_domain_event(CID_OTHER, {"type": "theirs"})
        mine = await store.drain_domain_events(CID)
        theirs = await store.drain_domain_events(CID_OTHER)
        assert [e["type"] for e in mine] == ["mine"]
        assert [e["type"] for e in theirs] == ["theirs"]


# --- V2: Transaction baseline ------------------------------------------------

class TestTransactionBaseline:
    """Running average for finance anomaly detection. Simple count/sum —
    no decay, no outlier rejection. Fancy enough for 'is this 2× normal?'."""

    async def test_no_transactions_no_baseline(self, store):
        assert await store.get_transaction_baseline(CID) is None

    async def test_below_min_samples_no_baseline(self, store):
        # Fewer than 3 samples → None. Avoids noisy early triggers when
        # a customer's first transaction happens to be large.
        await store.record_transaction(CID, 100.0)
        await store.record_transaction(CID, 200.0)
        assert await store.get_transaction_baseline(CID) is None

    async def test_baseline_is_mean(self, store):
        await store.record_transaction(CID, 100.0)
        await store.record_transaction(CID, 200.0)
        await store.record_transaction(CID, 300.0)
        baseline = await store.get_transaction_baseline(CID)
        assert baseline == pytest.approx(200.0)

    async def test_baseline_updates_incrementally(self, store):
        for _ in range(3):
            await store.record_transaction(CID, 100.0)
        assert await store.get_transaction_baseline(CID) == pytest.approx(100.0)
        await store.record_transaction(CID, 500.0)
        # (300 + 500) / 4 = 200
        assert await store.get_transaction_baseline(CID) == pytest.approx(200.0)

    async def test_isolated_per_customer(self, store):
        for _ in range(3):
            await store.record_transaction(CID, 100.0)
        for _ in range(3):
            await store.record_transaction(CID_OTHER, 1000.0)
        assert await store.get_transaction_baseline(CID) == pytest.approx(100.0)
        assert await store.get_transaction_baseline(CID_OTHER) == pytest.approx(1000.0)
