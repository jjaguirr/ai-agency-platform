"""
Built-in proactive behaviors — morning briefing and idle nudge.

These live in the EA itself (not specialists) because they're cross-domain:
briefing pulls from scheduling + finance + followups; nudge depends on
last-interaction which no specialist owns.

Both are implemented as `check_*` functions that return Optional[ProactiveTrigger].
The heartbeat daemon calls them per tick per customer. Idempotency (briefing
once per day, nudge once per idle period) is enforced here, not in the gate —
the gate's cooldown is a safety net, not the primary mechanism.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.agents.proactive.triggers import Priority


pytestmark = pytest.mark.asyncio


def _ctx(timezone="UTC", briefing_hour=8):
    from src.agents.executive_assistant import BusinessContext
    ctx = BusinessContext(business_name="Acme", timezone=timezone)
    return ctx


class TestMorningBriefing:
    async def test_fires_at_briefing_hour(self, state_store, clock):
        from src.agents.proactive.behaviors import check_morning_briefing
        # 08:05 local (UTC) — just past briefing hour
        clock.set(datetime(2026, 3, 18, 8, 5, tzinfo=ZoneInfo("UTC")))

        # Pretend there's something to brief about (pending followup)
        from src.agents.proactive.followups import Commitment
        await state_store.add_followup("cust", Commitment(
            text="call John",
            due=datetime(2026, 3, 18, 15, 0, tzinfo=ZoneInfo("UTC")),
            raw="r",
        ))

        t = await check_morning_briefing(
            "cust", _ctx(briefing_hour=8), state_store,
            briefing_hour=8, clock=clock,
        )
        assert t is not None
        assert t.trigger_type == "briefing"
        assert t.priority == Priority.MEDIUM

    async def test_does_not_fire_before_hour(self, state_store, clock):
        from src.agents.proactive.behaviors import check_morning_briefing
        clock.set(datetime(2026, 3, 18, 7, 59, tzinfo=ZoneInfo("UTC")))
        t = await check_morning_briefing(
            "cust", _ctx(), state_store, briefing_hour=8, clock=clock,
        )
        assert t is None

    async def test_fires_once_per_day(self, state_store, clock):
        from src.agents.proactive.behaviors import check_morning_briefing
        from src.agents.proactive.followups import Commitment
        await state_store.add_followup("cust", Commitment(
            text="x", due=datetime(2026, 3, 18, tzinfo=ZoneInfo("UTC")), raw="r"))

        clock.set(datetime(2026, 3, 18, 8, 5, tzinfo=ZoneInfo("UTC")))
        t1 = await check_morning_briefing("cust", _ctx(), state_store, briefing_hour=8, clock=clock)
        assert t1 is not None
        await state_store.set_last_briefing("cust", clock())

        # Same day, later tick — no second briefing
        clock.set(datetime(2026, 3, 18, 14, 0, tzinfo=ZoneInfo("UTC")))
        t2 = await check_morning_briefing("cust", _ctx(), state_store, briefing_hour=8, clock=clock)
        assert t2 is None

        # Next day — fires again
        clock.set(datetime(2026, 3, 19, 8, 1, tzinfo=ZoneInfo("UTC")))
        t3 = await check_morning_briefing("cust", _ctx(), state_store, briefing_hour=8, clock=clock)
        assert t3 is not None

    async def test_skips_if_no_content(self, state_store, clock):
        """
        Empty briefing (no events, no followups) → None. Don't message
        "Good morning, you have nothing today."
        """
        from src.agents.proactive.behaviors import check_morning_briefing
        clock.set(datetime(2026, 3, 18, 8, 5, tzinfo=ZoneInfo("UTC")))
        t = await check_morning_briefing("cust", _ctx(), state_store, briefing_hour=8, clock=clock)
        assert t is None

    async def test_respects_customer_timezone(self, state_store, clock):
        """
        08:00 America/New_York on 2026-03-18 is 12:00 UTC (DST).
        Clock at 12:05 UTC + TZ=NY + briefing_hour=8 → fires.
        """
        from src.agents.proactive.behaviors import check_morning_briefing
        from src.agents.proactive.followups import Commitment
        await state_store.add_followup("cust", Commitment(
            text="x", due=datetime(2026, 3, 18, tzinfo=ZoneInfo("UTC")), raw="r"))

        clock.set(datetime(2026, 3, 18, 12, 5, tzinfo=ZoneInfo("UTC")))
        t = await check_morning_briefing(
            "cust", _ctx(timezone="America/New_York"),
            state_store, briefing_hour=8, clock=clock,
        )
        assert t is not None

        # 11:00 UTC = 07:00 EDT → too early
        clock.set(datetime(2026, 3, 18, 11, 0, tzinfo=ZoneInfo("UTC")))
        await state_store.set_last_briefing("cust", None)  # reset
        t2 = await check_morning_briefing(
            "cust", _ctx(timezone="America/New_York"),
            state_store, briefing_hour=8, clock=clock,
        )
        assert t2 is None


class TestIdleNudge:
    async def test_nudge_after_idle_period(self, state_store, clock):
        from src.agents.proactive.behaviors import check_idle_nudge
        from src.agents.proactive.followups import Commitment

        # Last interaction 8 days ago
        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))
        await state_store.set_last_interaction("cust", clock() - timedelta(days=8))

        # Pending item exists → nudge
        await state_store.add_followup("cust", Commitment(
            text="x", due=clock() + timedelta(days=1), raw="r"))

        t = await check_idle_nudge("cust", _ctx(), state_store,
                                   idle_days=7, clock=clock)
        assert t is not None
        assert t.trigger_type == "suggestion"
        assert t.priority == Priority.LOW

    async def test_no_nudge_before_idle_period(self, state_store, clock):
        from src.agents.proactive.behaviors import check_idle_nudge
        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))
        await state_store.set_last_interaction("cust", clock() - timedelta(days=3))
        t = await check_idle_nudge("cust", _ctx(), state_store,
                                   idle_days=7, clock=clock)
        assert t is None

    async def test_nudge_once_per_idle_period(self, state_store, clock):
        from src.agents.proactive.behaviors import check_idle_nudge
        from src.agents.proactive.followups import Commitment
        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))
        await state_store.set_last_interaction("cust", clock() - timedelta(days=8))
        await state_store.add_followup("cust", Commitment(
            text="x", due=clock(), raw="r"))

        t1 = await check_idle_nudge("cust", _ctx(), state_store, idle_days=7, clock=clock)
        assert t1 is not None
        await state_store.set_last_nudge("cust", clock())

        # Still idle, but already nudged since last interaction → no second nudge
        clock.advance(timedelta(days=1))
        t2 = await check_idle_nudge("cust", _ctx(), state_store, idle_days=7, clock=clock)
        assert t2 is None

    async def test_no_nudge_if_no_pending_items(self, state_store, clock):
        """Idle but nothing pending → don't nag."""
        from src.agents.proactive.behaviors import check_idle_nudge
        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))
        await state_store.set_last_interaction("cust", clock() - timedelta(days=8))
        t = await check_idle_nudge("cust", _ctx(), state_store, idle_days=7, clock=clock)
        assert t is None

    async def test_no_nudge_if_never_interacted(self, state_store, clock):
        """
        No last_interaction recorded → customer hasn't onboarded yet.
        Don't nudge.
        """
        from src.agents.proactive.behaviors import check_idle_nudge
        t = await check_idle_nudge("cust", _ctx(), state_store, idle_days=7, clock=clock)
        assert t is None
