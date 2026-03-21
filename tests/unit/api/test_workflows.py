"""Tests for GET /v1/workflows endpoint."""
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
from src.integrations.n8n.tracking import TrackedWorkflow, WorkflowTracker

import fakeredis.aioredis


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def tracker(fake_redis):
    return WorkflowTracker(fake_redis)


@pytest.fixture
def mock_ea():
    ea = AsyncMock()
    ea.customer_id = "cust_test"
    ea.handle_customer_interaction = AsyncMock(return_value="reply")
    return ea


@pytest.fixture
def app(mock_ea, fake_redis, tracker):
    factory = MagicMock(return_value=mock_ea)
    return create_app(
        ea_registry=EARegistry(factory=factory, max_size=10),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
        workflow_tracker=tracker,
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


class TestWorkflowsEndpoint:
    def test_returns_empty_when_none(self, client, token):
        resp = client.get(
            "/v1/workflows",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_customer_workflows(self, async_client, token, tracker):
        await tracker.track("cust_test", TrackedWorkflow(
            "w1", "Weekly Report", "active", "2026-03-20T09:00:00Z",
        ))
        await tracker.track("cust_test", TrackedWorkflow(
            "w2", "Invoice Gen", "inactive", "2026-03-20T10:00:00Z",
        ))
        resp = await async_client.get(
            "/v1/workflows",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {w["name"] for w in data}
        assert names == {"Weekly Report", "Invoice Gen"}

    def test_requires_authentication(self, client):
        resp = client.get("/v1/workflows")
        assert resp.status_code in (401, 403)

    async def test_tenant_isolation(self, async_client, token, tracker):
        await tracker.track("cust_other", TrackedWorkflow(
            "w1", "Other's Flow", "active", "2026-01-01",
        ))
        resp = await async_client.get(
            "/v1/workflows",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.json() == []
