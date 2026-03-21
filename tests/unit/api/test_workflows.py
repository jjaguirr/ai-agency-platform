"""
GET /v1/workflows — tenant-scoped list of deployed automations.

Auth via the same JWT bearer as the rest of /v1. The customer_id claim
determines which WorkflowStore namespace is read. Cross-tenant reads
are impossible by construction: there's no query param for customer_id.
"""
import os

import fakeredis.aioredis
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry
from src.workflows.store import WorkflowStore


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return WorkflowStore(fake_redis)


@pytest.fixture
def app(fake_redis, store):
    factory = MagicMock(return_value=AsyncMock())
    a = create_app(
        ea_registry=EARegistry(factory=factory, max_size=10),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
    )
    # Routes pull store from app.state — same pattern as proactive_state_store
    a.state.workflow_store = store
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def token_a():
    return create_token("cust_a")


@pytest.fixture
def token_b():
    return create_token("cust_b")


class TestWorkflowsEndpoint:
    def test_requires_auth(self, client):
        resp = client.get("/v1/workflows")
        assert resp.status_code == 401

    def test_empty_list(self, client, token_a):
        resp = client.get("/v1/workflows",
                          headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_customer_workflows(self, client, store, token_a):
        await store.add_workflow("cust_a", "wf1", "Monday Report", "active")
        await store.add_workflow("cust_a", "wf2", "Invoice Sync", "inactive")
        resp = client.get("/v1/workflows",
                          headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        names = {w["name"] for w in body}
        assert names == {"Monday Report", "Invoice Sync"}

    async def test_response_schema(self, client, store, token_a):
        await store.add_workflow("cust_a", "wf1", "Report", "active")
        resp = client.get("/v1/workflows",
                          headers={"Authorization": f"Bearer {token_a}"})
        item = resp.json()[0]
        assert set(item.keys()) >= {"workflow_id", "name", "status", "created_at"}

    async def test_tenant_scoped(self, client, store, token_a, token_b):
        await store.add_workflow("cust_a", "wf_a", "A's Report", "active")
        await store.add_workflow("cust_b", "wf_b", "B's Sync", "active")

        resp_a = client.get("/v1/workflows",
                            headers={"Authorization": f"Bearer {token_a}"})
        resp_b = client.get("/v1/workflows",
                            headers={"Authorization": f"Bearer {token_b}"})

        assert {w["workflow_id"] for w in resp_a.json()} == {"wf_a"}
        assert {w["workflow_id"] for w in resp_b.json()} == {"wf_b"}

    def test_invalid_token_401(self, client):
        resp = client.get("/v1/workflows",
                          headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401
