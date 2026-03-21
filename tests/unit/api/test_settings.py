"""Tests for GET/PUT /v1/settings — dashboard configuration storage."""
import json
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
from src.api.auth import create_token
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
    return TestClient(app)


@pytest.fixture
async def aclient(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    token = create_token("cust_settings")
    return {"Authorization": f"Bearer {token}"}


def test_get_requires_auth(client):
    assert client.get("/v1/settings").status_code == 401


def test_put_requires_auth(client):
    assert client.put("/v1/settings", json={}).status_code == 401


def test_get_returns_defaults_when_unset(client, auth_headers):
    resp = client.get("/v1/settings", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    # Spot-check defaults from each nested section.
    assert body["working_hours"]["timezone"] == "UTC"
    assert body["briefing"]["enabled"] is True
    assert body["proactive"]["priority_threshold"] == "MEDIUM"
    assert body["personality"]["tone"] == "professional"


@pytest.mark.asyncio
async def test_put_then_get_roundtrips(aclient, auth_headers, fake_redis):
    payload = {
        "working_hours": {"start": "08:30", "end": "17:00", "timezone": "America/New_York"},
        "briefing": {"enabled": False, "time": "07:15"},
        "proactive": {"priority_threshold": "HIGH", "daily_cap": 3, "idle_nudge_minutes": 60},
        "personality": {"tone": "concise", "language": "es", "name": "Aria"},
        "connected_services": {"calendar": True, "n8n": False},
    }
    put = await aclient.put("/v1/settings", headers=auth_headers, json=payload)
    assert put.status_code == 200

    # Persisted under the documented key so other systems can read it.
    raw = await fake_redis.get("settings:cust_settings")
    assert raw is not None
    assert json.loads(raw)["personality"]["name"] == "Aria"

    got = await aclient.get("/v1/settings", headers=auth_headers)
    assert got.status_code == 200
    assert got.json() == payload


def test_put_validates_priority_enum(client, auth_headers):
    resp = client.put(
        "/v1/settings",
        headers=auth_headers,
        json={"proactive": {"priority_threshold": "EXTREME"}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tenant_isolation(aclient):
    """Customer A's settings don't leak to customer B."""
    token_a = create_token("cust_aaa")
    token_b = create_token("cust_bbb")

    await aclient.put(
        "/v1/settings",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"personality": {"tone": "friendly", "language": "en", "name": "Alice"}},
    )

    got_b = await aclient.get(
        "/v1/settings", headers={"Authorization": f"Bearer {token_b}"},
    )
    assert got_b.json()["personality"]["name"] == "Assistant"  # default, not Alice


@pytest.mark.asyncio
async def test_get_handles_partial_stored_json(aclient, auth_headers, fake_redis):
    # Simulate a schema evolution: old record only has one section.
    await fake_redis.set(
        "settings:cust_settings",
        json.dumps({"personality": {"tone": "detailed", "language": "fr", "name": "Old"}}),
    )
    resp = await aclient.get("/v1/settings", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["personality"]["tone"] == "detailed"
    # Missing sections filled from defaults — forward-compatible.
    assert body["working_hours"]["start"] == "09:00"
