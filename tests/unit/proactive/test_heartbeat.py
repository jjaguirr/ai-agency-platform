"""Tests for HeartbeatDaemon — lifecycle, tick, concurrency."""
import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.proactive.heartbeat import HeartbeatDaemon, OutboundDispatcher
from src.proactive.state import ProactiveStateStore
from src.proactive.gate import NoiseGate, NoiseConfig, GateDecision
from src.proactive.settings_cache import CustomerSettingsCache
from src.proactive.triggers import Priority, ProactiveTrigger
from src.api.ea_registry import EARegistry


@pytest.fixture
def fake_redis():
    import fakeredis.aioredis
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
def mock_ea():
    ea = AsyncMock()
    ea.customer_id = "cust_1"
    ea.handle_customer_interaction = AsyncMock(return_value="reply")
    return ea


@pytest.fixture
def registry(mock_ea):
    factory = MagicMock(return_value=mock_ea)
    reg = EARegistry(factory=factory, max_size=10)
    # Pre-populate
    reg._instances["cust_1"] = mock_ea
    return reg


def _trigger(domain="ea", priority=Priority.MEDIUM):
    return ProactiveTrigger(
        domain=domain,
        trigger_type="test",
        priority=priority,
        title="Test",
        payload={},
        suggested_message="Test message",
        cooldown_key=None,
    )


class TestLifecycle:
    async def test_starts_and_stops_cleanly(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, tick_interval=0.05,
        )
        await daemon.start()
        assert daemon.is_running
        await daemon.stop()
        assert not daemon.is_running

    async def test_stop_is_idempotent(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, tick_interval=0.05,
        )
        await daemon.start()
        await daemon.stop()
        await daemon.stop()  # Should not raise
        assert not daemon.is_running

    async def test_clean_stop_within_1_second(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, tick_interval=60.0,
        )
        await daemon.start()
        import time
        t0 = time.monotonic()
        await daemon.stop()
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0


class TestTick:
    async def test_iterates_active_customers(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, tick_interval=0.05,
        )
        # Add follow-up so behaviors produce a trigger
        await store.add_follow_up("cust_1", {
            "id": "fu_1", "commitment": "call John",
            "deadline": "2026-03-19T12:00:00+00:00",
        })
        await daemon._tick()
        # Daemon ran — no crash

    async def test_empty_registry_is_noop(self, store, gate, mock_dispatcher):
        empty_reg = EARegistry(factory=MagicMock(), max_size=10)
        daemon = HeartbeatDaemon(
            empty_reg, store, gate, mock_dispatcher, tick_interval=0.05,
        )
        await daemon._tick()  # Should not crash
        mock_dispatcher.dispatch.assert_not_called()

    async def test_approved_triggers_dispatched(self, registry, store, gate, mock_dispatcher):
        clock = lambda: datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, clock=clock,
        )
        trigger = _trigger()
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[trigger])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once_with("cust_1", trigger)

    async def test_suppressed_triggers_not_dispatched(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, tick_interval=0.05,
        )
        # LOW priority trigger will be suppressed by default MEDIUM threshold
        trigger = _trigger(priority=Priority.LOW)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[trigger])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_not_called()


class TestConcurrency:
    async def test_slow_check_does_not_block_others(self, store, gate, mock_dispatcher):
        """A customer check that sleeps should be timed out without blocking."""
        slow_ea = AsyncMock()
        slow_ea.customer_id = "cust_slow"
        fast_ea = AsyncMock()
        fast_ea.customer_id = "cust_fast"

        reg = EARegistry(factory=MagicMock(), max_size=10)
        reg._instances["cust_slow"] = slow_ea
        reg._instances["cust_fast"] = fast_ea

        daemon = HeartbeatDaemon(
            reg, store, gate, mock_dispatcher,
            tick_interval=0.05, customer_timeout=0.1,
        )

        # Make slow customer's check sleep forever
        original_check = daemon._check_customer

        async def patched_check(cid):
            if cid == "cust_slow":
                await asyncio.sleep(10)  # Will be timed out
                return []
            return await original_check(cid)

        daemon._check_customer = patched_check

        import time
        t0 = time.monotonic()
        await daemon._tick()
        elapsed = time.monotonic() - t0
        # Should complete quickly — slow customer timed out, fast customer processed
        assert elapsed < 2.0

    async def test_customer_exception_does_not_crash_daemon(self, store, gate, mock_dispatcher):
        bad_ea = AsyncMock()
        bad_ea.customer_id = "cust_bad"

        reg = EARegistry(factory=MagicMock(), max_size=10)
        reg._instances["cust_bad"] = bad_ea

        daemon = HeartbeatDaemon(
            reg, store, gate, mock_dispatcher, tick_interval=0.05,
        )

        original_check = daemon._check_customer

        async def failing_check(cid):
            raise RuntimeError("boom")

        daemon._check_customer = failing_check
        # Should not raise
        await daemon._tick()


class TestConfig:
    def test_default_tick_interval(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(registry, store, gate, mock_dispatcher)
        assert daemon._tick_interval == 300.0

    def test_custom_tick_interval(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, tick_interval=60.0,
        )
        assert daemon._tick_interval == 60.0

    def test_default_customer_timeout(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(registry, store, gate, mock_dispatcher)
        assert daemon._customer_timeout == 30.0


def _noon_utc():
    return datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)


class TestSettingsCacheWiring:

    async def test_uses_customer_settings_for_noise_config(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        """When settings_cache is provided, heartbeat uses per-customer config."""
        import json
        await fake_redis.set("settings:cust_1", json.dumps({
            "working_hours": {"start": "09:00", "end": "18:00", "timezone": "UTC"},
            "proactive": {"priority_threshold": "HIGH", "daily_cap": 5, "idle_nudge_minutes": 120},
            "briefing": {"enabled": True, "time": "08:00"},
            "personality": {"tone": "professional", "language": "en", "name": "Assistant"},
            "connected_services": {"calendar": False, "n8n": False},
        }))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=120)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=_noon_utc,
        )
        trigger = _trigger(priority=Priority.MEDIUM)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[trigger])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_not_called()

    async def test_customer_settings_allows_matching_priority(
        self, registry, store, gate, mock_dispatcher, fake_redis,
    ):
        """HIGH trigger passes when customer threshold is HIGH."""
        import json
        await fake_redis.set("settings:cust_1", json.dumps({
            "working_hours": {"start": "09:00", "end": "18:00", "timezone": "UTC"},
            "proactive": {"priority_threshold": "HIGH", "daily_cap": 5, "idle_nudge_minutes": 120},
            "briefing": {"enabled": True, "time": "08:00"},
            "personality": {"tone": "professional", "language": "en", "name": "Assistant"},
            "connected_services": {"calendar": False, "n8n": False},
        }))
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=120)
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, settings_cache=cache, clock=_noon_utc,
        )
        trigger = _trigger(priority=Priority.HIGH)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[trigger])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once()
        args = mock_dispatcher.dispatch.call_args[0]
        assert args[0] == "cust_1"
        assert args[1].priority == Priority.HIGH

    async def test_falls_back_to_defaults_without_cache(
        self, registry, store, gate, mock_dispatcher,
    ):
        """Without settings_cache, behavior is identical to before (MEDIUM threshold)."""
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, clock=_noon_utc,
        )
        trigger = _trigger(priority=Priority.MEDIUM)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[trigger])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once()
        args = mock_dispatcher.dispatch.call_args[0]
        assert args[0] == "cust_1"
        assert args[1].priority == Priority.MEDIUM


class TestEARegistryActiveCustomers:
    def test_active_customer_ids_empty(self):
        reg = EARegistry(factory=MagicMock(), max_size=10)
        assert reg.active_customer_ids() == []

    def test_active_customer_ids_returns_cached(self):
        reg = EARegistry(factory=MagicMock(), max_size=10)
        ea1 = MagicMock()
        ea1.customer_id = "a"
        ea2 = MagicMock()
        ea2.customer_id = "b"
        reg._instances["a"] = ea1
        reg._instances["b"] = ea2
        ids = reg.active_customer_ids()
        assert set(ids) == {"a", "b"}

    def test_active_customer_ids_is_snapshot(self):
        """Mutating the returned list doesn't affect the registry."""
        reg = EARegistry(factory=MagicMock(), max_size=10)
        reg._instances["a"] = MagicMock()
        ids = reg.active_customer_ids()
        ids.append("fake")
        assert "fake" not in reg.active_customer_ids()
