"""Test that morning briefing records last_briefing_time after dispatch."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from src.proactive.behaviors import MorningBriefingBehavior, BehaviorConfig
from src.proactive.state import ProactiveStateStore
from src.proactive.heartbeat import HeartbeatDaemon
from src.proactive.gate import NoiseGate, NoiseConfig
from src.api.ea_registry import EARegistry
from unittest.mock import MagicMock


@pytest.fixture
def fake_redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


CID = "cust_briefing_test"


class TestBriefingTimeRecordedAfterDispatch:
    async def test_briefing_time_set_after_dispatch(self, store):
        """After a morning briefing trigger is dispatched, last_briefing_time is updated."""
        gate = NoiseGate(store)
        dispatcher = AsyncMock()
        dispatcher.dispatch = AsyncMock()

        mock_ea = AsyncMock()
        mock_ea.customer_id = CID
        reg = EARegistry(factory=MagicMock(), max_size=10)
        reg._instances[CID] = mock_ea

        now = datetime(2026, 3, 19, 8, 5, tzinfo=timezone.utc)

        daemon = HeartbeatDaemon(
            reg, store, gate, dispatcher,
            tick_interval=60.0,
            clock=lambda: now,
        )

        # Seed data so morning briefing has something to report
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})

        # Before tick, no briefing time recorded
        assert await store.get_last_briefing_time(CID) is None

        await daemon._tick()

        # Dispatcher should have been called (briefing trigger)
        assert dispatcher.dispatch.call_count >= 1

        # After dispatch, briefing time should be recorded
        last = await store.get_last_briefing_time(CID)
        assert last is not None
        assert last.date() == now.date()

    async def test_second_tick_same_day_no_duplicate_briefing(self, store):
        """Once briefing is dispatched and time recorded, second tick doesn't re-send."""
        gate = NoiseGate(store)
        dispatcher = AsyncMock()
        dispatcher.dispatch = AsyncMock()

        mock_ea = AsyncMock()
        mock_ea.customer_id = CID
        reg = EARegistry(factory=MagicMock(), max_size=10)
        reg._instances[CID] = mock_ea

        now = datetime(2026, 3, 19, 8, 5, tzinfo=timezone.utc)

        daemon = HeartbeatDaemon(
            reg, store, gate, dispatcher,
            tick_interval=60.0,
            clock=lambda: now,
        )

        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})

        await daemon._tick()
        first_count = dispatcher.dispatch.call_count

        await daemon._tick()
        # Briefing should not fire again — same day
        # The only new dispatches would be follow-up tracker, not briefing
        briefing_calls = [
            c for c in dispatcher.dispatch.call_args_list
            if c[0][1].trigger_type == "morning_briefing"
        ]
        assert len(briefing_calls) == 1  # Only once
