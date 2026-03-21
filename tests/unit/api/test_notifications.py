"""Tests for /v1/notifications — GET + lifecycle POSTs.

V2: GET is non-destructive. Customer explicitly marks each notification
read/snoozed/dismissed via POST /v1/notifications/{id}/{action}. This
matches what a dashboard UI actually needs — the old destructive pop
meant refreshing the page lost your inbox.
"""
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


def _notif(nid: str, *, priority: str = "MEDIUM", created_at: str = "2026-03-19T08:00:00+00:00") -> dict:
    return {
        "id": nid, "domain": "ea", "trigger_type": "test",
        "priority": priority, "title": "Test", "message": "Hello",
        "created_at": created_at,
    }


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


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestGetNotifications:
    def test_returns_empty_when_none(self, client, auth):
        resp = client.get("/v1/notifications", headers=auth)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_pending_notifications(self, async_client, auth, store):
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
        resp = await async_client.get("/v1/notifications", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Ordered by priority (HIGH first) then timestamp
        assert data[0]["priority"] == "HIGH"
        assert data[1]["priority"] == "MEDIUM"
        # Status field exposed so the UI can badge snoozed-but-due items.
        assert data[0]["status"] == "pending"

    async def test_get_is_non_destructive(self, async_client, auth, store):
        """Replaces the old test_marks_as_delivered. Refreshing the
        dashboard must not clear your inbox."""
        await store.add_pending_notification("cust_test", _notif("n_1"))
        r1 = await async_client.get("/v1/notifications", headers=auth)
        assert len(r1.json()) == 1
        r2 = await async_client.get("/v1/notifications", headers=auth)
        assert len(r2.json()) == 1

    def test_requires_authentication(self, client):
        resp = client.get("/v1/notifications")
        assert resp.status_code in (401, 403)

    async def test_returns_only_own_notifications(self, async_client, auth, store):
        await store.add_pending_notification("cust_other", _notif("n_1"))
        resp = await async_client.get("/v1/notifications", headers=auth)
        assert resp.json() == []


class TestMarkRead:
    async def test_read_then_excluded_from_get(self, async_client, auth, store):
        await store.add_pending_notification("cust_test", _notif("n_1"))
        r = await async_client.post("/v1/notifications/n_1/read", headers=auth)
        assert r.status_code == 204

        after = await async_client.get("/v1/notifications", headers=auth)
        assert after.json() == []

    async def test_read_nonexistent_is_404(self, async_client, auth):
        r = await async_client.post("/v1/notifications/n_ghost/read", headers=auth)
        assert r.status_code == 404

    async def test_cannot_read_another_customers_notification(
        self, async_client, auth, store,
    ):
        """n_1 belongs to cust_other. cust_test's token must not reach it —
        404, not 403, to avoid leaking existence."""
        await store.add_pending_notification("cust_other", _notif("n_1"))
        r = await async_client.post("/v1/notifications/n_1/read", headers=auth)
        assert r.status_code == 404

        # cust_other still has it.
        now = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
        remaining = await store.list_pending_notifications("cust_other", now=now)
        assert len(remaining) == 1

    def test_read_requires_auth(self, client):
        r = client.post("/v1/notifications/n_1/read")
        assert r.status_code in (401, 403)


class TestSnooze:
    async def test_snooze_hides_from_get(self, async_client, auth, store):
        await store.add_pending_notification("cust_test", _notif("n_1"))
        r = await async_client.post(
            "/v1/notifications/n_1/snooze",
            headers=auth,
            json={"minutes": 120},
        )
        assert r.status_code == 204

        after = await async_client.get("/v1/notifications", headers=auth)
        assert after.json() == []

    async def test_snooze_default_minutes(self, async_client, auth, store):
        """Empty body → 60 minutes. Spec says 'default 1hr'."""
        await store.add_pending_notification("cust_test", _notif("n_1"))
        r = await async_client.post(
            "/v1/notifications/n_1/snooze", headers=auth, json={},
        )
        assert r.status_code == 204

    async def test_snooze_reappears_after_deadline(self, async_client, auth, store):
        """Route records real snooze_until; when that passes the store
        includes it again. Verified via the store since we can't
        fast-forward the route's clock from here."""
        await store.add_pending_notification("cust_test", _notif("n_1"))
        await async_client.post(
            "/v1/notifications/n_1/snooze", headers=auth, json={"minutes": 60},
        )
        # Far in the future → reappears.
        future = datetime(2027, 1, 1, tzinfo=timezone.utc)
        reappeared = await store.list_pending_notifications("cust_test", now=future)
        assert len(reappeared) == 1
        assert reappeared[0]["status"] == "snoozed"

    async def test_snooze_nonexistent_is_404(self, async_client, auth):
        r = await async_client.post(
            "/v1/notifications/n_ghost/snooze", headers=auth, json={"minutes": 60},
        )
        assert r.status_code == 404

    async def test_snooze_rejects_bad_minutes(self, async_client, auth, store):
        await store.add_pending_notification("cust_test", _notif("n_1"))
        for bad in (0, -5, 100_000):
            r = await async_client.post(
                "/v1/notifications/n_1/snooze", headers=auth, json={"minutes": bad},
            )
            assert r.status_code == 422, f"minutes={bad} should be rejected"


class TestDismiss:
    async def test_dismiss_removes_permanently(self, async_client, auth, store):
        await store.add_pending_notification("cust_test", _notif("n_1"))
        r = await async_client.post("/v1/notifications/n_1/dismiss", headers=auth)
        assert r.status_code == 204

        after = await async_client.get("/v1/notifications", headers=auth)
        assert after.json() == []

        # Not coming back — far future check via store.
        future = datetime(2027, 1, 1, tzinfo=timezone.utc)
        assert await store.list_pending_notifications("cust_test", now=future) == []

    async def test_dismiss_nonexistent_is_404(self, async_client, auth):
        r = await async_client.post("/v1/notifications/n_ghost/dismiss", headers=auth)
        assert r.status_code == 404

    async def test_cannot_dismiss_another_customers_notification(
        self, async_client, auth, store,
    ):
        await store.add_pending_notification("cust_other", _notif("n_1"))
        r = await async_client.post("/v1/notifications/n_1/dismiss", headers=auth)
        assert r.status_code == 404

        now = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
        assert len(await store.list_pending_notifications("cust_other", now=now)) == 1

    def test_dismiss_requires_auth(self, client):
        r = client.post("/v1/notifications/n_1/dismiss")
        assert r.status_code in (401, 403)
