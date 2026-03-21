"""
N8nClient — httpx wrapper over n8n's REST API.

Same seam pattern as TwilioWhatsAppProvider: constructor takes an
optional http_client so tests inject MockTransport. No live n8n in
unit tests.

n8n REST reference (public API, /api/v1):
  GET    /workflows
  GET    /workflows/{id}
  POST   /workflows
  PATCH  /workflows/{id}        (activate/deactivate: {"active": bool})
  DELETE /workflows/{id}
  GET    /executions?workflowId={id}
Auth: X-N8N-API-KEY header.
"""
import json

import httpx
import pytest

from src.workflows.client import N8nClient, N8nError, N8nAuthError


BASE = "http://n8n.test"
KEY = "test-api-key"


def _client(handler) -> N8nClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return N8nClient(base_url=BASE, api_key=KEY, http_client=http)


# --- Auth header ------------------------------------------------------------

class TestAuth:
    async def test_api_key_sent_as_header(self):
        captured = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["key"] = req.headers.get("X-N8N-API-KEY")
            return httpx.Response(200, json={"data": []})

        c = _client(handler)
        await c.list_workflows()
        assert captured["key"] == KEY

    async def test_401_raises_auth_error(self):
        def handler(req):
            return httpx.Response(401, json={"message": "Unauthorized"})

        c = _client(handler)
        with pytest.raises(N8nAuthError):
            await c.list_workflows()


# --- list_workflows ---------------------------------------------------------

class TestListWorkflows:
    async def test_returns_list(self):
        def handler(req):
            assert req.method == "GET"
            assert req.url.path == "/api/v1/workflows"
            return httpx.Response(200, json={
                "data": [
                    {"id": "1", "name": "Report", "active": True},
                    {"id": "2", "name": "Sync", "active": False},
                ]
            })

        c = _client(handler)
        result = await c.list_workflows()
        assert len(result) == 2
        assert result[0]["name"] == "Report"

    async def test_empty_list(self):
        def handler(req):
            return httpx.Response(200, json={"data": []})

        c = _client(handler)
        assert await c.list_workflows() == []


# --- get_workflow -----------------------------------------------------------

class TestGetWorkflow:
    async def test_by_id(self):
        def handler(req):
            assert req.url.path == "/api/v1/workflows/abc123"
            return httpx.Response(200, json={
                "id": "abc123", "name": "Report", "active": True, "nodes": []
            })

        c = _client(handler)
        wf = await c.get_workflow("abc123")
        assert wf["id"] == "abc123"

    async def test_404_raises(self):
        def handler(req):
            return httpx.Response(404, json={"message": "not found"})

        c = _client(handler)
        with pytest.raises(N8nError, match="404"):
            await c.get_workflow("nope")


# --- create_workflow --------------------------------------------------------

class TestCreateWorkflow:
    async def test_posts_definition(self):
        captured = {}

        def handler(req: httpx.Request):
            assert req.method == "POST"
            assert req.url.path == "/api/v1/workflows"
            captured["body"] = json.loads(req.content)
            return httpx.Response(200, json={"id": "new_wf", "name": "Created"})

        c = _client(handler)
        definition = {"name": "Created", "nodes": [], "connections": {}}
        result = await c.create_workflow(definition)
        assert result["id"] == "new_wf"
        assert captured["body"]["name"] == "Created"

    async def test_400_raises(self):
        def handler(req):
            return httpx.Response(400, json={"message": "invalid workflow"})

        c = _client(handler)
        with pytest.raises(N8nError, match="invalid workflow"):
            await c.create_workflow({"bad": "data"})


# --- activate / deactivate --------------------------------------------------

class TestActivateDeactivate:
    async def test_activate_patches_active_true(self):
        captured = {}

        def handler(req: httpx.Request):
            assert req.method == "PATCH"
            assert req.url.path == "/api/v1/workflows/wf1"
            captured["body"] = json.loads(req.content)
            return httpx.Response(200, json={"id": "wf1", "active": True})

        c = _client(handler)
        await c.activate_workflow("wf1")
        assert captured["body"] == {"active": True}

    async def test_deactivate_patches_active_false(self):
        captured = {}

        def handler(req: httpx.Request):
            captured["body"] = json.loads(req.content)
            return httpx.Response(200, json={"id": "wf1", "active": False})

        c = _client(handler)
        await c.deactivate_workflow("wf1")
        assert captured["body"] == {"active": False}


# --- delete_workflow --------------------------------------------------------

class TestDeleteWorkflow:
    async def test_delete_by_id(self):
        captured = {}

        def handler(req):
            captured["method"] = req.method
            captured["path"] = req.url.path
            return httpx.Response(200, json={})

        c = _client(handler)
        await c.delete_workflow("doomed")
        assert captured["method"] == "DELETE"
        assert captured["path"] == "/api/v1/workflows/doomed"


# --- list_executions --------------------------------------------------------

class TestListExecutions:
    async def test_filtered_by_workflow_id(self):
        captured = {}

        def handler(req):
            captured["query"] = dict(req.url.params)
            return httpx.Response(200, json={
                "data": [
                    {"id": "ex1", "status": "success", "startedAt": "2026-03-16T09:00:00Z"},
                    {"id": "ex2", "status": "error", "startedAt": "2026-03-09T09:00:00Z"},
                ]
            })

        c = _client(handler)
        runs = await c.list_executions("wf1")
        assert captured["query"]["workflowId"] == "wf1"
        assert len(runs) == 2
        assert runs[0]["status"] == "success"


# --- Failure modes ----------------------------------------------------------

class TestFailures:
    async def test_connection_error_wrapped(self):
        def handler(req):
            raise httpx.ConnectError("refused")

        c = _client(handler)
        with pytest.raises(N8nError, match="refused"):
            await c.list_workflows()

    async def test_timeout_wrapped(self):
        def handler(req):
            raise httpx.TimeoutException("slow")

        c = _client(handler)
        with pytest.raises(N8nError, match="slow"):
            await c.list_workflows()

    async def test_500_raises(self):
        def handler(req):
            return httpx.Response(500, text="internal error")

        c = _client(handler)
        with pytest.raises(N8nError, match="500"):
            await c.list_workflows()

    async def test_default_client_has_timeout(self):
        """Without injected http_client, constructor must set a timeout —
        no unbounded waits in production."""
        c = N8nClient(base_url=BASE, api_key=KEY)
        assert c._http.timeout.connect is not None
        assert c._http.timeout.read is not None

    async def test_base_url_trailing_slash_normalized(self):
        """http://n8n.test/ and http://n8n.test both work."""
        captured = {}

        def handler(req):
            captured["url"] = str(req.url)
            return httpx.Response(200, json={"data": []})

        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(transport=transport)
        c = N8nClient(base_url="http://n8n.test/", api_key=KEY, http_client=http)
        await c.list_workflows()
        assert "//" not in captured["url"].replace("http://", "")
