"""
ProactiveStateStore — Redis-backed operational metadata for the proactive
system.

Key prefix: proactive:{customer_id}:*
  :cooldown:{key}       → ISO timestamp of last fire
  :daily:{YYYY-MM-DD}   → count (int, expires after 48h)
  :last_briefing        → ISO timestamp
  :last_interaction     → ISO timestamp
  :last_nudge           → ISO timestamp
  :followups            → JSON list of Commitment dicts
  :notifications        → JSON list of pending trigger dicts
  :phone                → last-seen WhatsApp E.164 (for outbound routing)

Everything JSON-serializable. No pickles.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.agents.proactive.state import ProactiveStateStore


pytestmark = pytest.mark.asyncio


class TestCooldownState:
    async def test_unset_cooldown_returns_none(self, state_store):
        assert await state_store.get_cooldown("cust", "key") is None

    async def test_roundtrip_cooldown(self, state_store, fixed_now):
        await state_store.set_cooldown("cust", "key", fixed_now)
        got = await state_store.get_cooldown("cust", "key")
        assert got == fixed_now

    async def test_cooldown_is_per_customer(self, state_store, fixed_now):
        await state_store.set_cooldown("cust_a", "key", fixed_now)
        assert await state_store.get_cooldown("cust_b", "key") is None


class TestDailyCounter:
    async def test_initial_count_is_zero(self, state_store):
        assert await state_store.get_daily_count("cust", "2026-03-18") == 0

    async def test_increment_bumps_count(self, state_store):
        await state_store.incr_daily_count("cust", "2026-03-18")
        await state_store.incr_daily_count("cust", "2026-03-18")
        assert await state_store.get_daily_count("cust", "2026-03-18") == 2

    async def test_different_days_are_distinct(self, state_store):
        await state_store.incr_daily_count("cust", "2026-03-18")
        assert await state_store.get_daily_count("cust", "2026-03-19") == 0


class TestTimestamps:
    async def test_last_briefing_roundtrip(self, state_store, fixed_now):
        assert await state_store.get_last_briefing("cust") is None
        await state_store.set_last_briefing("cust", fixed_now)
        assert await state_store.get_last_briefing("cust") == fixed_now

    async def test_last_interaction_roundtrip(self, state_store, fixed_now):
        await state_store.set_last_interaction("cust", fixed_now)
        assert await state_store.get_last_interaction("cust") == fixed_now

    async def test_last_nudge_roundtrip(self, state_store, fixed_now):
        await state_store.set_last_nudge("cust", fixed_now)
        assert await state_store.get_last_nudge("cust") == fixed_now


class TestFollowups:
    async def test_empty_followups(self, state_store):
        assert await state_store.list_followups("cust") == []

    async def test_add_and_list_followups(self, state_store, fixed_now):
        from src.agents.proactive.followups import Commitment
        c = Commitment(
            text="call John", due=fixed_now, raw="remind me to call John by Wednesday"
        )
        await state_store.add_followup("cust", c)
        got = await state_store.list_followups("cust")
        assert len(got) == 1
        assert got[0].text == "call John"
        assert got[0].due == fixed_now

    async def test_remove_followup(self, state_store, fixed_now):
        from src.agents.proactive.followups import Commitment
        c = Commitment(text="x", due=fixed_now, raw="r")
        await state_store.add_followup("cust", c)
        await state_store.remove_followup("cust", c.id)
        assert await state_store.list_followups("cust") == []


class TestNotifications:
    async def test_enqueue_and_drain_notifications(self, state_store, fixed_now):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        t = ProactiveTrigger(
            domain="ea", trigger_type="briefing", priority=Priority.MEDIUM,
            title="Morning", payload={}, suggested_message="hi",
            created_at=fixed_now,
        )
        await state_store.enqueue_notification("cust", t)
        pending = await state_store.drain_notifications("cust")
        assert len(pending) == 1
        assert pending[0].title == "Morning"
        # Drained → empty
        assert await state_store.drain_notifications("cust") == []

    async def test_notifications_ordered_by_priority_then_time(self, state_store, fixed_now):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        med = ProactiveTrigger(domain="a", trigger_type="x", priority=Priority.MEDIUM,
                               title="med", payload={}, suggested_message="m",
                               created_at=fixed_now)
        urg = ProactiveTrigger(domain="a", trigger_type="x", priority=Priority.URGENT,
                               title="urg", payload={}, suggested_message="m",
                               created_at=fixed_now + timedelta(hours=1))
        await state_store.enqueue_notification("cust", med)
        await state_store.enqueue_notification("cust", urg)
        drained = await state_store.drain_notifications("cust")
        assert [t.title for t in drained] == ["urg", "med"]


class TestPhone:
    async def test_phone_roundtrip(self, state_store):
        await state_store.set_phone("cust", "+14155551234")
        assert await state_store.get_phone("cust") == "+14155551234"

    async def test_phone_unset_returns_none(self, state_store):
        assert await state_store.get_phone("cust") is None


class TestPersistenceAcrossStoreInstances:
    """
    State must survive 'EA restarts' — simulated by building a second
    ProactiveStateStore against the same Redis.
    """
    async def test_survives_new_store_instance(self, fake_redis, clock, fixed_now):
        s1 = ProactiveStateStore(redis=fake_redis, clock=clock)
        await s1.set_last_interaction("cust", fixed_now)

        s2 = ProactiveStateStore(redis=fake_redis, clock=clock)
        assert await s2.get_last_interaction("cust") == fixed_now
