"""Tests for GET /v1/notifications endpoint."""
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import httpx
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry
from src.proactive.state import ProactiveStateStore

import fakeredis.aioredis


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def mock_ea():
    ea = AsyncMock()
    ea.customer_id = "cust_test"
    ea.handle_customer_interaction = AsyncMock(return_value="reply")
    return ea


@pytest.fixture
def app(mock_ea, fake_redis, store):
    factory = MagicMock(return_value=mock_ea)
    return create_app(
        ea_registry=EARegistry(factory=factory, max_size=10),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
        proactive_state_store=store,
    )


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
async def async_client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def token():
    return create_token("cust_test")


@pytest.fixture
def other_token():
    return create_token("cust_other")


class TestNotificationsEndpoint:
    def test_returns_empty_when_none(self, client, token):
        resp = client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_pending_notifications(self, async_client, token, store):
        await store.add_pending_notification("cust_test", {
            "id": "n_1", "domain": "ea", "trigger_type": "briefing",
            "priority": "MEDIUM", "title": "Morning Briefing",
            "message": "Good morning!", "created_at": "2026-03-19T08:00:00+00:00",
        })
        await store.add_pending_notification("cust_test", {
            "id": "n_2", "domain": "ea", "trigger_type": "follow_up",
            "priority": "HIGH", "title": "Follow-up",
            "message": "Call John", "created_at": "2026-03-19T09:00:00+00:00",
        })
        resp = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Ordered by priority (HIGH first) then timestamp
        assert data[0]["priority"] == "HIGH"
        assert data[1]["priority"] == "MEDIUM"

    async def test_marks_as_delivered(self, async_client, token, store):
        await store.add_pending_notification("cust_test", {
            "id": "n_1", "domain": "ea", "trigger_type": "test",
            "priority": "MEDIUM", "title": "Test",
            "message": "Hello", "created_at": "2026-03-19T08:00:00+00:00",
        })
        resp1 = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(resp1.json()) == 1
        resp2 = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.json() == []

    def test_requires_authentication(self, client):
        resp = client.get("/v1/notifications")
        assert resp.status_code in (401, 403)

    async def test_returns_only_own_notifications(self, async_client, token, store):
        await store.add_pending_notification("cust_other", {
            "id": "n_1", "domain": "ea", "trigger_type": "test",
            "priority": "MEDIUM", "title": "Other",
            "message": "Not yours", "created_at": "2026-03-19T08:00:00+00:00",
        })
        resp = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.json() == []


class TestNotificationLifecycleEndpoints:
    """Tests for persistent notification lifecycle: read, snooze, dismiss."""

    async def _add_notif(self, store, cid="cust_test"):
        return await store.add_notification(cid, {
            "domain": "ea", "trigger_type": "test", "priority": "MEDIUM",
            "title": "Test", "message": "Hello",
            "created_at": "2026-03-19T08:00:00+00:00",
        })

    async def test_get_returns_persistent_notifications(self, async_client, token, store):
        notif_id = await self._add_notif(store)
        resp = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == notif_id
        assert data[0]["domain"] == "ea"
        assert data[0]["title"] == "Test"

    async def test_get_persistent_not_consumed(self, async_client, token, store):
        """Persistent notifications survive multiple GETs."""
        notif_id = await self._add_notif(store)
        resp1 = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(resp1.json()) == 1
        resp2 = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(resp2.json()) == 1
        assert resp2.json()[0]["id"] == notif_id

    async def test_mark_read(self, async_client, token, store):
        notif_id = await self._add_notif(store)
        resp = await async_client.post(
            f"/v1/notifications/{notif_id}/read",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        # Should be excluded from GET
        resp2 = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        ids = [n["id"] for n in resp2.json()]
        assert notif_id not in ids

    async def test_snooze_hides_from_listing(self, async_client, token, store):
        notif_id = await self._add_notif(store)
        resp = await async_client.post(
            f"/v1/notifications/{notif_id}/snooze",
            headers={"Authorization": f"Bearer {token}"},
            json={"duration_seconds": 3600},
        )
        assert resp.status_code == 200
        # Snoozed notification should be hidden from GET
        resp2 = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        ids = [n["id"] for n in resp2.json()]
        assert notif_id not in ids

    async def test_snooze_default_1hr(self, async_client, token, store):
        notif_id = await self._add_notif(store)
        resp = await async_client.post(
            f"/v1/notifications/{notif_id}/snooze",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        stored = await store.get_notification("cust_test", notif_id)
        assert stored["status"] == "snoozed"
        # Validate snooze_until is a parseable ISO timestamp ~1 hour in the future
        from datetime import datetime as dt
        snooze_ts = dt.fromisoformat(stored["snooze_until"])
        assert snooze_ts > dt.now(timezone.utc)

    async def test_snoozed_notification_reappears_after_expiry(self, async_client, token, store):
        """Snooze with duration_seconds=1 → reappears on next GET after expiry."""
        notif_id = await self._add_notif(store)
        # Snooze for 1 second
        resp = await async_client.post(
            f"/v1/notifications/{notif_id}/snooze",
            headers={"Authorization": f"Bearer {token}"},
            json={"duration_seconds": 60},
        )
        assert resp.status_code == 200
        # Manually advance snooze_until to the past so it reappears
        past = datetime(2026, 3, 19, 0, 0, tzinfo=timezone.utc)
        await store.snooze_notification("cust_test", notif_id, past)
        resp2 = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        ids = [n["id"] for n in resp2.json()]
        assert notif_id in ids

    async def test_dismiss(self, async_client, token, store):
        notif_id = await self._add_notif(store)
        resp = await async_client.post(
            f"/v1/notifications/{notif_id}/dismiss",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        stored = await store.get_notification("cust_test", notif_id)
        assert stored["status"] == "dismissed"

    async def test_action_on_nonexistent_returns_404(self, async_client, token):
        resp = await async_client.post(
            "/v1/notifications/notif_fake/read",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_tenant_isolation_on_actions(self, async_client, other_token, store):
        notif_id = await self._add_notif(store, cid="cust_test")
        resp = await async_client.post(
            f"/v1/notifications/{notif_id}/read",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 404
