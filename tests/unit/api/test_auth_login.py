"""Tests for POST /v1/auth/login endpoint."""
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import httpx

from src.api.app import create_app
from src.api.auth import decode_token
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


class TestAuthLogin:
    async def test_valid_login(self, async_client, fake_redis):
        await fake_redis.set("customer_secret:cust_demo", "mysecret")
        resp = await async_client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_demo", "secret": "mysecret"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer_id"] == "cust_demo"
        assert isinstance(data["token"], str) and len(data["token"]) > 0
        # Token should be decodable and carry the right customer_id
        claims = decode_token(data["token"])
        assert claims["customer_id"] == "cust_demo"
        assert "exp" in claims
        assert "iat" in claims

    async def test_wrong_secret(self, async_client, fake_redis):
        await fake_redis.set("customer_secret:cust_demo", "correct")
        resp = await async_client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_demo", "secret": "wrong"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["type"] == "unauthorized"
        assert body["detail"] == "Invalid credentials"

    async def test_unknown_customer(self, async_client):
        resp = await async_client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_unknown", "secret": "anything"},
        )
        # Same 401 and same error body — doesn't reveal whether customer exists
        assert resp.status_code == 401
        body = resp.json()
        assert body["type"] == "unauthorized"
        assert body["detail"] == "Invalid credentials"

    async def test_unknown_and_wrong_secret_indistinguishable(self, async_client, fake_redis):
        """Security: wrong secret and missing customer produce identical responses."""
        await fake_redis.set("customer_secret:cust_demo", "correct")
        wrong_secret = await async_client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_demo", "secret": "wrong"},
        )
        missing_customer = await async_client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_ghost", "secret": "anything"},
        )
        assert wrong_secret.status_code == missing_customer.status_code == 401
        assert wrong_secret.json() == missing_customer.json()

    async def test_invalid_customer_id_format(self, async_client):
        resp = await async_client.post(
            "/v1/auth/login",
            json={"customer_id": "INVALID!", "secret": "anything"},
        )
        assert resp.status_code == 422

    async def test_empty_secret_rejected(self, async_client):
        resp = await async_client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_demo", "secret": ""},
        )
        assert resp.status_code == 422
