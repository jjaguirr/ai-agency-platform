"""
GET /v1/notifications — pull model for proactive messages.

Customers without WhatsApp (or when WhatsApp delivery fails) retrieve
proactive messages via this endpoint. Each GET drains the queue — once
retrieved, notifications are marked delivered and won't be returned again.

Ordered by priority DESC, then created_at ASC. Tenant-isolated.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


@pytest.fixture
def fake_redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def app(fake_redis, mock_ea):
    return create_app(
        ea_registry=EARegistry(factory=lambda cid: mock_ea),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
    )


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {create_token('cust_notif')}"}


@pytest.fixture
def state_store(fake_redis):
    from src.agents.proactive.state import ProactiveStateStore
    return ProactiveStateStore(redis=fake_redis)


class TestNotificationsEndpoint:
    @pytest.mark.asyncio
    async def test_empty_queue_returns_empty_list(self, app, auth_headers):
        client = TestClient(app)
        resp = client.get("/v1/notifications", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"notifications": []}

    @pytest.mark.asyncio
    async def test_returns_pending_and_drains(self, app, auth_headers, state_store):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        t = ProactiveTrigger(
            domain="ea", trigger_type="briefing", priority=Priority.MEDIUM,
            title="Morning", payload={"n_items": 2},
            suggested_message="Good morning — 2 items today.",
            created_at=datetime(2026, 3, 18, 8, 0, tzinfo=ZoneInfo("UTC")),
        )
        await state_store.enqueue_notification("cust_notif", t)

        client = TestClient(app)
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

    @pytest.mark.asyncio
    async def test_ordered_by_priority_then_timestamp(self, app, auth_headers, state_store):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        base = datetime(2026, 3, 18, 8, 0, tzinfo=ZoneInfo("UTC"))

        for i, (prio, dt) in enumerate([
            (Priority.MEDIUM, base + timedelta(minutes=10)),
            (Priority.URGENT, base + timedelta(minutes=20)),
            (Priority.MEDIUM, base),
        ]):
            t = ProactiveTrigger(
                domain="x", trigger_type="y", priority=prio,
                title=f"t{i}", payload={}, suggested_message="m",
                created_at=dt,
            )
            await state_store.enqueue_notification("cust_notif", t)

        client = TestClient(app)
        resp = client.get("/v1/notifications", headers=auth_headers)
        titles = [n["title"] for n in resp.json()["notifications"]]
        # urgent first, then medium by timestamp ascending (t2 older than t0)
        assert titles == ["t1", "t2", "t0"]

    def test_requires_auth(self, app):
        client = TestClient(app)
        resp = client.get("/v1/notifications")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, app, state_store):
        from src.agents.proactive.triggers import Priority, ProactiveTrigger
        t = ProactiveTrigger(domain="x", trigger_type="y", priority=Priority.HIGH,
                             title="secret", payload={}, suggested_message="m")
        await state_store.enqueue_notification("cust_other", t)

        client = TestClient(app)
        tok = create_token("cust_notif")
        resp = client.get("/v1/notifications",
                          headers={"Authorization": f"Bearer {tok}"})
        # cust_notif sees nothing — the trigger belongs to cust_other
        assert resp.json() == {"notifications": []}
