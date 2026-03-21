"""
n8n REST API client.

Thin wrapper — same seam pattern as TwilioWhatsAppProvider: the
constructor takes an optional httpx.AsyncClient so tests inject
MockTransport. No n8n SDK dependency.

Every network/HTTP error surfaces as N8nError so callers have one
exception type to catch. 401 gets its own subclass because "your API
key is wrong" warrants a different EA response than "n8n is down."
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class N8nError(Exception):
    """Any failure talking to n8n — transport, timeout, 4xx/5xx."""


class N8nAuthError(N8nError):
    """401 — bad or missing API key."""


class N8nClient:

    def __init__(
        self,
        base_url: str,
        api_key: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._http = http_client or httpx.AsyncClient(timeout=10.0)

    # --- Request helper -----------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self._base}/api/v1{path}"
        headers = {"X-N8N-API-KEY": self._api_key, **kwargs.pop("headers", {})}
        try:
            resp = await self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as e:
            raise N8nError(str(e)) from e

        if resp.status_code == 401:
            raise N8nAuthError("n8n rejected API key (401)")
        if resp.status_code >= 400:
            detail = self._extract_error(resp)
            raise N8nError(f"n8n returned {resp.status_code}: {detail}")

        return resp.json()

    @staticmethod
    def _extract_error(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            return body.get("message", resp.text)
        except Exception:
            return resp.text

    # --- Workflow CRUD ------------------------------------------------------

    async def list_workflows(self) -> List[Dict[str, Any]]:
        body = await self._request("GET", "/workflows")
        return body.get("data", [])

    async def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/workflows/{workflow_id}")

    async def create_workflow(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/workflows", json=definition)

    async def activate_workflow(self, workflow_id: str) -> None:
        await self._request("PATCH", f"/workflows/{workflow_id}",
                            json={"active": True})

    async def deactivate_workflow(self, workflow_id: str) -> None:
        await self._request("PATCH", f"/workflows/{workflow_id}",
                            json={"active": False})

    async def delete_workflow(self, workflow_id: str) -> None:
        await self._request("DELETE", f"/workflows/{workflow_id}")

    async def list_executions(self, workflow_id: str) -> List[Dict[str, Any]]:
        body = await self._request("GET", "/executions",
                                   params={"workflowId": workflow_id})
        return body.get("data", [])

    async def aclose(self) -> None:
        await self._http.aclose()
