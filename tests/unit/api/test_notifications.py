"""Tests for GET /v1/notifications endpoint."""
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
        assert resp.status_code == 401

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


class TestNotificationsPeek:
    async def test_peek_returns_notifications(self, async_client, token, store):
        await store.add_pending_notification("cust_test", {
            "id": "n_1", "domain": "ea", "trigger_type": "briefing",
            "priority": "MEDIUM", "title": "Morning Briefing",
            "message": "Good morning!", "created_at": "2026-03-19T08:00:00+00:00",
        })
        resp = await async_client.get(
            "/v1/notifications/peek",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["id"] == "n_1"

    async def test_peek_does_not_consume(self, async_client, token, store):
        await store.add_pending_notification("cust_test", {
            "id": "n_1", "domain": "ea", "trigger_type": "test",
            "priority": "LOW", "title": "Test",
            "message": "Hello", "created_at": "2026-03-19T08:00:00+00:00",
        })
        # Peek twice — both should return identical data
        resp1 = await async_client.get(
            "/v1/notifications/peek",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp2 = await async_client.get(
            "/v1/notifications/peek",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.json() == resp2.json()
        assert resp1.json()[0]["id"] == "n_1"
        assert resp1.json()[0]["title"] == "Test"

    async def test_peek_then_pop(self, async_client, token, store):
        await store.add_pending_notification("cust_test", {
            "id": "n_1", "domain": "ea", "trigger_type": "test",
            "priority": "LOW", "title": "Test",
            "message": "Hello", "created_at": "2026-03-19T08:00:00+00:00",
        })
        # Peek should show it
        peek_resp = await async_client.get(
            "/v1/notifications/peek",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(peek_resp.json()) == 1

        # Pop should consume it
        pop_resp = await async_client.get(
            "/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(pop_resp.json()) == 1

        # Peek should now be empty
        peek_after = await async_client.get(
            "/v1/notifications/peek",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert peek_after.json() == []

    async def test_peek_empty(self, async_client, token):
        resp = await async_client.get(
            "/v1/notifications/peek",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_peek_requires_auth(self, client):
        resp = client.get("/v1/notifications/peek")
        assert resp.status_code == 401
