"""Tests for WorkflowHealthBehavior — n8n execution failure detection."""
import pytest
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis

from src.proactive.workflow_health import WorkflowHealthBehavior
from src.proactive.triggers import Priority
from src.workflows.store import WorkflowStore


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def wf_store(fake_redis):
    return WorkflowStore(fake_redis)


CID = "cust_wf_test"


def _mock_n8n_client(executions_by_workflow=None):
    """Build a mock N8nClient with canned execution responses."""
    client = AsyncMock()

    async def _list_executions(wf_id):
        if executions_by_workflow and wf_id in executions_by_workflow:
            return executions_by_workflow[wf_id]
        return []

    client.list_executions = AsyncMock(side_effect=_list_executions)
    return client


class TestWorkflowHealthBehavior:
    async def test_no_workflows_returns_empty(self, wf_store):
        behavior = WorkflowHealthBehavior(wf_store)
        result = await behavior.check(CID)
        assert result == []

    async def test_no_n8n_config_returns_empty(self, wf_store):
        # Add workflow but no config
        await wf_store.add_workflow(CID, "wf_1", "Weekly Report", "active")
        behavior = WorkflowHealthBehavior(wf_store)
        result = await behavior.check(CID)
        assert result == []

    async def test_all_successful_returns_empty(self, wf_store):
        await wf_store.set_config(CID, base_url="http://n8n:5678", api_key="key")
        await wf_store.add_workflow(CID, "wf_1", "Weekly Report", "active")
        mock_client = _mock_n8n_client({
            "wf_1": [{"id": "exec_1", "status": "success", "finished": True}],
        })
        behavior = WorkflowHealthBehavior(wf_store, n8n_client_factory=lambda *a: mock_client)
        result = await behavior.check(CID)
        assert result == []

    async def test_failed_execution_triggers(self, wf_store):
        await wf_store.set_config(CID, base_url="http://n8n:5678", api_key="key")
        await wf_store.add_workflow(CID, "wf_1", "Weekly Report", "active")
        mock_client = _mock_n8n_client({
            "wf_1": [{"id": "exec_1", "status": "error", "finished": True}],
        })
        behavior = WorkflowHealthBehavior(wf_store, n8n_client_factory=lambda *a: mock_client)
        result = await behavior.check(CID)
        assert len(result) == 1
        assert result[0].trigger_type == "workflow_failure"
        assert result[0].priority == Priority.HIGH
        assert result[0].domain == "workflows"

    async def test_trigger_payload_includes_workflow_name(self, wf_store):
        await wf_store.set_config(CID, base_url="http://n8n:5678", api_key="key")
        await wf_store.add_workflow(CID, "wf_1", "Weekly Report", "active")
        mock_client = _mock_n8n_client({
            "wf_1": [{"id": "exec_42", "status": "error", "finished": True}],
        })
        behavior = WorkflowHealthBehavior(wf_store, n8n_client_factory=lambda *a: mock_client)
        result = await behavior.check(CID)
        assert result[0].payload["workflow_name"] == "Weekly Report"
        assert result[0].payload["workflow_id"] == "wf_1"
        assert result[0].payload["execution_id"] == "exec_42"

    async def test_cooldown_key_per_workflow(self, wf_store):
        await wf_store.set_config(CID, base_url="http://n8n:5678", api_key="key")
        await wf_store.add_workflow(CID, "wf_1", "Report A", "active")
        mock_client = _mock_n8n_client({
            "wf_1": [{"id": "exec_1", "status": "error", "finished": True}],
        })
        behavior = WorkflowHealthBehavior(wf_store, n8n_client_factory=lambda *a: mock_client)
        result = await behavior.check(CID)
        assert "wf_1" in result[0].cooldown_key

    async def test_multiple_failed_workflows(self, wf_store):
        await wf_store.set_config(CID, base_url="http://n8n:5678", api_key="key")
        await wf_store.add_workflow(CID, "wf_1", "Report A", "active")
        await wf_store.add_workflow(CID, "wf_2", "Report B", "active")
        mock_client = _mock_n8n_client({
            "wf_1": [{"id": "exec_1", "status": "error", "finished": True}],
            "wf_2": [{"id": "exec_2", "status": "crashed", "finished": True}],
        })
        behavior = WorkflowHealthBehavior(wf_store, n8n_client_factory=lambda *a: mock_client)
        result = await behavior.check(CID)
        assert len(result) == 2

    async def test_n8n_client_error_does_not_crash(self, wf_store):
        await wf_store.set_config(CID, base_url="http://n8n:5678", api_key="key")
        await wf_store.add_workflow(CID, "wf_1", "Report A", "active")
        mock_client = AsyncMock()
        mock_client.list_executions = AsyncMock(side_effect=RuntimeError("connection refused"))
        behavior = WorkflowHealthBehavior(wf_store, n8n_client_factory=lambda *a: mock_client)
        result = await behavior.check(CID)
        assert result == []
