"""Tests for CustomerSettingsLoader — Redis → NoiseConfig/BehaviorConfig projection."""
import json
import pytest
from datetime import datetime, timezone

from src.proactive.settings_loader import CustomerSettingsLoader
from src.proactive.gate import NoiseConfig
from src.proactive.behaviors import BehaviorConfig
from src.proactive.triggers import Priority


CID = "cust_settings_test"


@pytest.fixture
def loader(fake_redis):
    # Short TTL so cache tests can drive expiry via clock
    return CustomerSettingsLoader(fake_redis, ttl_seconds=180)


async def _seed(redis, customer_id: str, settings: dict) -> None:
    await redis.set(f"settings:{customer_id}", json.dumps(settings))


# --- Defaults ----------------------------------------------------------------

class TestMissingKey:
    """No settings:{cid} in Redis → fall back to Settings() defaults."""

    async def test_noise_config_defaults_match_current_hardcoded(self, loader):
        cfg = await loader.noise_config_for(CID)
        assert isinstance(cfg, NoiseConfig)
        assert cfg.priority_threshold == Priority.MEDIUM
        assert cfg.daily_cap == 5
        assert cfg.timezone == "UTC"

    async def test_noise_config_default_quiet_hours_from_default_working_hours(self, loader):
        # Default working hours are 09:00–18:00 → quiet is 18→09
        cfg = await loader.noise_config_for(CID)
        assert cfg.quiet_start == 18
        assert cfg.quiet_end == 9

    async def test_behavior_config_defaults(self, loader):
        cfg = await loader.behavior_config_for(CID)
        assert isinstance(cfg, BehaviorConfig)
        assert cfg.briefing_hour == 8
        assert cfg.briefing_enabled is True
        assert cfg.timezone == "UTC"
        assert cfg.tone == "professional"
        assert cfg.ea_name == "Assistant"
        assert cfg.language == "en"
        assert cfg.idle_nudge_minutes == 120


# --- NoiseConfig projection --------------------------------------------------

class TestNoiseConfigProjection:

    async def test_priority_threshold_string_to_enum(self, fake_redis, loader):
        await _seed(fake_redis, CID, {
            "proactive": {"priority_threshold": "HIGH", "daily_cap": 3},
        })
        cfg = await loader.noise_config_for(CID)
        assert cfg.priority_threshold == Priority.HIGH
        assert cfg.daily_cap == 3

    async def test_low_threshold(self, fake_redis, loader):
        await _seed(fake_redis, CID, {
            "proactive": {"priority_threshold": "LOW"},
        })
        cfg = await loader.noise_config_for(CID)
        assert cfg.priority_threshold == Priority.LOW

    async def test_working_hours_invert_to_quiet_hours(self, fake_redis, loader):
        # Working 07:00–19:00 America/New_York → quiet 19→07 in that TZ
        await _seed(fake_redis, CID, {
            "working_hours": {"start": "07:00", "end": "19:00",
                              "timezone": "America/New_York"},
        })
        cfg = await loader.noise_config_for(CID)
        assert cfg.quiet_start == 19
        assert cfg.quiet_end == 7
        assert cfg.timezone == "America/New_York"

    async def test_working_hours_with_minutes_truncates_to_hour(self, fake_redis, loader):
        # "09:30" → hour 9 (gate operates on hour granularity)
        await _seed(fake_redis, CID, {
            "working_hours": {"start": "09:30", "end": "17:45"},
        })
        cfg = await loader.noise_config_for(CID)
        assert cfg.quiet_start == 17
        assert cfg.quiet_end == 9

    async def test_daily_cap_zero(self, fake_redis, loader):
        await _seed(fake_redis, CID, {"proactive": {"daily_cap": 0}})
        cfg = await loader.noise_config_for(CID)
        assert cfg.daily_cap == 0


# --- BehaviorConfig projection -----------------------------------------------

class TestBehaviorConfigProjection:

    async def test_briefing_time_parsed_to_hour(self, fake_redis, loader):
        await _seed(fake_redis, CID, {
            "briefing": {"enabled": True, "time": "06:30"},
        })
        cfg = await loader.behavior_config_for(CID)
        assert cfg.briefing_hour == 6
        assert cfg.briefing_enabled is True

    async def test_briefing_disabled(self, fake_redis, loader):
        await _seed(fake_redis, CID, {
            "briefing": {"enabled": False, "time": "08:00"},
        })
        cfg = await loader.behavior_config_for(CID)
        assert cfg.briefing_enabled is False

    async def test_personality_fields(self, fake_redis, loader):
        await _seed(fake_redis, CID, {
            "personality": {"tone": "friendly", "language": "es", "name": "Sarah"},
        })
        cfg = await loader.behavior_config_for(CID)
        assert cfg.tone == "friendly"
        assert cfg.language == "es"
        assert cfg.ea_name == "Sarah"

    async def test_idle_nudge_minutes(self, fake_redis, loader):
        await _seed(fake_redis, CID, {
            "proactive": {"idle_nudge_minutes": 480},
        })
        cfg = await loader.behavior_config_for(CID)
        assert cfg.idle_nudge_minutes == 480

    async def test_timezone_from_working_hours(self, fake_redis, loader):
        await _seed(fake_redis, CID, {
            "working_hours": {"timezone": "Europe/London"},
        })
        cfg = await loader.behavior_config_for(CID)
        assert cfg.timezone == "Europe/London"


# --- Caching -----------------------------------------------------------------

class TestCaching:

    async def test_second_call_within_ttl_does_not_hit_redis(self, fake_redis):
        """Modify Redis between calls; cached value should persist."""
        t0 = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
        loader = CustomerSettingsLoader(
            fake_redis, ttl_seconds=180, clock=lambda: t0,
        )
        await _seed(fake_redis, CID, {"proactive": {"daily_cap": 3}})
        cfg1 = await loader.noise_config_for(CID)
        assert cfg1.daily_cap == 3

        # Change Redis; loader should not see it
        await _seed(fake_redis, CID, {"proactive": {"daily_cap": 99}})
        cfg2 = await loader.noise_config_for(CID)
        assert cfg2.daily_cap == 3  # still cached

    async def test_call_after_ttl_refetches(self, fake_redis):
        times = [datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)]
        loader = CustomerSettingsLoader(
            fake_redis, ttl_seconds=180, clock=lambda: times[0],
        )
        await _seed(fake_redis, CID, {"proactive": {"daily_cap": 3}})
        cfg1 = await loader.noise_config_for(CID)
        assert cfg1.daily_cap == 3

        # Advance past TTL, change Redis
        times[0] = datetime(2026, 3, 21, 10, 4, tzinfo=timezone.utc)  # +240s > 180
        await _seed(fake_redis, CID, {"proactive": {"daily_cap": 7}})
        cfg2 = await loader.noise_config_for(CID)
        assert cfg2.daily_cap == 7

    async def test_cache_isolated_per_customer(self, fake_redis, loader):
        await _seed(fake_redis, "cust_a", {"proactive": {"daily_cap": 1}})
        await _seed(fake_redis, "cust_b", {"proactive": {"daily_cap": 9}})
        a = await loader.noise_config_for("cust_a")
        b = await loader.noise_config_for("cust_b")
        assert a.daily_cap == 1
        assert b.daily_cap == 9

    async def test_missing_key_also_cached(self, fake_redis):
        """Don't hammer Redis for customers who never configured settings."""
        t0 = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
        loader = CustomerSettingsLoader(
            fake_redis, ttl_seconds=180, clock=lambda: t0,
        )
        cfg1 = await loader.noise_config_for(CID)
        # Now seed — should still return cached defaults
        await _seed(fake_redis, CID, {"proactive": {"daily_cap": 50}})
        cfg2 = await loader.noise_config_for(CID)
        assert cfg2.daily_cap == cfg1.daily_cap  # still default


# --- Malformed data ----------------------------------------------------------

class TestMalformedData:

    async def test_garbage_json_falls_back_to_defaults(self, fake_redis, loader):
        await fake_redis.set(f"settings:{CID}", "not-json{")
        cfg = await loader.noise_config_for(CID)
        assert cfg.priority_threshold == Priority.MEDIUM

    async def test_partial_settings_fills_defaults(self, fake_redis, loader):
        """Only working_hours set — everything else defaults."""
        await _seed(fake_redis, CID, {
            "working_hours": {"timezone": "Asia/Tokyo"},
        })
        ncfg = await loader.noise_config_for(CID)
        bcfg = await loader.behavior_config_for(CID)
        assert ncfg.timezone == "Asia/Tokyo"
        assert ncfg.daily_cap == 5  # default
        assert bcfg.briefing_hour == 8  # default
