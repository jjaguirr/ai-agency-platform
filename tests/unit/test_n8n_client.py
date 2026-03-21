"""
Tests for N8nClient Protocol, HttpN8nClient, and N8nConfig.

Uses httpx.MockTransport for HTTP assertions — no external mocking library.
Uses fakeredis for config persistence tests.
"""
from __future__ import annotations

import json

import httpx
import pytest

from src.integrations.n8n.client import HttpN8nClient, N8nClientError
from src.integrations.n8n.config import N8nConfig


# --- Helpers ----------------------------------------------------------------

def _mock_transport(handler):
    """Build an httpx.AsyncClient with a mock transport."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json_response(data, status_code=200):
    return httpx.Response(status_code, json=data)


# --- N8nConfig --------------------------------------------------------------

class TestN8nConfig:
    def test_construction(self):
        cfg = N8nConfig(base_url="http://n8n:5678", api_key="secret")
        assert cfg.base_url == "http://n8n:5678"
        assert cfg.api_key == "secret"

    @pytest.fixture
    def redis(self):
        import fakeredis.aioredis
        return fakeredis.aioredis.FakeRedis()

    async def test_save_load_roundtrip(self, redis):
        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key123")
        await cfg.save(redis, "cust_a")
        loaded = await N8nConfig.load(redis, "cust_a")
        assert loaded is not None
        assert loaded.base_url == cfg.base_url
        assert loaded.api_key == cfg.api_key

    async def test_load_returns_none_when_absent(self, redis):
        loaded = await N8nConfig.load(redis, "nonexistent")
        assert loaded is None

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("N8N_BASE_URL", "http://localhost:5678")
        monkeypatch.setenv("N8N_API_KEY", "test-key")
        cfg = N8nConfig.from_env()
        assert cfg.base_url == "http://localhost:5678"
        assert cfg.api_key == "test-key"


# --- HttpN8nClient ---------------------------------------------------------

class TestListWorkflows:
    async def test_returns_parsed_response(self):
        workflows = [{"id": "1", "name": "My Flow", "active": True}]

        def handler(request: httpx.Request):
            assert request.url.path == "/api/v1/workflows"
            assert request.headers["X-N8N-API-KEY"] == "key"
            return _json_response({"data": workflows})

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        result = await client.list_workflows()
        assert result == workflows


class TestGetWorkflow:
    async def test_returns_workflow(self):
        wf = {"id": "42", "name": "Report", "nodes": []}

        def handler(request: httpx.Request):
            assert request.url.path == "/api/v1/workflows/42"
            return _json_response(wf)

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        result = await client.get_workflow("42")
        assert result["name"] == "Report"


class TestCreateWorkflow:
    async def test_sends_correct_payload(self):
        definition = {"name": "New Flow", "nodes": [], "connections": {}}

        def handler(request: httpx.Request):
            assert request.method == "POST"
            assert request.url.path == "/api/v1/workflows"
            body = json.loads(request.content)
            assert body["name"] == "New Flow"
            return _json_response({"id": "99", **definition}, status_code=201)

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        result = await client.create_workflow(definition)
        assert result["id"] == "99"


class TestActivateWorkflow:
    async def test_calls_correct_endpoint(self):
        def handler(request: httpx.Request):
            assert request.method == "POST"
            assert request.url.path == "/api/v1/workflows/7/activate"
            return _json_response({"id": "7", "active": True})

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        result = await client.activate_workflow("7")
        assert result["active"] is True


class TestDeactivateWorkflow:
    async def test_calls_correct_endpoint(self):
        def handler(request: httpx.Request):
            assert request.method == "POST"
            assert request.url.path == "/api/v1/workflows/7/deactivate"
            return _json_response({"id": "7", "active": False})

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        result = await client.deactivate_workflow("7")
        assert result["active"] is False


class TestDeleteWorkflow:
    async def test_sends_delete_request(self):
        def handler(request: httpx.Request):
            assert request.method == "DELETE"
            assert request.url.path == "/api/v1/workflows/3"
            return httpx.Response(204)

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        await client.delete_workflow("3")  # should not raise


class TestListExecutions:
    async def test_with_workflow_filter(self):
        executions = [{"id": "e1", "status": "success", "workflowId": "5"}]

        def handler(request: httpx.Request):
            assert request.url.path == "/api/v1/executions"
            assert "workflowId=5" in str(request.url)
            return _json_response({"data": executions})

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        result = await client.list_executions(workflow_id="5")
        assert len(result) == 1

    async def test_without_workflow_filter(self):
        def handler(request: httpx.Request):
            assert "workflowId" not in str(request.url)
            return _json_response({"data": []})

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        result = await client.list_executions()
        assert result == []


class TestErrorHandling:
    async def test_api_error_raises(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, json={"message": "Internal Server Error"})

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        with pytest.raises(N8nClientError, match="500"):
            await client.list_workflows()

    async def test_auth_error_raises(self):
        def handler(request: httpx.Request):
            return httpx.Response(401, json={"message": "Unauthorized"})

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="bad")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        with pytest.raises(N8nClientError, match="401"):
            await client.get_workflow("1")

    async def test_connection_error_raises(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        cfg = N8nConfig(base_url="http://n8n:5678", api_key="key")
        client = HttpN8nClient(cfg, http_client=_mock_transport(handler))
        with pytest.raises(N8nClientError, match="[Cc]onnect"):
            await client.list_workflows()
