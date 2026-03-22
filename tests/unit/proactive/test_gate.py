"""Tests for NoiseGate — cooldown, priority threshold, quiet hours, daily cap."""
import pytest
from datetime import datetime, timezone

from src.proactive.triggers import Priority, ProactiveTrigger
from src.proactive.state import ProactiveStateStore
from src.proactive.gate import NoiseGate, NoiseConfig, GateDecision
from tests.unit.proactive.conftest import REFERENCE_TIME


# Pinned to 10:00 UTC — outside the default 22:00–07:00 quiet window.
# Without this, tests that don't care about quiet hours flake whenever
# the suite runs during UTC night.
NOW = REFERENCE_TIME


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def gate(store):
    return NoiseGate(store)


@pytest.fixture
def config():
    return NoiseConfig()


CID = "cust_gate_test"


def _trigger(
    priority=Priority.MEDIUM,
    cooldown_key="test:trigger",
    domain="ea",
    trigger_type="test",
) -> ProactiveTrigger:
    return ProactiveTrigger(
        domain=domain,
        trigger_type=trigger_type,
        priority=priority,
        title="Test trigger",
        payload={},
        suggested_message="Test message",
        cooldown_key=cooldown_key,
    )


class TestCooldown:
    async def test_allows_first_trigger(self, gate, config):
        decision = await gate.evaluate(CID, _trigger(), config, now=NOW)
        assert decision.allowed

    async def test_suppresses_duplicate_within_window(self, gate, store, config):
        await store.record_cooldown(CID, "test:trigger", window_seconds=3600)
        decision = await gate.evaluate(CID, _trigger(), config, now=NOW)
        assert not decision.allowed
        assert "cooldown" in decision.reason

    async def test_different_keys_independent(self, gate, store, config):
        await store.record_cooldown(CID, "other:key", window_seconds=3600)
        decision = await gate.evaluate(
            CID, _trigger(cooldown_key="test:trigger"), config, now=NOW,
        )
        assert decision.allowed

    async def test_no_cooldown_key_skips_check(self, gate, config):
        trigger = _trigger(cooldown_key=None)
        trigger.cooldown_key = None
        decision = await gate.evaluate(CID, trigger, config, now=NOW)
        assert decision.allowed


class TestPriorityThreshold:
    async def test_low_suppressed_at_medium_threshold(self, gate, config):
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.LOW), config, now=NOW,
        )
        assert not decision.allowed
        assert "threshold" in decision.reason

    async def test_medium_allowed_at_medium_threshold(self, gate, config):
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.MEDIUM), config, now=NOW,
        )
        assert decision.allowed

    async def test_high_allowed(self, gate, config):
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.HIGH), config, now=NOW,
        )
        assert decision.allowed

    async def test_urgent_always_allowed(self, gate, config):
        cfg = NoiseConfig(priority_threshold=Priority.URGENT)
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.URGENT), cfg, now=NOW,
        )
        assert decision.allowed

    async def test_custom_threshold(self, gate):
        cfg = NoiseConfig(priority_threshold=Priority.HIGH)
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.MEDIUM), cfg, now=NOW,
        )
        assert not decision.allowed
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.HIGH), cfg, now=NOW,
        )
        assert decision.allowed


class TestQuietHours:
    async def test_suppressed_during_quiet_hours(self, gate):
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="UTC")
        trigger = _trigger(priority=Priority.MEDIUM, cooldown_key=None)
        # 23:00 UTC is within quiet hours
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 23, 0, tzinfo=timezone.utc),
        )
        assert not decision.allowed
        assert "quiet_hours" in decision.reason

    async def test_suppressed_early_morning(self, gate):
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="UTC")
        trigger = _trigger(priority=Priority.MEDIUM, cooldown_key=None)
        # 5:00 UTC is within quiet hours
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 5, 0, tzinfo=timezone.utc),
        )
        assert not decision.allowed

    async def test_allowed_outside_quiet_hours(self, gate):
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="UTC")
        trigger = _trigger(priority=Priority.MEDIUM, cooldown_key=None)
        # 10:00 UTC is outside quiet hours
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc),
        )
        assert decision.allowed

    async def test_urgent_overrides_quiet_hours(self, gate):
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="UTC")
        trigger = _trigger(priority=Priority.URGENT, cooldown_key=None)
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 23, 0, tzinfo=timezone.utc),
        )
        assert decision.allowed

    async def test_respects_customer_timezone(self, gate):
        # 10:00 UTC = 06:00 America/New_York (during EDT, UTC-4)
        # 06:00 is within quiet hours 22:00-07:00
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="America/New_York")
        trigger = _trigger(priority=Priority.MEDIUM, cooldown_key=None)
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc),
        )
        assert not decision.allowed

    async def test_custom_quiet_hours(self, gate):
        cfg = NoiseConfig(quiet_start=20, quiet_end=9, timezone="UTC")
        trigger = _trigger(priority=Priority.MEDIUM, cooldown_key=None)
        # 21:00 is within 20:00-09:00
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 21, 0, tzinfo=timezone.utc),
        )
        assert not decision.allowed


class TestDailyCap:
    # Seed counts on the same date the gate will read — NOW.date() under
    # the default UTC config. Without this the seed and check could land
    # in different buckets if the wall clock rolls past midnight mid-test.

    async def test_allowed_under_cap(self, gate, config):
        decision = await gate.evaluate(
            CID, _trigger(cooldown_key=None), config, now=NOW,
        )
        assert decision.allowed

    async def test_suppressed_at_cap(self, gate, store, config):
        for _ in range(config.daily_cap):
            await store.increment_daily_count(CID, on_date=NOW.date())
        decision = await gate.evaluate(
            CID, _trigger(cooldown_key=None), config, now=NOW,
        )
        assert not decision.allowed
        assert "daily_cap" in decision.reason

    async def test_urgent_exempt_from_cap(self, gate, store, config):
        for _ in range(config.daily_cap):
            await store.increment_daily_count(CID, on_date=NOW.date())
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.URGENT, cooldown_key=None),
            config, now=NOW,
        )
        assert decision.allowed

    async def test_custom_cap(self, gate, store):
        cfg = NoiseConfig(daily_cap=2)
        await store.increment_daily_count(CID, on_date=NOW.date())
        await store.increment_daily_count(CID, on_date=NOW.date())
        decision = await gate.evaluate(
            CID, _trigger(cooldown_key=None), cfg, now=NOW,
        )
        assert not decision.allowed

    async def test_cap_keyed_by_customer_local_date(self, gate, store):
        """2026-03-19 23:00 UTC is already 2026-03-20 in Auckland (UTC+13).
        The cap bucket must follow the customer's local calendar."""
        cfg = NoiseConfig(daily_cap=1, timezone="Pacific/Auckland")
        utc_23 = datetime(2026, 3, 19, 23, 0, tzinfo=timezone.utc)
        from datetime import date
        await store.increment_daily_count(CID, on_date=date(2026, 3, 20))
        decision = await gate.evaluate(
            CID,
            _trigger(priority=Priority.URGENT, cooldown_key=None),  # bypass quiet hours
            cfg, now=utc_23,
        )
        # URGENT bypasses cap — but we want to verify the read path, so
        # drop to HIGH and confirm it hits the Auckland-dated bucket.
        decision = await gate.evaluate(
            CID,
            _trigger(priority=Priority.HIGH, cooldown_key=None),
            NoiseConfig(daily_cap=1, timezone="Pacific/Auckland",
                        quiet_start=0, quiet_end=0),  # no quiet hours
            now=utc_23,
        )
        assert not decision.allowed
        assert "daily_cap" in decision.reason


class TestCombined:
    async def test_all_pass_delivers(self, gate, config):
        decision = await gate.evaluate(
            CID, _trigger(cooldown_key=None), config,
            now=datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc),
        )
        assert decision.allowed
        assert decision.reason == "delivered"

    async def test_first_failing_check_suppresses(self, gate, store, config):
        # Both cooldown active AND low priority — cooldown should be the reason
        # since it's checked first
        await store.record_cooldown(CID, "test:trigger", window_seconds=3600)
        decision = await gate.evaluate(
            CID, _trigger(priority=Priority.LOW), config, now=NOW,
        )
        assert not decision.allowed
        assert "cooldown" in decision.reason

    async def test_invalid_timezone_falls_back_to_utc(self, gate):
        """Bad timezone should not crash the gate — fall back to UTC."""
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="Fake/Zone")
        trigger = _trigger(priority=Priority.MEDIUM, cooldown_key=None)
        # 10:00 UTC is outside quiet hours in any reasonable interpretation
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc),
        )
        assert decision.allowed

    async def test_invalid_timezone_quiet_hours_still_work(self, gate):
        """Even with fallback, quiet hours logic applies using UTC."""
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="Not/Real")
        trigger = _trigger(priority=Priority.MEDIUM, cooldown_key=None)
        # 23:00 UTC — within quiet hours under UTC fallback
        decision = await gate.evaluate(
            CID, trigger, cfg,
            now=datetime(2026, 3, 19, 23, 0, tzinfo=timezone.utc),
        )
        assert not decision.allowed
        assert "quiet_hours" in decision.reason

    async def test_urgent_bypasses_quiet_and_cap_but_not_cooldown(self, gate, store):
        cfg = NoiseConfig(quiet_start=22, quiet_end=7, timezone="UTC")
        # Cooldown active
        await store.record_cooldown(CID, "test:trigger", window_seconds=3600)
        # Cap exceeded — seed on UTC date of the pinned now (23:00 UTC → 2026-03-19)
        for _ in range(cfg.daily_cap):
            await store.increment_daily_count(
                CID, on_date=datetime(2026, 3, 19, tzinfo=timezone.utc).date(),
            )
        # During quiet hours, with URGENT — cooldown still blocks
        decision = await gate.evaluate(
            CID,
            _trigger(priority=Priority.URGENT, cooldown_key="test:trigger"),
            cfg,
            now=datetime(2026, 3, 19, 23, 0, tzinfo=timezone.utc),
        )
        assert not decision.allowed
        assert "cooldown" in decision.reason
