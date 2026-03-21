"""Tests for POST /v1/auth/login — dashboard bootstrap auth."""
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import fakeredis.aioredis
import httpx
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import decode_token
from src.api.ea_registry import EARegistry


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def app(fake_redis):
    return create_app(
        ea_registry=EARegistry(factory=MagicMock(), max_size=10),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
    )


@pytest.fixture
def client(app):
    # Sync TestClient for cases that DON'T seed fakeredis — TestClient
    # runs its own event loop which would conflict with the one
    # fakeredis's queue is bound to. Async-seeded tests use aclient.
    return TestClient(app)


@pytest.fixture
async def aclient(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_login_success_returns_valid_jwt(aclient, fake_redis):
    # fakeredis (like real redis.asyncio without decode_responses) returns
    # bytes on get() regardless of whether set() received str or bytes —
    # so this test already exercises the decode branch in the handler.
    await fake_redis.set("auth:cust_dash:secret", "s3cret-key-123")

    resp = await aclient.post(
        "/v1/auth/login",
        json={"customer_id": "cust_dash", "secret": "s3cret-key-123"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] == "cust_dash"
    # The token must decode and carry the same customer_id the rest of
    # the API expects — otherwise the dashboard can't make auth'd calls.
    claims = decode_token(body["token"])
    assert claims["customer_id"] == "cust_dash"


@pytest.mark.asyncio
async def test_login_wrong_secret_is_401(aclient, fake_redis):
    await fake_redis.set("auth:cust_dash:secret", "correct")
    resp = await aclient.post(
        "/v1/auth/login",
        json={"customer_id": "cust_dash", "secret": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_login_unknown_customer_is_401(client):
    resp = client.post(
        "/v1/auth/login",
        json={"customer_id": "cust_nobody", "secret": "whatever"},
    )
    assert resp.status_code == 401
    # Identical message to wrong-secret — don't leak customer enumeration.
    assert resp.json()["detail"] == "Invalid credentials"


def test_login_rejects_invalid_customer_id_format(client):
    # Uppercase rejected by the same pattern as ProvisionRequest.
    resp = client.post(
        "/v1/auth/login",
        json={"customer_id": "BAD_ID", "secret": "x"},
    )
    assert resp.status_code == 422
