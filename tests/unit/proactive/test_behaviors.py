"""Tests for built-in proactive behaviors: morning briefing, follow-up tracker, idle nudge."""
import pytest
from datetime import datetime, timezone, timedelta

from src.proactive.behaviors import (
    MorningBriefingBehavior,
    FollowUpTrackerBehavior,
    IdleNudgeBehavior,
    BehaviorConfig,
)
from src.proactive.state import ProactiveStateStore
from src.proactive.triggers import Priority


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


CID = "cust_behavior_test"


def _clock(dt: datetime):
    return lambda: dt


class TestMorningBriefing:
    async def test_triggers_at_configured_hour(self, store):
        # 8:00 UTC — default briefing hour
        behavior = MorningBriefingBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 8, 5, tzinfo=timezone.utc))
        )
        # Add a follow-up so briefing has data
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(briefing_hour=8, timezone="UTC")
        result = await behavior.check(CID, cfg)
        assert result is not None
        assert result.trigger_type == "morning_briefing"
        assert result.priority == Priority.LOW

    async def test_does_not_trigger_before_hour(self, store):
        behavior = MorningBriefingBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 7, 0, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(briefing_hour=8, timezone="UTC")
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_does_not_trigger_twice_same_day(self, store):
        behavior = MorningBriefingBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        # Mark as already sent today
        await store.set_last_briefing_time(
            CID, datetime(2026, 3, 19, 8, 0, tzinfo=timezone.utc)
        )
        cfg = BehaviorConfig(briefing_hour=8, timezone="UTC")
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_skips_if_no_data(self, store):
        behavior = MorningBriefingBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 8, 5, tzinfo=timezone.utc))
        )
        cfg = BehaviorConfig(briefing_hour=8, timezone="UTC")
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_includes_follow_ups_in_payload(self, store):
        behavior = MorningBriefingBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 8, 5, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        await store.add_follow_up(CID, {"id": "fu_2", "commitment": "send proposal"})
        cfg = BehaviorConfig(briefing_hour=8, timezone="UTC")
        result = await behavior.check(CID, cfg)
        assert result is not None
        assert len(result.payload.get("follow_ups", [])) == 2

    async def test_respects_customer_timezone(self, store):
        # 12:00 UTC = 08:00 America/New_York (EDT, UTC-4)
        behavior = MorningBriefingBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 12, 5, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(briefing_hour=8, timezone="America/New_York")
        result = await behavior.check(CID, cfg)
        assert result is not None

    async def test_default_hour_is_8(self):
        cfg = BehaviorConfig()
        assert cfg.briefing_hour == 8


class TestFollowUpTracker:
    async def test_triggers_near_deadline(self, store):
        # Now is 2026-03-19 10:00 UTC, deadline is in 12 hours
        behavior = FollowUpTrackerBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {
            "id": "fu_1",
            "commitment": "call John",
            "deadline": "2026-03-19T22:00:00+00:00",
        })
        results = await behavior.check(CID)
        assert len(results) == 1
        assert "call John" in results[0].suggested_message

    async def test_does_not_trigger_far_from_deadline(self, store):
        behavior = FollowUpTrackerBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc))
        )
        # Deadline is 5 days away
        await store.add_follow_up(CID, {
            "id": "fu_1",
            "commitment": "call John",
            "deadline": "2026-03-24T10:00:00+00:00",
        })
        results = await behavior.check(CID)
        assert len(results) == 0

    async def test_triggers_for_overdue(self, store):
        behavior = FollowUpTrackerBehavior(
            store, clock=_clock(datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {
            "id": "fu_1",
            "commitment": "send proposal",
            "deadline": "2026-03-19T17:00:00+00:00",
        })
        results = await behavior.check(CID)
        assert len(results) == 1
        assert results[0].priority == Priority.HIGH  # Overdue = higher priority

    async def test_includes_commitment_text(self, store):
        behavior = FollowUpTrackerBehavior(
            store, clock=_clock(datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {
            "id": "fu_1",
            "commitment": "email Sarah the contract",
            "deadline": "2026-03-19T18:00:00+00:00",
        })
        results = await behavior.check(CID)
        assert "email Sarah" in results[0].suggested_message or "contract" in results[0].suggested_message


class TestIdleNudge:
    async def test_triggers_after_idle_period(self, store):
        behavior = IdleNudgeBehavior(
            store, clock=_clock(datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc))
        )
        # Last interaction was 8 days ago
        await store.update_last_interaction_time(CID)
        # Override with a time 8 days ago
        await store._r.set(
            f"proactive:{CID}:last_interaction",
            datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc).isoformat(),
        )
        # Has pending follow-ups
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(idle_days=7)
        result = await behavior.check(CID, cfg)
        assert result is not None
        assert result.trigger_type == "idle_nudge"

    async def test_does_not_trigger_before_idle_period(self, store):
        behavior = IdleNudgeBehavior(
            store, clock=_clock(datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc))
        )
        # Last interaction was 3 days ago
        await store._r.set(
            f"proactive:{CID}:last_interaction",
            datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc).isoformat(),
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(idle_days=7)
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_does_not_trigger_without_pending_items(self, store):
        behavior = IdleNudgeBehavior(
            store, clock=_clock(datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc))
        )
        await store._r.set(
            f"proactive:{CID}:last_interaction",
            datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc).isoformat(),
        )
        # No follow-ups
        cfg = BehaviorConfig(idle_days=7)
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_max_one_nudge_per_idle_period(self, store):
        behavior = IdleNudgeBehavior(
            store, clock=_clock(datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc))
        )
        await store._r.set(
            f"proactive:{CID}:last_interaction",
            datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc).isoformat(),
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(idle_days=7)

        # First check triggers
        result = await behavior.check(CID, cfg)
        assert result is not None

        # Second check doesn't (cooldown recorded)
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_no_interaction_ever_does_not_trigger(self, store):
        """If we've never tracked an interaction, don't nudge."""
        behavior = IdleNudgeBehavior(
            store, clock=_clock(datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc))
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(idle_days=7)
        result = await behavior.check(CID, cfg)
        assert result is None
