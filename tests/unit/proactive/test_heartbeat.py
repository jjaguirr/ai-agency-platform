"""Tests for HeartbeatDaemon — lifecycle, tick, concurrency."""
import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.proactive.heartbeat import HeartbeatDaemon, OutboundDispatcher
from src.proactive.state import ProactiveStateStore
from src.proactive.gate import NoiseGate, NoiseConfig, GateDecision
from src.proactive.triggers import Priority, ProactiveTrigger
from src.api.ea_registry import EARegistry
from tests.unit.proactive.conftest import REFERENCE_TIME


# Fixed clock at 10:00 UTC — outside default quiet hours. Without this,
# any daemon tick test flakes when run between 22:00–07:00 UTC.
CLOCK = lambda: REFERENCE_TIME  # noqa: E731


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
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, clock=CLOCK,
        )
        # Spy on _check_customer to prove every active customer is visited.
        checked: list[str] = []
        original = daemon._check_customer

        async def spy(cid, cfg=None):
            checked.append(cid)
            return await original(cid, cfg)

        daemon._check_customer = spy
        await daemon._tick()

        assert checked == ["cust_1"]

    async def test_empty_registry_is_noop(self, store, gate, mock_dispatcher):
        empty_reg = EARegistry(factory=MagicMock(), max_size=10)
        daemon = HeartbeatDaemon(
            empty_reg, store, gate, mock_dispatcher, tick_interval=0.05,
        )
        await daemon._tick()  # Should not crash
        mock_dispatcher.dispatch.assert_not_called()

    async def test_approved_triggers_dispatched(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, clock=CLOCK,
        )
        # Inject a behavior that returns a trigger
        trigger = _trigger()
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[trigger])
        # Gate allows by default (MEDIUM >= MEDIUM threshold)
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called()

    async def test_suppressed_triggers_not_dispatched(self, registry, store, gate, mock_dispatcher):
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            tick_interval=0.05, clock=CLOCK,
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


# --- Per-customer settings (V2) ---------------------------------------------

import json
from src.proactive.settings_loader import CustomerSettingsLoader


async def _seed_settings(redis, cid: str, settings: dict) -> None:
    await redis.set(f"settings:{cid}", json.dumps(settings))


@pytest.fixture
def loader(fake_redis):
    return CustomerSettingsLoader(fake_redis, ttl_seconds=1)


class TestPerCustomerConfig:
    """Heartbeat reads per-customer NoiseConfig from the settings loader,
    replacing the hardcoded NoiseConfig() at the gate-evaluation site."""

    async def test_high_threshold_customer_suppresses_medium_trigger(
        self, fake_redis, registry, store, gate, mock_dispatcher, loader,
    ):
        # cust_1's settings set threshold to HIGH
        await _seed_settings(fake_redis, "cust_1", {
            "proactive": {"priority_threshold": "HIGH"},
        })
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            settings_loader=loader, clock=CLOCK,
        )
        # MEDIUM trigger — would pass the old hardcoded MEDIUM threshold,
        # but should be suppressed by this customer's HIGH threshold.
        medium = _trigger(priority=Priority.MEDIUM)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[medium])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_not_called()

    async def test_low_threshold_customer_allows_low_trigger(
        self, fake_redis, registry, store, gate, mock_dispatcher, loader,
    ):
        await _seed_settings(fake_redis, "cust_1", {
            "proactive": {"priority_threshold": "LOW"},
        })
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            settings_loader=loader, clock=CLOCK,
        )
        low = _trigger(priority=Priority.LOW)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[low])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once()

    async def test_missing_settings_falls_back_to_defaults(
        self, fake_redis, registry, store, gate, mock_dispatcher, loader,
    ):
        # No settings seeded — loader returns Settings() defaults.
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            settings_loader=loader, clock=CLOCK,
        )
        # MEDIUM passes default MEDIUM threshold
        medium = _trigger(priority=Priority.MEDIUM)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[medium])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once()

    async def test_no_loader_injected_uses_hardcoded_defaults(
        self, registry, store, gate, mock_dispatcher,
    ):
        """Backward compat — daemon without a loader still works."""
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher, clock=CLOCK,
        )
        medium = _trigger(priority=Priority.MEDIUM)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[medium])
        await daemon._tick()
        mock_dispatcher.dispatch.assert_called_once()

    async def test_different_customers_get_different_configs(
        self, fake_redis, store, gate, mock_dispatcher, loader,
    ):
        # Two customers, different thresholds
        await _seed_settings(fake_redis, "cust_strict", {
            "proactive": {"priority_threshold": "HIGH"},
        })
        await _seed_settings(fake_redis, "cust_relaxed", {
            "proactive": {"priority_threshold": "LOW"},
        })

        reg = EARegistry(factory=MagicMock(), max_size=10)
        reg._instances["cust_strict"] = MagicMock()
        reg._instances["cust_relaxed"] = MagicMock()

        daemon = HeartbeatDaemon(
            reg, store, gate, mock_dispatcher,
            settings_loader=loader, clock=CLOCK,
        )
        # Both customers produce a LOW trigger
        low = _trigger(priority=Priority.LOW)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[low])
        await daemon._tick()

        # Only cust_relaxed's trigger dispatched (strict's LOW < HIGH)
        dispatched_to = [
            call.args[0] for call in mock_dispatcher.dispatch.call_args_list
        ]
        assert "cust_relaxed" in dispatched_to
        assert "cust_strict" not in dispatched_to

    async def test_daily_cap_from_settings(
        self, fake_redis, registry, store, gate, mock_dispatcher, loader,
    ):
        await _seed_settings(fake_redis, "cust_1", {
            "proactive": {"daily_cap": 1, "priority_threshold": "LOW"},
        })
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            settings_loader=loader, clock=CLOCK,
        )
        # Two triggers — cap of 1 means only first gets through
        t1 = _trigger(priority=Priority.MEDIUM)
        t2 = _trigger(priority=Priority.MEDIUM)
        daemon._get_behaviors = lambda: []
        daemon._get_specialist_triggers = AsyncMock(return_value=[t1, t2])
        await daemon._tick()
        assert mock_dispatcher.dispatch.call_count == 1

    async def test_behavior_config_passed_to_behaviors(
        self, fake_redis, registry, store, gate, mock_dispatcher, loader,
    ):
        """Behaviors invoked with config signature receive the per-customer
        BehaviorConfig, not a default one."""
        await _seed_settings(fake_redis, "cust_1", {
            "briefing": {"enabled": False, "time": "06:00"},
        })
        daemon = HeartbeatDaemon(
            registry, store, gate, mock_dispatcher,
            settings_loader=loader, clock=CLOCK,
        )

        captured = []

        class SpyBehavior:
            async def check(self, cid, config):
                captured.append(config)
                return None

        daemon._get_behaviors = lambda: [SpyBehavior()]
        daemon._get_specialist_triggers = AsyncMock(return_value=[])
        await daemon._tick()

        assert len(captured) == 1
        assert captured[0].briefing_enabled is False
        assert captured[0].briefing_hour == 6
