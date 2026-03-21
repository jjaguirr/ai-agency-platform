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
    """Customer A's settings don't leak to customer B.

    Ordering matters: prove A's write is live BEFORE checking B can't
    see it. Without the A-reads-back step, this test passes against a
    no-op PUT — "B sees default" is vacuously true when nothing writes.
    """
    token_a = create_token("cust_aaa")
    token_b = create_token("cust_bbb")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    put = await aclient.put(
        "/v1/settings",
        headers=headers_a,
        json={"personality": {"tone": "friendly", "language": "en", "name": "Alice"}},
    )
    assert put.status_code == 200

    # A sees their own write.
    got_a = await aclient.get("/v1/settings", headers=headers_a)
    assert got_a.json()["personality"]["name"] == "Alice"

    # B does NOT see A's write.
    got_b = await aclient.get("/v1/settings", headers=headers_b)
    assert got_b.json()["personality"]["name"] == "Assistant"


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


# --- Live n8n health on GET --------------------------------------------------
# connected_services.n8n is stored as a dumb bool the customer PUTs — it
# means nothing. When an N8nClient is wired on app.state, GET probes it
# via list_workflows() and overrides the stored value with reality.
# No client → stored value passes through (legacy + test_put_then_get_roundtrips
# above relies on exact-payload echo).

class TestN8nHealthOnGet:
    def _app(self, fake_redis, *, n8n_client):
        return create_app(
            ea_registry=EARegistry(factory=MagicMock(), max_size=10),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=fake_redis,
            n8n_client=n8n_client,
        )

    @pytest.fixture
    def auth_headers(self):
        token = create_token("cust_n8n")
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_healthy_n8n_overrides_stored_false(self, fake_redis, auth_headers):
        """Stored n8n=False but probe succeeds → response shows True."""
        await fake_redis.set("settings:cust_n8n", json.dumps({
            "connected_services": {"calendar": False, "n8n": False},
        }))
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(return_value=[{"id": "wf_1"}])
        app = self._app(fake_redis, n8n_client=n8n)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/v1/settings", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["connected_services"]["n8n"] is True
        n8n.list_workflows.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unhealthy_n8n_overrides_stored_true(self, fake_redis, auth_headers):
        """Stored n8n=True but probe raises → response shows False.
        N8nError is the documented failure surface of N8nClient."""
        from src.workflows.client import N8nError

        await fake_redis.set("settings:cust_n8n", json.dumps({
            "connected_services": {"calendar": False, "n8n": True},
        }))
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(side_effect=N8nError("502 bad gateway"))
        app = self._app(fake_redis, n8n_client=n8n)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/v1/settings", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["connected_services"]["n8n"] is False

    @pytest.mark.asyncio
    async def test_n8n_timeout_reports_false(self, fake_redis, auth_headers):
        """Slow n8n (>2s) → False, and the GET doesn't hang waiting."""
        import asyncio

        async def slow_list():
            await asyncio.sleep(10)  # would hang the test if not bounded
            return []

        n8n = MagicMock()
        n8n.list_workflows = slow_list
        app = self._app(fake_redis, n8n_client=n8n)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            # If the route doesn't bound the probe, this await blocks for
            # 10s and pytest-asyncio will flag the slow test. 3s gives the
            # 2s cap room to fire.
            resp = await asyncio.wait_for(
                c.get("/v1/settings", headers=auth_headers), timeout=3.0,
            )

        assert resp.status_code == 200
        assert resp.json()["connected_services"]["n8n"] is False

    @pytest.mark.asyncio
    async def test_no_client_passes_stored_value_through(self, fake_redis, auth_headers):
        """n8n_client=None → no probe, stored value echoed. This is what
        keeps test_put_then_get_roundtrips above passing unchanged."""
        await fake_redis.set("settings:cust_n8n", json.dumps({
            "connected_services": {"calendar": True, "n8n": True},
        }))
        app = self._app(fake_redis, n8n_client=None)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/v1/settings", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["connected_services"]["n8n"] is True

    @pytest.mark.asyncio
    async def test_probe_exception_does_not_500(self, fake_redis, auth_headers):
        """Weird exception type from probe → still 200, n8n=False.
        Settings GET is the dashboard's landing page; it must not fail
        because n8n's having a bad day."""
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(side_effect=RuntimeError("unexpected"))
        app = self._app(fake_redis, n8n_client=n8n)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/v1/settings", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["connected_services"]["n8n"] is False

    @pytest.mark.asyncio
    async def test_calendar_unchanged_by_n8n_probe(self, fake_redis, auth_headers):
        """n8n probe only touches n8n — calendar stays whatever was stored.
        (No calendar integration exists yet; the stored bool is all we have.)"""
        await fake_redis.set("settings:cust_n8n", json.dumps({
            "connected_services": {"calendar": True, "n8n": False},
        }))
        n8n = MagicMock()
        n8n.list_workflows = AsyncMock(return_value=[])
        app = self._app(fake_redis, n8n_client=n8n)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/v1/settings", headers=auth_headers)

        body = resp.json()
        assert body["connected_services"]["calendar"] is True  # stored, untouched
        assert body["connected_services"]["n8n"] is True       # probed, live
