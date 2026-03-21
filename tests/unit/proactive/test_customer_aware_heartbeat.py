"""Integration tests for customer-aware heartbeat — settings → noise gate + behaviors."""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis

from src.proactive.heartbeat import HeartbeatDaemon, OutboundDispatcher
from src.proactive.state import ProactiveStateStore
from src.proactive.gate import NoiseGate
from src.proactive.settings_cache import CustomerSettingsCache
from src.proactive.triggers import Priority, ProactiveTrigger
from src.api.ea_registry import EARegistry


def _settings(
    *,
    priority_threshold="MEDIUM",
    daily_cap=5,
    wh_start="09:00",
    wh_end="18:00",
    tz="UTC",
    briefing_time="08:00",
    briefing_enabled=True,
    idle_nudge_minutes=10080,
    tone="professional",
    name="Assistant",
):
    return json.dumps({
        "working_hours": {"start": wh_start, "end": wh_end, "timezone": tz},
        "proactive": {
            "priority_threshold": priority_threshold,
            "daily_cap": daily_cap,
            "idle_nudge_minutes": idle_nudge_minutes,
        },
        "briefing": {"enabled": briefing_enabled, "time": briefing_time},
        "personality": {"tone": tone, "language": "en", "name": name},
        "connected_services": {"calendar": False, "n8n": False},
    })


def _trigger(priority=Priority.MEDIUM, cooldown_key=None):
    return ProactiveTrigger(
        domain="ea", trigger_type="test", priority=priority,
        title="Test", payload={}, suggested_message="Test msg",
        cooldown_key=cooldown_key,
    )


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def gate(store):
    return NoiseGate(store)


@pytest.fixture
def mock_dispatcher():
    d = AsyncMock(spec=OutboundDispatcher)
    d.dispatch = AsyncMock()
    return d


@pytest.fixture
def registry():
    ea = AsyncMock()
    ea.customer_id = "cust_1"
    reg = EARegistry(factory=MagicMock(), max_size=10)
    reg._instances["cust_1"] = ea
    return reg


CID = "cust_1"


class TestPriorityThresholdRouting:
    async def test_customer_high_threshold_suppresses_medium(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        await fake_redis.set(f"settings:{CID}", _settings(priority_threshold="HIGH"))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_not_called()

    async def test_customer_low_threshold_allows_low(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        await fake_redis.set(f"settings:{CID}", _settings(priority_threshold="LOW"))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.LOW)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called()


class TestQuietHoursFromWorkingHours:
    async def test_quiet_hours_suppress_outside_working_hours(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        # Working hours 09:00-17:00 UTC → quiet 17:00-09:00
        await fake_redis.set(f"settings:{CID}", _settings(
            wh_start="09:00", wh_end="17:00", tz="UTC",
        ))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        # Clock at 18:00 UTC — in quiet hours
        clock = lambda: datetime(2026, 3, 19, 18, 0, tzinfo=timezone.utc)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=clock,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_not_called()

    async def test_working_hours_allow_during_work(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        await fake_redis.set(f"settings:{CID}", _settings(
            wh_start="09:00", wh_end="17:00", tz="UTC",
        ))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        clock = lambda: datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=clock,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called()


class TestDailyCapRouting:
    async def test_customer_cap_respected(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        await fake_redis.set(f"settings:{CID}", _settings(daily_cap=2))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache,
        )
        daemon._get_behaviors = lambda: []

        # Dispatch 2 triggers to hit the cap
        for _ in range(2):
            daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger()])
            await daemon._tick()

        # Third should be suppressed
        mock_dispatcher.dispatch.reset_mock()
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger()])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_not_called()


class TestBriefingConfigPassthrough:
    async def test_briefing_fires_at_customer_time(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        # Briefing at 09:00 US/Eastern, working hours 07:00-19:00
        # so quiet hours are 19:00-07:00 Eastern, briefing at 09:00 is within working hours
        await fake_redis.set(f"settings:{CID}", _settings(
            briefing_time="09:00", tz="US/Eastern",
            wh_start="07:00", wh_end="19:00",
            priority_threshold="LOW",
        ))
        # Add follow-up so briefing has data
        await store.add_follow_up(CID, {"id": "fu_1", "commitment": "call John"})

        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        # 13:05 UTC = 09:05 Eastern (EDT, UTC-4), past briefing hour, within working hours
        clock = lambda: datetime(2026, 3, 19, 13, 5, tzinfo=timezone.utc)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=clock,
        )
        # Don't override behaviors — let the real MorningBriefingBehavior run
        daemon._get_specialist_triggers = AsyncMock(return_value=[])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called()
        call_args = mock_dispatcher.dispatch.call_args
        trigger = call_args[0][1]
        assert trigger.trigger_type == "morning_briefing"


class TestQuietHoursBoundary:
    """Boundary tests: triggers at exact quiet hour start/end."""

    async def test_exactly_at_working_hours_end_is_quiet(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        """At exactly 17:00 UTC (working_hours end), quiet hours begin → suppressed."""
        await fake_redis.set(f"settings:{CID}", _settings(
            wh_start="09:00", wh_end="17:00", tz="UTC",
        ))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        clock = lambda: datetime(2026, 3, 19, 17, 0, tzinfo=timezone.utc)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=clock,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_not_called()

    async def test_exactly_at_working_hours_start_is_allowed(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        """At exactly 09:00 UTC (working_hours start), quiet hours end → allowed."""
        await fake_redis.set(f"settings:{CID}", _settings(
            wh_start="09:00", wh_end="17:00", tz="UTC",
        ))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        clock = lambda: datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=clock,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once()

    async def test_one_minute_before_working_hours_end_is_allowed(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        """At 16:59 UTC, still within working hours → allowed."""
        await fake_redis.set(f"settings:{CID}", _settings(
            wh_start="09:00", wh_end="17:00", tz="UTC",
        ))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        clock = lambda: datetime(2026, 3, 19, 16, 59, tzinfo=timezone.utc)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=clock,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once()


class TestDefaultsFallback:
    async def test_missing_settings_uses_defaults(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        # No settings key in Redis
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=300)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache,
        )
        # MEDIUM trigger should pass default MEDIUM threshold
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called()

    async def test_no_cache_at_all_uses_defaults(
        self, registry, store, gate, mock_dispatcher,
    ):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, tick_interval=0.05,
        )
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[_trigger(Priority.MEDIUM)])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called()
