"""Tests for demo data seeding."""
import json
from datetime import date

import pytest
import fakeredis.aioredis

from src.onboarding.demo import seed_demo_data, DEMO_SETTINGS
from src.onboarding.state import OnboardingStateStore
from src.proactive.state import ProactiveStateStore
from datetime import datetime, timezone

CID = "cust_demo_test"
CID_B = "cust_demo_other"


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def onboarding_store(fake_redis):
    return OnboardingStateStore(fake_redis)


@pytest.fixture
def proactive_store(fake_redis):
    return ProactiveStateStore(fake_redis)


class TestSeedDemoData:
    @pytest.mark.asyncio
    async def test_seeds_non_default_settings(self, fake_redis, onboarding_store, proactive_store):
        await onboarding_store.initialize(CID)
        await seed_demo_data(fake_redis, CID, onboarding_store, proactive_store)

        raw = await fake_redis.get(f"settings:{CID}")
        assert raw is not None
        settings = json.loads(raw)
        assert settings["personality"]["name"] == "Aria"
        assert settings["personality"]["tone"] == "friendly"
        assert settings["working_hours"]["timezone"] == "America/New_York"

    @pytest.mark.asyncio
    async def test_marks_onboarding_completed(self, fake_redis, onboarding_store, proactive_store):
        await onboarding_store.initialize(CID)
        await seed_demo_data(fake_redis, CID, onboarding_store, proactive_store)

        state = await onboarding_store.get(CID)
        assert state.status == "completed"

    @pytest.mark.asyncio
    async def test_seeds_notifications(self, fake_redis, onboarding_store, proactive_store):
        await onboarding_store.initialize(CID)
        await seed_demo_data(fake_redis, CID, onboarding_store, proactive_store)

        notifications = await proactive_store.list_pending_notifications(
            CID, now=datetime.now(timezone.utc),
        )
        assert len(notifications) >= 3

    @pytest.mark.asyncio
    async def test_seeds_activity_counters(self, fake_redis, onboarding_store, proactive_store):
        await seed_demo_data(fake_redis, CID, onboarding_store, proactive_store)

        today = date.today().isoformat()
        raw = await fake_redis.get(f"activity:{CID}:messages:{today}")
        assert raw is not None
        assert int(raw) > 0

    @pytest.mark.asyncio
    async def test_tenant_isolated(self, fake_redis, onboarding_store, proactive_store):
        await onboarding_store.initialize(CID)
        await onboarding_store.initialize(CID_B)
        await seed_demo_data(fake_redis, CID, onboarding_store, proactive_store)

        # CID_B should not have demo data
        state_b = await onboarding_store.get(CID_B)
        assert state_b.status == "not_started"

        notifs_b = await proactive_store.list_pending_notifications(
            CID_B, now=datetime.now(timezone.utc),
        )
        assert len(notifs_b) == 0

    @pytest.mark.asyncio
    async def test_works_without_onboarding_store(self, fake_redis, proactive_store):
        """Gracefully handles None onboarding_store."""
        await seed_demo_data(fake_redis, CID, None, proactive_store)

        raw = await fake_redis.get(f"settings:{CID}")
        assert raw is not None  # Settings still seeded

    @pytest.mark.asyncio
    async def test_works_without_proactive_store(self, fake_redis, onboarding_store):
        """Gracefully handles None proactive_store."""
        await onboarding_store.initialize(CID)
        await seed_demo_data(fake_redis, CID, onboarding_store, None)

        state = await onboarding_store.get(CID)
        assert state.status == "completed"  # Onboarding still marked complete
