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


class TestNotificationLifecycle:
    async def test_add_notification_assigns_status(self, store):
        notif = {
            "domain": "ea", "trigger_type": "morning_briefing",
            "priority": "MEDIUM", "title": "Briefing", "message": "Hello",
            "created_at": "2026-03-19T08:00:00+00:00",
        }
        notif_id = await store.add_notification(CID, notif)
        assert notif_id is not None
        stored = await store.get_notification(CID, notif_id)
        assert stored["status"] == "pending"
        assert stored["id"] == notif_id

    async def test_list_notifications_returns_pending(self, store):
        n = {"domain": "ea", "trigger_type": "test", "priority": "MEDIUM",
             "title": "T", "message": "M", "created_at": "2026-03-19T08:00:00+00:00"}
        notif_id = await store.add_notification(CID, n)
        result = await store.list_notifications(CID)
        assert len(result) == 1
        assert result[0]["id"] == notif_id

    async def test_mark_read_excludes_from_list(self, store):
        n = {"domain": "ea", "trigger_type": "test", "priority": "MEDIUM",
             "title": "T", "message": "M", "created_at": "2026-03-19T08:00:00+00:00"}
        notif_id = await store.add_notification(CID, n)
        await store.mark_notification_read(CID, notif_id)
        result = await store.list_notifications(CID)
        assert len(result) == 0
        # But notification still exists
        stored = await store.get_notification(CID, notif_id)
        assert stored["status"] == "read"

    async def test_snooze_hides_until_expiry(self, store):
        n = {"domain": "ea", "trigger_type": "test", "priority": "MEDIUM",
             "title": "T", "message": "M", "created_at": "2026-03-19T08:00:00+00:00"}
        notif_id = await store.add_notification(CID, n)
        snooze_until = datetime(2026, 3, 19, 11, 0, tzinfo=timezone.utc)
        await store.snooze_notification(CID, notif_id, snooze_until)

        # Before expiry — hidden
        now_before = datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc)
        result = await store.list_notifications(CID, now=now_before)
        assert len(result) == 0

        # After expiry — visible again
        now_after = datetime(2026, 3, 19, 11, 5, tzinfo=timezone.utc)
        result = await store.list_notifications(CID, now=now_after)
        assert len(result) == 1

    async def test_dismiss_hides_permanently(self, store):
        n = {"domain": "ea", "trigger_type": "test", "priority": "MEDIUM",
             "title": "T", "message": "M", "created_at": "2026-03-19T08:00:00+00:00"}
        notif_id = await store.add_notification(CID, n)
        await store.dismiss_notification(CID, notif_id)
        result = await store.list_notifications(CID)
        assert len(result) == 0
        stored = await store.get_notification(CID, notif_id)
        assert stored["status"] == "dismissed"

    async def test_get_notification_by_id(self, store):
        n = {"domain": "finance", "trigger_type": "anomaly", "priority": "HIGH",
             "title": "Anomaly", "message": "Unusual", "created_at": "2026-03-19T08:00:00+00:00"}
        notif_id = await store.add_notification(CID, n)
        stored = await store.get_notification(CID, notif_id)
        assert stored["domain"] == "finance"
        assert stored["title"] == "Anomaly"

    async def test_get_nonexistent_returns_none(self, store):
        result = await store.get_notification(CID, "notif_fake")
        assert result is None

    async def test_customer_isolation(self, store):
        n = {"domain": "ea", "trigger_type": "test", "priority": "MEDIUM",
             "title": "T", "message": "M", "created_at": "2026-03-19T08:00:00+00:00"}
        await store.add_notification(CID, n)
        result = await store.list_notifications(CID_OTHER)
        assert len(result) == 0

    async def test_notification_has_ttl(self, fake_redis, store):
        n = {"domain": "ea", "trigger_type": "test", "priority": "MEDIUM",
             "title": "T", "message": "M", "created_at": "2026-03-19T08:00:00+00:00"}
        notif_id = await store.add_notification(CID, n)
        key = f"proactive:{CID}:notif:{notif_id}"
        ttl = await fake_redis.ttl(key)
        assert ttl > 0  # Has TTL set


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
