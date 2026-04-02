"""Tests for enhanced provisioning: seeding settings, auth, onboarding, demo."""
import json
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import fakeredis.aioredis
import httpx

from src.api.app import create_app
from src.api.ea_registry import EARegistry
from src.onboarding.state import OnboardingStateStore


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def onboarding_store(fake_redis):
    return OnboardingStateStore(fake_redis)


@pytest.fixture
def mock_orchestrator():
    orch = AsyncMock()

    async def _provision(customer_id, tier="professional", **_):
        env = MagicMock()
        env.customer_id = customer_id
        env.tier = tier
        return env

    orch.provision_customer_environment = AsyncMock(side_effect=_provision)
    return orch


@pytest.fixture
def app(mock_orchestrator, fake_redis, onboarding_store):
    return create_app(
        ea_registry=EARegistry(factory=MagicMock()),
        orchestrator=mock_orchestrator,
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
        onboarding_state_store=onboarding_store,
    )


@pytest.fixture
async def aclient(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestProvisionSeeding:
    @pytest.mark.asyncio
    async def test_seeds_default_settings(self, aclient, fake_redis):
        resp = await aclient.post("/v1/customers/provision", json={"tier": "basic"})
        assert resp.status_code == 201
        cid = resp.json()["customer_id"]

        raw = await fake_redis.get(f"settings:{cid}")
        assert raw is not None
        settings = json.loads(raw)
        assert settings["working_hours"]["timezone"] == "UTC"
        assert settings["personality"]["tone"] == "professional"

    @pytest.mark.asyncio
    async def test_creates_auth_secret(self, aclient, fake_redis):
        resp = await aclient.post("/v1/customers/provision", json={"tier": "basic"})
        cid = resp.json()["customer_id"]

        secret = await fake_redis.get(f"auth:{cid}:secret")
        assert secret is not None
        decoded = secret.decode() if isinstance(secret, bytes) else secret
        assert len(decoded) > 10

    @pytest.mark.asyncio
    async def test_response_includes_dashboard_secret(self, aclient):
        resp = await aclient.post("/v1/customers/provision", json={"tier": "basic"})
        body = resp.json()
        assert "dashboard_secret" in body
        assert body["dashboard_secret"] is not None
        assert len(body["dashboard_secret"]) > 10

    @pytest.mark.asyncio
    async def test_initializes_onboarding(self, aclient, fake_redis):
        resp = await aclient.post("/v1/customers/provision", json={"tier": "basic"})
        cid = resp.json()["customer_id"]

        raw = await fake_redis.get(f"onboarding:{cid}")
        assert raw is not None
        state = json.loads(raw)
        assert state["status"] == "not_started"
        assert state["current_step"] == 0

    @pytest.mark.asyncio
    async def test_explicit_customer_id(self, aclient, fake_redis):
        resp = await aclient.post(
            "/v1/customers/provision",
            json={"tier": "basic", "customer_id": "acme-test-001"},
        )
        assert resp.status_code == 201
        cid = resp.json()["customer_id"]
        assert cid == "acme-test-001"

        raw = await fake_redis.get(f"settings:{cid}")
        assert raw is not None
        settings = json.loads(raw)
        assert settings["personality"]["tone"] == "professional"
        assert settings["working_hours"]["timezone"] == "UTC"


class TestProvisionDemo:
    @pytest.mark.asyncio
    async def test_demo_flag_accepted(self, aclient):
        resp = await aclient.post(
            "/v1/customers/provision",
            json={"tier": "professional", "demo": True},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_demo_marks_onboarding_completed(self, aclient, fake_redis):
        resp = await aclient.post(
            "/v1/customers/provision",
            json={"tier": "professional", "demo": True},
        )
        cid = resp.json()["customer_id"]

        raw = await fake_redis.get(f"onboarding:{cid}")
        state = json.loads(raw)
        assert state["status"] == "completed"

    @pytest.mark.asyncio
    async def test_demo_seeds_non_default_settings(self, aclient, fake_redis):
        resp = await aclient.post(
            "/v1/customers/provision",
            json={"tier": "professional", "demo": True},
        )
        cid = resp.json()["customer_id"]

        raw = await fake_redis.get(f"settings:{cid}")
        settings = json.loads(raw)
        assert settings["personality"]["name"] == "Aria"

    @pytest.mark.asyncio
    async def test_demo_false_does_not_seed_demo_data(self, aclient, fake_redis):
        resp = await aclient.post(
            "/v1/customers/provision",
            json={"tier": "professional"},
        )
        cid = resp.json()["customer_id"]

        raw = await fake_redis.get(f"onboarding:{cid}")
        state = json.loads(raw)
        assert state["status"] == "not_started"
