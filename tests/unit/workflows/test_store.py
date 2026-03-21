"""
WorkflowStore — Redis-backed tracking of customer→workflow ownership.

Key pattern follows ProactiveStateStore convention:
  n8n:{customer_id}:config     → hash {base_url, api_key}
  n8n:{customer_id}:workflows  → hash {workflow_id → json(name, status, created_at)}

Tenant scoping is the critical property: customer A must never see
customer B's workflows, even by wildcard.
"""
import json

import fakeredis.aioredis
import pytest

from src.workflows.store import WorkflowStore


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(redis):
    return WorkflowStore(redis)


# --- Config -----------------------------------------------------------------

class TestConfig:
    async def test_get_config_unset_returns_none(self, store):
        assert await store.get_config("cust_a") is None

    async def test_set_and_get_config(self, store):
        await store.set_config("cust_a", base_url="http://n8n.a", api_key="key_a")
        cfg = await store.get_config("cust_a")
        assert cfg == {"base_url": "http://n8n.a", "api_key": "key_a"}

    async def test_config_is_customer_scoped(self, store):
        await store.set_config("cust_a", base_url="http://n8n.a", api_key="key_a")
        await store.set_config("cust_b", base_url="http://n8n.b", api_key="key_b")
        a = await store.get_config("cust_a")
        b = await store.get_config("cust_b")
        assert a["base_url"] == "http://n8n.a"
        assert b["base_url"] == "http://n8n.b"


# --- Workflow tracking ------------------------------------------------------

class TestWorkflowTracking:
    async def test_add_and_list(self, store):
        await store.add_workflow("cust_a", workflow_id="wf1",
                                 name="Monday Report", status="active")
        wfs = await store.list_workflows("cust_a")
        assert len(wfs) == 1
        assert wfs[0]["workflow_id"] == "wf1"
        assert wfs[0]["name"] == "Monday Report"
        assert wfs[0]["status"] == "active"
        assert "created_at" in wfs[0]

    async def test_list_empty(self, store):
        assert await store.list_workflows("cust_a") == []

    async def test_multiple_workflows(self, store):
        await store.add_workflow("cust_a", "wf1", "Report", "active")
        await store.add_workflow("cust_a", "wf2", "Sync", "inactive")
        wfs = await store.list_workflows("cust_a")
        ids = {w["workflow_id"] for w in wfs}
        assert ids == {"wf1", "wf2"}

    async def test_update_status(self, store):
        await store.add_workflow("cust_a", "wf1", "Report", "active")
        await store.update_status("cust_a", "wf1", "inactive")
        wfs = await store.list_workflows("cust_a")
        assert wfs[0]["status"] == "inactive"

    async def test_remove_workflow(self, store):
        await store.add_workflow("cust_a", "wf1", "Report", "active")
        await store.remove_workflow("cust_a", "wf1")
        assert await store.list_workflows("cust_a") == []

    async def test_get_by_id(self, store):
        await store.add_workflow("cust_a", "wf1", "Report", "active")
        wf = await store.get_workflow("cust_a", "wf1")
        assert wf["name"] == "Report"

    async def test_get_unknown_returns_none(self, store):
        assert await store.get_workflow("cust_a", "nope") is None


# --- Tenant isolation -------------------------------------------------------

class TestTenantIsolation:
    async def test_customer_a_cannot_see_b(self, store):
        await store.add_workflow("cust_a", "wf_a", "A's Report", "active")
        await store.add_workflow("cust_b", "wf_b", "B's Sync", "active")
        a_wfs = await store.list_workflows("cust_a")
        b_wfs = await store.list_workflows("cust_b")
        assert {w["workflow_id"] for w in a_wfs} == {"wf_a"}
        assert {w["workflow_id"] for w in b_wfs} == {"wf_b"}

    async def test_remove_is_scoped(self, store):
        """Removing cust_a's wf1 leaves cust_b's wf1 intact — even with
        the same workflow_id (different n8n instances can collide)."""
        await store.add_workflow("cust_a", "wf1", "A", "active")
        await store.add_workflow("cust_b", "wf1", "B", "active")
        await store.remove_workflow("cust_a", "wf1")
        assert await store.list_workflows("cust_a") == []
        b_wfs = await store.list_workflows("cust_b")
        assert len(b_wfs) == 1
        assert b_wfs[0]["name"] == "B"

    async def test_update_status_is_scoped(self, store):
        await store.add_workflow("cust_a", "wf1", "A", "active")
        await store.add_workflow("cust_b", "wf1", "B", "active")
        await store.update_status("cust_a", "wf1", "inactive")
        b_wfs = await store.list_workflows("cust_b")
        assert b_wfs[0]["status"] == "active"

    async def test_redis_keys_include_customer_id(self, store, redis):
        """Whitebox: key format is n8n:{customer_id}:workflows — GDPR
        deletion pipeline relies on being able to wildcard by customer."""
        await store.add_workflow("cust_a", "wf1", "X", "active")
        keys = await redis.keys("n8n:cust_a:*")
        assert len(keys) > 0
        other = await redis.keys("n8n:cust_b:*")
        assert other == []


# --- Find by name (conversational lookup) -----------------------------------

class TestFindByName:
    """'Pause my Monday reports' → need to find workflow by fuzzy name."""

    async def test_exact_match(self, store):
        await store.add_workflow("cust_a", "wf1", "Monday Report", "active")
        found = await store.find_by_name("cust_a", "Monday Report")
        assert found is not None
        assert found["workflow_id"] == "wf1"

    async def test_case_insensitive(self, store):
        await store.add_workflow("cust_a", "wf1", "Monday Report", "active")
        found = await store.find_by_name("cust_a", "monday report")
        assert found["workflow_id"] == "wf1"

    async def test_partial_match(self, store):
        """'my Monday reports' → match 'Monday Report'."""
        await store.add_workflow("cust_a", "wf1", "Monday Report", "active")
        await store.add_workflow("cust_a", "wf2", "Invoice Tracker", "active")
        found = await store.find_by_name("cust_a", "monday")
        assert found["workflow_id"] == "wf1"

    async def test_no_match_returns_none(self, store):
        await store.add_workflow("cust_a", "wf1", "Monday Report", "active")
        assert await store.find_by_name("cust_a", "tuesday") is None

    async def test_scoped_to_customer(self, store):
        await store.add_workflow("cust_b", "wf_b", "Monday Report", "active")
        assert await store.find_by_name("cust_a", "monday") is None
