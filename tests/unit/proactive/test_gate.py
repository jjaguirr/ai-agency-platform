"""
NoiseGate — the thing that stops the proactive system from spamming.

Four filters, applied in order:
  1. Cooldown       — same cooldown_key within window → SUPPRESS
  2. Priority floor — below customer's min_priority → SUPPRESS (URGENT immune)
  3. Quiet hours    — local time in [quiet_start, quiet_end) → SUPPRESS (URGENT immune)
  4. Daily cap      — already sent N today → SUPPRESS (URGENT immune, doesn't count)

The gate is a pure-ish function of (trigger, customer prefs, proactive state).
It returns a decision + reason; the caller applies the decision. Keeping it
side-effect-free makes it testable without a real Redis.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.agents.proactive.triggers import Priority, ProactiveTrigger
from src.agents.proactive.gate import GateDecision, NoiseGate, ProactivePrefs


def _trigger(priority=Priority.MEDIUM, cooldown_key=None):
    return ProactiveTrigger(
        domain="test", trigger_type="test", priority=priority,
        title="t", payload={}, suggested_message="m",
        cooldown_key=cooldown_key,
    )


@pytest.fixture
def default_prefs():
    return ProactivePrefs(
        timezone="UTC",
        min_priority=Priority.MEDIUM,
        quiet_start_hour=22,
        quiet_end_hour=7,
        daily_cap=5,
        cooldown_hours=24,
    )


class TestCooldown:
    @pytest.mark.asyncio
    async def test_same_key_within_window_suppressed(self, state_store, default_prefs, clock):
        gate = NoiseGate(state_store, clock=clock)
        t = _trigger(cooldown_key="spend_high")

        # First fires
        d1 = await gate.evaluate("cust", t, default_prefs)
        assert d1.allow
        await gate.record_sent("cust", t, default_prefs)

        # Second within 24h suppressed
        clock.advance(timedelta(hours=12))
        d2 = await gate.evaluate("cust", t, default_prefs)
        assert not d2.allow
        assert "cooldown" in d2.reason

    @pytest.mark.asyncio
    async def test_same_key_after_window_allowed(self, state_store, default_prefs, clock):
        gate = NoiseGate(state_store, clock=clock)
        t = _trigger(cooldown_key="spend_high")

        await gate.evaluate("cust", t, default_prefs)
        await gate.record_sent("cust", t, default_prefs)

        clock.advance(timedelta(hours=25))
        d = await gate.evaluate("cust", t, default_prefs)
        assert d.allow

    @pytest.mark.asyncio
    async def test_no_cooldown_key_never_suppressed_by_cooldown(self, state_store, default_prefs, clock):
        gate = NoiseGate(state_store, clock=clock)
        t = _trigger(cooldown_key=None)

        for _ in range(3):
            d = await gate.evaluate("cust", t, default_prefs)
            # cooldown doesn't apply — but daily cap might, so only check reason
            if not d.allow:
                assert "cooldown" not in d.reason
            await gate.record_sent("cust", t, default_prefs)

    @pytest.mark.asyncio
    async def test_cooldown_is_per_customer(self, state_store, default_prefs, clock):
        gate = NoiseGate(state_store, clock=clock)
        t = _trigger(cooldown_key="spend_high")

        d_a = await gate.evaluate("cust_a", t, default_prefs)
        assert d_a.allow
        await gate.record_sent("cust_a", t, default_prefs)

        # cust_b unaffected by cust_a's cooldown
        d_b = await gate.evaluate("cust_b", t, default_prefs)
        assert d_b.allow


class TestPriorityFloor:
    @pytest.mark.asyncio
    async def test_low_priority_suppressed_at_default_floor(self, state_store, default_prefs, clock):
        gate = NoiseGate(state_store, clock=clock)
        t = _trigger(priority=Priority.LOW)
        d = await gate.evaluate("cust", t, default_prefs)
        assert not d.allow
        assert "priority" in d.reason

    @pytest.mark.asyncio
    async def test_at_floor_allowed(self, state_store, default_prefs, clock):
        gate = NoiseGate(state_store, clock=clock)
        t = _trigger(priority=Priority.MEDIUM)
        d = await gate.evaluate("cust", t, default_prefs)
        assert d.allow

    @pytest.mark.asyncio
    async def test_urgent_ignores_floor(self, state_store, clock):
        # Even a floor of URGENT can't suppress URGENT — they're equal, >= passes.
        # But a hypothetical misconfiguration floor above URGENT shouldn't exist.
        # Test the practical case: floor=HIGH, trigger=URGENT passes.
        prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.HIGH,
                               quiet_start_hour=22, quiet_end_hour=7,
                               daily_cap=5, cooldown_hours=24)
        gate = NoiseGate(state_store, clock=clock)
        t = _trigger(priority=Priority.URGENT)
        d = await gate.evaluate("cust", t, prefs)
        assert d.allow


class TestQuietHours:
    @pytest.mark.asyncio
    async def test_inside_quiet_hours_suppressed(self, state_store, default_prefs, clock):
        # Quiet: 22:00–07:00 UTC. Move clock to 23:00 UTC.
        clock.set(datetime(2026, 3, 18, 23, 0, tzinfo=ZoneInfo("UTC")))
        gate = NoiseGate(state_store, clock=clock)
        d = await gate.evaluate("cust", _trigger(), default_prefs)
        assert not d.allow
        assert "quiet" in d.reason

    @pytest.mark.asyncio
    async def test_after_quiet_hours_allowed(self, state_store, default_prefs, clock):
        clock.set(datetime(2026, 3, 18, 8, 0, tzinfo=ZoneInfo("UTC")))
        gate = NoiseGate(state_store, clock=clock)
        d = await gate.evaluate("cust", _trigger(), default_prefs)
        assert d.allow

    @pytest.mark.asyncio
    async def test_quiet_hours_start_is_inclusive(self, state_store, default_prefs, clock):
        """22:00 sharp is inside [22, 07) — start bound is inclusive.
        Pins the `h >= start` semantics in the wrap-midnight branch."""
        clock.set(datetime(2026, 3, 18, 22, 0, tzinfo=ZoneInfo("UTC")))
        gate = NoiseGate(state_store, clock=clock)
        assert not (await gate.evaluate("cust", _trigger(), default_prefs)).allow

    @pytest.mark.asyncio
    async def test_quiet_hours_end_is_exclusive(self, state_store, default_prefs, clock):
        """07:00 sharp is outside [22, 07) — end bound is exclusive.
        06:59 is still quiet, 07:00 is not. Pins `h < end`."""
        gate = NoiseGate(state_store, clock=clock)
        clock.set(datetime(2026, 3, 18, 6, 59, tzinfo=ZoneInfo("UTC")))
        assert not (await gate.evaluate("cust", _trigger(), default_prefs)).allow
        clock.set(datetime(2026, 3, 18, 7, 0, tzinfo=ZoneInfo("UTC")))
        assert (await gate.evaluate("cust", _trigger(), default_prefs)).allow

    @pytest.mark.asyncio
    async def test_quiet_hours_non_wrapping_window(self, state_store, clock):
        """Normal (non-wrapping) quiet window, e.g. a lunch break 12–14.
        Exercises the `start < end` branch that midnight-wrapping prefs
        never hit."""
        prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.LOW,
                               quiet_start_hour=12, quiet_end_hour=14,
                               daily_cap=5, cooldown_hours=24)
        gate = NoiseGate(state_store, clock=clock)
        clock.set(datetime(2026, 3, 18, 11, 59, tzinfo=ZoneInfo("UTC")))
        assert (await gate.evaluate("cust", _trigger(), prefs)).allow
        clock.set(datetime(2026, 3, 18, 12, 0, tzinfo=ZoneInfo("UTC")))
        assert not (await gate.evaluate("cust", _trigger(), prefs)).allow
        clock.set(datetime(2026, 3, 18, 14, 0, tzinfo=ZoneInfo("UTC")))
        assert (await gate.evaluate("cust", _trigger(), prefs)).allow

    @pytest.mark.asyncio
    async def test_urgent_overrides_quiet_hours(self, state_store, default_prefs, clock):
        clock.set(datetime(2026, 3, 18, 3, 0, tzinfo=ZoneInfo("UTC")))
        gate = NoiseGate(state_store, clock=clock)
        d = await gate.evaluate("cust", _trigger(priority=Priority.URGENT), default_prefs)
        assert d.allow

    @pytest.mark.asyncio
    async def test_quiet_hours_respect_customer_timezone(self, state_store, clock):
        """
        14:30 UTC on 2026-03-18 is 10:30 EDT (America/New_York, DST).
        Prefs say quiet 22–07 in NY → 10:30 local is not quiet → allow.

        But 02:00 UTC is 22:00 EDT the previous day → quiet → suppress.
        """
        prefs = ProactivePrefs(timezone="America/New_York",
                               min_priority=Priority.LOW,
                               quiet_start_hour=22, quiet_end_hour=7,
                               daily_cap=5, cooldown_hours=24)
        gate = NoiseGate(state_store, clock=clock)

        # 14:30 UTC = 10:30 EDT → not quiet
        clock.set(datetime(2026, 3, 18, 14, 30, tzinfo=ZoneInfo("UTC")))
        assert (await gate.evaluate("cust", _trigger(), prefs)).allow

        # 03:00 UTC = 23:00 EDT prev day → quiet
        clock.set(datetime(2026, 3, 19, 3, 0, tzinfo=ZoneInfo("UTC")))
        assert not (await gate.evaluate("cust", _trigger(), prefs)).allow


class TestDailyCap:
    @pytest.mark.asyncio
    async def test_cap_blocks_after_n_messages(self, state_store, clock):
        prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.LOW,
                               quiet_start_hour=22, quiet_end_hour=7,
                               daily_cap=2, cooldown_hours=24)
        gate = NoiseGate(state_store, clock=clock)

        # Two allowed, third blocked
        for i in range(2):
            t = _trigger(cooldown_key=f"k{i}")
            d = await gate.evaluate("cust", t, prefs)
            assert d.allow
            await gate.record_sent("cust", t, prefs)

        d = await gate.evaluate("cust", _trigger(cooldown_key="k3"), prefs)
        assert not d.allow
        assert "cap" in d.reason

    @pytest.mark.asyncio
    async def test_cap_resets_next_day(self, state_store, clock):
        prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.LOW,
                               quiet_start_hour=22, quiet_end_hour=7,
                               daily_cap=1, cooldown_hours=1)
        gate = NoiseGate(state_store, clock=clock)

        d = await gate.evaluate("cust", _trigger(), prefs)
        assert d.allow
        await gate.record_sent("cust", _trigger(), prefs)

        # Same day — capped
        clock.advance(timedelta(hours=2))
        assert not (await gate.evaluate("cust", _trigger(), prefs)).allow

        # Next day — reset
        clock.advance(timedelta(days=1))
        assert (await gate.evaluate("cust", _trigger(), prefs)).allow

    @pytest.mark.asyncio
    async def test_urgent_ignores_cap_and_does_not_consume(self, state_store, clock):
        prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.LOW,
                               quiet_start_hour=22, quiet_end_hour=7,
                               daily_cap=1, cooldown_hours=1)
        gate = NoiseGate(state_store, clock=clock)

        # Fill the cap
        t = _trigger()
        await gate.record_sent("cust", t, prefs)

        # URGENT still passes
        u = _trigger(priority=Priority.URGENT)
        assert (await gate.evaluate("cust", u, prefs)).allow
        await gate.record_sent("cust", u, prefs)

        # And the cap for non-urgent is still 1 (urgent didn't count)
        # → already at 1, so next non-urgent blocked
        assert not (await gate.evaluate("cust", _trigger(), prefs)).allow

        # Fresh day, cap reset, one slot — NOT consumed by the urgent above
        clock.advance(timedelta(days=1))
        assert (await gate.evaluate("cust", _trigger(), prefs)).allow

    @pytest.mark.asyncio
    async def test_urgent_leaves_room_in_cap_for_non_urgent(self, state_store, clock):
        """With cap=2: send 1 MEDIUM + 1 URGENT → count is still 1 →
        a second MEDIUM fits. Pins the `< URGENT` exemption — if URGENT
        counted, count would be 2 and the second MEDIUM would be blocked."""
        prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.LOW,
                               quiet_start_hour=22, quiet_end_hour=7,
                               daily_cap=2, cooldown_hours=1)
        gate = NoiseGate(state_store, clock=clock)

        await gate.record_sent("cust", _trigger(), prefs)                      # count → 1
        await gate.record_sent("cust", _trigger(priority=Priority.URGENT), prefs)  # count still 1
        d = await gate.evaluate("cust", _trigger(), prefs)
        assert d.allow, "URGENT must not have consumed a cap slot"
