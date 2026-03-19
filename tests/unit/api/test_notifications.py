"""
GET /v1/notifications — pull model for proactive messages.

Customers without WhatsApp (or when WhatsApp delivery fails) retrieve
proactive messages via this endpoint. Each GET drains the queue — once
retrieved, notifications are marked delivered and won't be returned again.

Ordered by priority DESC, then created_at ASC. Tenant-isolated.

Test-infra note: TestClient runs handlers in its own event loop;
fakeredis's async client binds an internal asyncio.Queue to whichever
loop first touches it. Writing from the pytest-asyncio loop then reading
from TestClient's loop faults. We sidestep by writing raw Redis keys via
the SYNC fakeredis API (no loop affinity) against a shared FakeServer,
letting the app's async client bind to TestClient's loop unmolested.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


@pytest.fixture
def fake_server():
    import fakeredis
    return fakeredis.FakeServer()


@pytest.fixture
def sync_redis(fake_server):
    """Sync client for test-body setup — shares backend with app's async client."""
    import fakeredis
    return fakeredis.FakeStrictRedis(server=fake_server, decode_responses=True)


@pytest.fixture
def app(fake_server, mock_ea):
    import fakeredis.aioredis
    redis_client = fakeredis.aioredis.FakeRedis(
        server=fake_server, decode_responses=True
    )
    return create_app(
        ea_registry=EARegistry(factory=lambda cid: mock_ea),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=redis_client,
    )


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {create_token('cust_notif')}"}


def _enqueue(sync_redis, customer_id: str, *triggers):
    """Write triggers directly to the notifications key.

    Mirrors ProactiveStateStore.enqueue_notification's wire format
    without going through the async client — see module docstring for
    why. Coupling to the key layout is the price of clean event-loop
    isolation; the state-store unit tests already cover that format.
    """
    key = f"proactive:{customer_id}:notifications"
    sync_redis.set(key, json.dumps([t.to_dict() for t in triggers]))


class TestNotificationsEndpoint:
    def test_empty_queue_returns_empty_list(self, app, auth_headers):
        client = TestClient(app)
        resp = client.get("/v1/notifications", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"notifications": []}

    def test_returns_pending_and_drains(self, app, auth_headers, sync_redis):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        t = ProactiveTrigger(
            domain="ea", trigger_type="briefing", priority=Priority.MEDIUM,
            title="Morning", payload={"n_items": 2},
            suggested_message="Good morning — 2 items today.",
            created_at=datetime(2026, 3, 18, 8, 0, tzinfo=ZoneInfo("UTC")),
        )
        _enqueue(sync_redis, "cust_notif", t)

        # `with` keeps one loop alive across both requests — without it
        # TestClient spins a fresh portal per call and the fakeredis
        # connection pool (bound on first request) faults on the second.
        with TestClient(app) as client:
            resp = client.get("/v1/notifications", headers=auth_headers)
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["notifications"]) == 1
            assert body["notifications"][0]["title"] == "Morning"
            assert body["notifications"][0]["priority"] == "medium"
            assert body["notifications"][0]["message"] == "Good morning — 2 items today."

            # Second GET — drained
            resp2 = client.get("/v1/notifications", headers=auth_headers)
            assert resp2.json() == {"notifications": []}

    def test_ordered_by_priority_then_timestamp(self, app, auth_headers, sync_redis):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        base = datetime(2026, 3, 18, 8, 0, tzinfo=ZoneInfo("UTC"))

        triggers = []
        for i, (prio, dt) in enumerate([
            (Priority.MEDIUM, base + timedelta(minutes=10)),
            (Priority.URGENT, base + timedelta(minutes=20)),
            (Priority.MEDIUM, base),
        ]):
            triggers.append(ProactiveTrigger(
                domain="x", trigger_type="y", priority=prio,
                title=f"t{i}", payload={}, suggested_message="m",
                created_at=dt,
            ))
        _enqueue(sync_redis, "cust_notif", *triggers)

        client = TestClient(app)
        resp = client.get("/v1/notifications", headers=auth_headers)
        titles = [n["title"] for n in resp.json()["notifications"]]
        # urgent first, then medium by timestamp ascending (t2 older than t0)
        assert titles == ["t1", "t2", "t0"]

    def test_requires_auth(self, app):
        client = TestClient(app)
        resp = client.get("/v1/notifications")
        assert resp.status_code == 401

    def test_tenant_isolation(self, app, sync_redis):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        t = ProactiveTrigger(domain="x", trigger_type="y", priority=Priority.HIGH,
                             title="secret", payload={}, suggested_message="m")
        _enqueue(sync_redis, "cust_other", t)

        client = TestClient(app)
        tok = create_token("cust_notif")
        resp = client.get("/v1/notifications",
                          headers={"Authorization": f"Bearer {tok}"})
        # cust_notif sees nothing — the trigger belongs to cust_other
        assert resp.json() == {"notifications": []}
