"""Tests for GET/PUT /v1/settings endpoints."""
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import httpx
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry

import fakeredis.aioredis


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def app(fake_redis):
    ea = AsyncMock()
    factory = MagicMock(return_value=ea)
    return create_app(
        ea_registry=EARegistry(factory=factory, max_size=10),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
    )


@pytest.fixture
async def async_client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def token():
    return create_token("cust_test")


class TestGetSettings:
    async def test_returns_defaults_when_empty(self, async_client, token):
        resp = await async_client.get(
            "/v1/settings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # All fields should be null
        assert data["working_hours_start"] is None
        assert data["tone"] is None
        assert data["ea_name"] is None

    def test_requires_auth(self, app):
        client = TestClient(app)
        resp = client.get("/v1/settings")
        assert resp.status_code == 401

    async def test_tenant_isolation(self, async_client, fake_redis):
        # Store settings for cust_a
        import json
        await fake_redis.set(
            "settings:cust_aaa",
            json.dumps({"ea_name": "Alice's EA"}),
        )
        # Request as cust_bbb — should not see cust_aaa's settings
        token_b = create_token("cust_bbb")
        resp = await async_client.get(
            "/v1/settings",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200
        assert resp.json()["ea_name"] is None


class TestPutSettings:
    async def test_save_and_load_roundtrip(self, async_client, token):
        payload = {
            "working_hours_start": "09:00",
            "working_hours_end": "17:00",
            "timezone": "America/New_York",
            "briefing_enabled": True,
            "briefing_time": "08:00",
            "ea_name": "Aria",
            "tone": "friendly",
            "language": "en",
        }
        put_resp = await async_client.put(
            "/v1/settings",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["ea_name"] == "Aria"

        # GET should return the same data
        get_resp = await async_client.get(
            "/v1/settings",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = get_resp.json()
        assert data["working_hours_start"] == "09:00"
        assert data["tone"] == "friendly"
        assert data["ea_name"] == "Aria"

    async def test_full_replace_semantics(self, async_client, token):
        # First PUT with ea_name
        await async_client.put(
            "/v1/settings",
            json={"ea_name": "Aria"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Second PUT without ea_name — should reset to null
        await async_client.put(
            "/v1/settings",
            json={"tone": "concise"},
            headers={"Authorization": f"Bearer {token}"},
        )
        get_resp = await async_client.get(
            "/v1/settings",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = get_resp.json()
        assert data["ea_name"] is None
        assert data["tone"] == "concise"

    async def test_invalid_tone_rejected(self, async_client, token):
        resp = await async_client.put(
            "/v1/settings",
            json={"tone": "sarcastic"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
