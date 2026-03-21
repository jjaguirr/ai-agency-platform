"""Tests for CustomerSettingsCache — per-customer config from Redis with TTL."""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import fakeredis.aioredis

from src.proactive.settings_cache import CustomerSettingsCache, CustomerConfig, PersonalityConfig
from src.proactive.gate import NoiseConfig
from src.proactive.behaviors import BehaviorConfig
from src.proactive.triggers import Priority


CID = "cust_cache_test"
SETTINGS_KEY = f"settings:{CID}"


def _settings_json(
    *,
    wh_start="09:00",
    wh_end="18:00",
    tz="UTC",
    briefing_enabled=True,
    briefing_time="08:00",
    priority_threshold="MEDIUM",
    daily_cap=5,
    idle_nudge_minutes=120,
    tone="professional",
    language="en",
    name="Assistant",
    calendar=False,
    n8n=False,
    anomaly_threshold=2.0,
    monthly_budget=None,
) -> str:
    d = {
        "working_hours": {"start": wh_start, "end": wh_end, "timezone": tz},
        "briefing": {"enabled": briefing_enabled, "time": briefing_time},
        "proactive": {
            "priority_threshold": priority_threshold,
            "daily_cap": daily_cap,
            "idle_nudge_minutes": idle_nudge_minutes,
            "anomaly_threshold": anomaly_threshold,
        },
        "personality": {"tone": tone, "language": language, "name": name},
        "connected_services": {"calendar": calendar, "n8n": n8n},
    }
    if monthly_budget is not None:
        d["proactive"]["monthly_budget"] = monthly_budget
    return json.dumps(d)


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def cache(fake_redis):
    return CustomerSettingsCache(fake_redis, ttl_seconds=120)


class TestDefaults:
    async def test_returns_defaults_when_no_settings_key(self, cache):
        config = await cache.get(CID)
        assert isinstance(config, CustomerConfig)
        assert config.noise.priority_threshold == Priority.MEDIUM
        assert config.noise.daily_cap == 5
        assert config.noise.timezone == "UTC"
        assert config.behavior.briefing_hour == 8
        assert config.behavior.timezone == "UTC"
        assert config.personality.tone == "professional"
        assert config.personality.name == "Assistant"
        assert config.briefing_enabled is True


class TestConfigBuilding:
    async def test_builds_noise_config_from_settings(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(
            priority_threshold="HIGH",
            daily_cap=10,
            tz="America/New_York",
            wh_start="09:00",
            wh_end="17:00",
        ))
        config = await cache.get(CID)
        assert config.noise.priority_threshold == Priority.HIGH
        assert config.noise.daily_cap == 10
        assert config.noise.timezone == "America/New_York"

    async def test_quiet_hours_from_working_hours_inversion(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(
            wh_start="09:00", wh_end="18:00",
        ))
        config = await cache.get(CID)
        assert config.noise.quiet_start == 18
        assert config.noise.quiet_end == 9

    async def test_quiet_hours_inversion_early_shift(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(
            wh_start="06:00", wh_end="14:00",
        ))
        config = await cache.get(CID)
        assert config.noise.quiet_start == 14
        assert config.noise.quiet_end == 6

    async def test_builds_behavior_config_from_settings(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(
            briefing_time="07:30",
            tz="US/Eastern",
            idle_nudge_minutes=10080,  # 7 days
        ))
        config = await cache.get(CID)
        assert config.behavior.briefing_hour == 7
        assert config.behavior.timezone == "US/Eastern"
        assert config.behavior.idle_days == 7

    async def test_idle_days_minimum_one(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(
            idle_nudge_minutes=60,  # less than 1 day
        ))
        config = await cache.get(CID)
        assert config.behavior.idle_days == 1

    async def test_personality_settings_returned(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(
            tone="friendly", language="es", name="Maria",
        ))
        config = await cache.get(CID)
        assert config.personality.tone == "friendly"
        assert config.personality.language == "es"
        assert config.personality.name == "Maria"

    async def test_briefing_disabled(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(briefing_enabled=False))
        config = await cache.get(CID)
        assert config.briefing_enabled is False

    async def test_connected_services(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(calendar=True, n8n=True))
        config = await cache.get(CID)
        assert config.connected_services["calendar"] is True
        assert config.connected_services["n8n"] is True

    async def test_anomaly_threshold_returned(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(anomaly_threshold=3.0))
        config = await cache.get(CID)
        assert config.anomaly_threshold == 3.0

    async def test_monthly_budget_returned(self, cache, fake_redis):
        await fake_redis.set(SETTINGS_KEY, _settings_json(monthly_budget=5000.0))
        config = await cache.get(CID)
        assert config.monthly_budget == 5000.0


class TestTTLCache:
    async def test_second_call_within_ttl_reuses_cache(self, fake_redis):
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=120)
        await fake_redis.set(SETTINGS_KEY, _settings_json(daily_cap=10))

        config1 = await cache.get(CID)
        # Change Redis value — should NOT be reflected
        await fake_redis.set(SETTINGS_KEY, _settings_json(daily_cap=20))
        config2 = await cache.get(CID)

        assert config1.noise.daily_cap == 10
        assert config2.noise.daily_cap == 10  # still cached

    async def test_cache_refreshes_after_ttl_expiry(self, fake_redis):
        t = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
        calls = [t]

        def clock():
            return calls[0]

        cache = CustomerSettingsCache(fake_redis, ttl_seconds=120, clock=clock)
        await fake_redis.set(SETTINGS_KEY, _settings_json(daily_cap=10))
        config1 = await cache.get(CID)

        # Advance clock past TTL
        calls[0] = datetime(2026, 3, 19, 10, 3, tzinfo=timezone.utc)  # +3 min
        await fake_redis.set(SETTINGS_KEY, _settings_json(daily_cap=20))
        config2 = await cache.get(CID)

        assert config1.noise.daily_cap == 10
        assert config2.noise.daily_cap == 20  # refreshed

    async def test_invalidate_clears_cache(self, fake_redis):
        cache = CustomerSettingsCache(fake_redis, ttl_seconds=120)
        await fake_redis.set(SETTINGS_KEY, _settings_json(daily_cap=10))
        await cache.get(CID)

        await fake_redis.set(SETTINGS_KEY, _settings_json(daily_cap=20))
        cache.invalidate(CID)
        config = await cache.get(CID)
        assert config.noise.daily_cap == 20


class TestForwardCompatibility:
    async def test_tolerates_extra_keys_in_redis(self, cache, fake_redis):
        data = json.loads(_settings_json())
        data["unknown_section"] = {"foo": "bar"}
        await fake_redis.set(SETTINGS_KEY, json.dumps(data))
        config = await cache.get(CID)
        # Should not crash, returns defaults for known fields
        assert config.noise.priority_threshold == Priority.MEDIUM

    async def test_tolerates_missing_sections(self, cache, fake_redis):
        # Minimal settings — only working_hours
        await fake_redis.set(SETTINGS_KEY, json.dumps({"working_hours": {"start": "10:00", "end": "19:00", "timezone": "UTC"}}))
        config = await cache.get(CID)
        assert config.noise.quiet_start == 19
        assert config.noise.quiet_end == 10
        # Other fields get defaults
        assert config.noise.priority_threshold == Priority.MEDIUM
