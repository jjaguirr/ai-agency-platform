"""Tests for built-in proactive behaviors: morning briefing, follow-up tracker, idle nudge."""
import pytest
from datetime import datetime, timezone, timedelta

from src.proactive.behaviors import (
    MorningBriefingBehavior,
    FollowUpTrackerBehavior,
    IdleNudgeBehavior,
    DomainEventBehavior,
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
        assert result.priority == Priority.MEDIUM

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


_WEEK_MIN = 7 * 24 * 60


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
        cfg = BehaviorConfig(idle_nudge_minutes=_WEEK_MIN)
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
        cfg = BehaviorConfig(idle_nudge_minutes=_WEEK_MIN)
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
        cfg = BehaviorConfig(idle_nudge_minutes=_WEEK_MIN)
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
        cfg = BehaviorConfig(idle_nudge_minutes=_WEEK_MIN)

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
        cfg = BehaviorConfig(idle_nudge_minutes=_WEEK_MIN)
        result = await behavior.check(CID, cfg)
        assert result is None


# --- V2: briefing personalization ---------------------------------------------

BRIEFING_TIME = datetime(2026, 3, 19, 8, 5, tzinfo=timezone.utc)


class TestBriefingPersonalization:
    """Morning briefing respects per-customer tone, enabled flag, and
    gracefully degrades when optional data sources fail."""

    async def _briefing(self, store, cfg):
        behavior = MorningBriefingBehavior(store, clock=_clock(BRIEFING_TIME))
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        return await behavior.check(CID, cfg)

    async def test_disabled_briefing_returns_none(self, store):
        cfg = BehaviorConfig(briefing_hour=8, briefing_enabled=False)
        result = await self._briefing(store, cfg)
        assert result is None

    async def test_enabled_by_default(self, store):
        cfg = BehaviorConfig(briefing_hour=8)
        result = await self._briefing(store, cfg)
        assert result is not None

    async def test_professional_tone(self, store):
        cfg = BehaviorConfig(briefing_hour=8, tone="professional")
        result = await self._briefing(store, cfg)
        # Professional: no exclamation, formal register
        assert "!" not in result.suggested_message.split("\n")[0]
        assert "Good morning" in result.suggested_message

    async def test_friendly_tone(self, store):
        cfg = BehaviorConfig(briefing_hour=8, tone="friendly")
        result = await self._briefing(store, cfg)
        assert "!" in result.suggested_message

    async def test_concise_tone(self, store):
        cfg = BehaviorConfig(briefing_hour=8, tone="concise")
        result = await self._briefing(store, cfg)
        # Concise: no "Good morning" preamble
        first_line = result.suggested_message.split("\n")[0]
        assert "Good morning" not in first_line

    async def test_ea_name_in_signature(self, store):
        cfg = BehaviorConfig(briefing_hour=8, ea_name="Sarah")
        result = await self._briefing(store, cfg)
        assert "Sarah" in result.suggested_message

    async def test_default_ea_name_not_signed(self, store):
        """The placeholder 'Assistant' shouldn't appear — it's generic."""
        cfg = BehaviorConfig(briefing_hour=8, ea_name="Assistant")
        result = await self._briefing(store, cfg)
        assert "— Assistant" not in result.suggested_message

    async def test_language_carried_in_payload(self, store):
        """Language is passed downstream for actual translation — out of
        scope here, just verify it's propagated."""
        cfg = BehaviorConfig(briefing_hour=8, language="es")
        result = await self._briefing(store, cfg)
        assert result.payload.get("language") == "es"


class TestBriefingSources:
    """Briefing assembles content from pluggable sources. A failing
    source is skipped — don't fail the briefing because one specialist
    domain is unavailable."""

    async def test_extra_sources_included(self, store):
        async def events_source(cid: str) -> str:
            return "2 meetings today."

        behavior = MorningBriefingBehavior(
            store, clock=_clock(BRIEFING_TIME),
            extra_sources=[events_source],
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(briefing_hour=8)
        result = await behavior.check(CID, cfg)
        assert "2 meetings today" in result.suggested_message

    async def test_failing_source_skipped(self, store):
        async def boom(cid: str) -> str:
            raise RuntimeError("finance service down")

        behavior = MorningBriefingBehavior(
            store, clock=_clock(BRIEFING_TIME),
            extra_sources=[boom],
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(briefing_hour=8)
        result = await behavior.check(CID, cfg)
        # Briefing still fires with follow-ups
        assert result is not None
        assert "call John" in result.suggested_message

    async def test_source_returning_none_skipped(self, store):
        async def empty(cid: str) -> None:
            return None  # no data from this domain

        behavior = MorningBriefingBehavior(
            store, clock=_clock(BRIEFING_TIME),
            extra_sources=[empty],
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})
        cfg = BehaviorConfig(briefing_hour=8)
        result = await behavior.check(CID, cfg)
        assert result is not None

    async def test_all_sources_empty_returns_none(self, store):
        """No follow-ups, no source data → nothing to brief."""
        async def empty(cid: str) -> None:
            return None

        behavior = MorningBriefingBehavior(
            store, clock=_clock(BRIEFING_TIME),
            extra_sources=[empty],
        )
        # No follow-ups seeded
        cfg = BehaviorConfig(briefing_hour=8)
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_extra_source_without_follow_ups_still_briefs(self, store):
        """A source with data should trigger briefing even if follow-ups
        are empty — graceful partial content."""
        async def finance(cid: str) -> str:
            return "Budget: $12k remaining this month."

        behavior = MorningBriefingBehavior(
            store, clock=_clock(BRIEFING_TIME),
            extra_sources=[finance],
        )
        # No follow-ups
        cfg = BehaviorConfig(briefing_hour=8)
        result = await behavior.check(CID, cfg)
        assert result is not None
        assert "$12k" in result.suggested_message


# --- V2: idle nudge in minutes -----------------------------------------------

class TestIdleNudgeMinutes:
    """V2 aligns IdleNudgeBehavior with the dashboard settings schema,
    which uses idle_nudge_minutes (not days)."""

    async def test_triggers_after_configured_minutes(self, store):
        now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
        behavior = IdleNudgeBehavior(store, clock=_clock(now))
        # Last interaction 3 hours (180 min) ago
        await store._r.set(
            f"proactive:{CID}:last_interaction",
            datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc).isoformat(),
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "x"})
        cfg = BehaviorConfig(idle_nudge_minutes=120)
        result = await behavior.check(CID, cfg)
        assert result is not None

    async def test_does_not_trigger_before_configured_minutes(self, store):
        now = datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc)
        behavior = IdleNudgeBehavior(store, clock=_clock(now))
        # 90 minutes ago
        await store._r.set(
            f"proactive:{CID}:last_interaction",
            datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc).isoformat(),
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "x"})
        cfg = BehaviorConfig(idle_nudge_minutes=120)
        result = await behavior.check(CID, cfg)
        assert result is None

    async def test_zero_minutes_disables_nudge(self, store):
        now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
        behavior = IdleNudgeBehavior(store, clock=_clock(now))
        await store._r.set(
            f"proactive:{CID}:last_interaction",
            datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc).isoformat(),
        )
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "x"})
        cfg = BehaviorConfig(idle_nudge_minutes=0)
        result = await behavior.check(CID, cfg)
        assert result is None


# --- V2: Domain events → triggers --------------------------------------------

class TestDomainEventBehavior:
    """Converts staged domain events into ProactiveTrigger. Drain is
    destructive — each event fires once."""

    async def test_empty_queue_returns_empty_list(self, store):
        behavior = DomainEventBehavior(store)
        assert await behavior.check(CID) == []

    async def test_finance_anomaly_maps_to_high_priority(self, store):
        await store.add_domain_event(CID, {
            "type": "finance_anomaly",
            "amount": 500.0,
            "baseline": 100.0,
            "category": "operations",
        })
        behavior = DomainEventBehavior(store)
        triggers = await behavior.check(CID)
        assert len(triggers) == 1
        t = triggers[0]
        assert t.domain == "finance"
        assert t.trigger_type == "finance_anomaly"
        assert t.priority == Priority.HIGH
        assert "$500" in t.suggested_message or "500" in t.suggested_message
        assert t.payload["amount"] == 500.0
        assert t.cooldown_key is not None  # prevent re-fire on redelivery

    async def test_schedule_conflict_maps_to_high_priority(self, store):
        await store.add_domain_event(CID, {
            "type": "schedule_conflict",
            "new_event": {"title": "Board meeting", "start": "2026-03-20T10:00"},
            "conflicts_with": [{"title": "Standup", "start": "2026-03-20T10:00"}],
        })
        behavior = DomainEventBehavior(store)
        triggers = await behavior.check(CID)
        assert len(triggers) == 1
        t = triggers[0]
        assert t.domain == "scheduling"
        assert t.trigger_type == "schedule_conflict"
        assert t.priority == Priority.HIGH
        assert "Board meeting" in t.suggested_message
        assert "Standup" in t.suggested_message

    async def test_unknown_type_gets_medium_priority_fallback(self, store):
        await store.add_domain_event(CID, {
            "type": "never_seen_this",
            "detail": "something",
        })
        behavior = DomainEventBehavior(store)
        triggers = await behavior.check(CID)
        assert len(triggers) == 1
        assert triggers[0].priority == Priority.MEDIUM
        assert triggers[0].domain == "ea"

    async def test_multiple_events_all_converted(self, store):
        await store.add_domain_event(CID, {"type": "finance_anomaly", "amount": 1})
        await store.add_domain_event(CID, {"type": "schedule_conflict"})
        behavior = DomainEventBehavior(store)
        triggers = await behavior.check(CID)
        assert len(triggers) == 2

    async def test_drains_on_check(self, store):
        """Second check on same tick returns empty — events consumed."""
        await store.add_domain_event(CID, {"type": "finance_anomaly", "amount": 1})
        behavior = DomainEventBehavior(store)
        first = await behavior.check(CID)
        second = await behavior.check(CID)
        assert len(first) == 1
        assert second == []

    async def test_event_without_type_skipped(self, store):
        await store.add_domain_event(CID, {"not_a_type": "oops"})
        behavior = DomainEventBehavior(store)
        triggers = await behavior.check(CID)
        assert triggers == []
