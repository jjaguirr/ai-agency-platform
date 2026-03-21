"""
N8n REST API client.

Protocol + concrete httpx implementation. Specialists depend on the Protocol;
tests inject a stub that conforms by shape (structural typing).
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from .config import N8nConfig

logger = logging.getLogger(__name__)


class N8nClientError(Exception):
    """Raised when an n8n API call fails."""


@runtime_checkable
class N8nClient(Protocol):
    async def list_workflows(self) -> list[dict[str, Any]]: ...
    async def get_workflow(self, workflow_id: str) -> dict[str, Any]: ...
    async def create_workflow(self, definition: dict[str, Any]) -> dict[str, Any]: ...
    async def activate_workflow(self, workflow_id: str) -> dict[str, Any]: ...
    async def deactivate_workflow(self, workflow_id: str) -> dict[str, Any]: ...
    async def delete_workflow(self, workflow_id: str) -> None: ...
    async def list_executions(
        self, workflow_id: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]: ...


class HttpN8nClient:
    """Concrete N8n client backed by httpx."""

    def __init__(
        self,
        config: N8nConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base = config.base_url.rstrip("/")
        self._headers = {"X-N8N-API-KEY": config.api_key}
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    async def _request(
        self, method: str, path: str, **kwargs: Any,
    ) -> httpx.Response:
        try:
            resp = await self._http.request(
                method, self._url(path), headers=self._headers, **kwargs,
            )
        except httpx.HTTPError as exc:
            raise N8nClientError(str(exc)) from exc
        if resp.status_code >= 400:
            detail = resp.text[:200]
            raise N8nClientError(
                f"n8n API error {resp.status_code}: {detail}"
            )
        return resp

    async def list_workflows(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/api/v1/workflows")
        return resp.json().get("data", [])

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/api/v1/workflows/{workflow_id}")
        return resp.json()

    async def create_workflow(self, definition: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("POST", "/api/v1/workflows", json=definition)
        return resp.json()

    async def activate_workflow(self, workflow_id: str) -> dict[str, Any]:
        resp = await self._request("POST", f"/api/v1/workflows/{workflow_id}/activate")
        return resp.json()

    async def deactivate_workflow(self, workflow_id: str) -> dict[str, Any]:
        resp = await self._request("POST", f"/api/v1/workflows/{workflow_id}/deactivate")
        return resp.json()

    async def delete_workflow(self, workflow_id: str) -> None:
        await self._request("DELETE", f"/api/v1/workflows/{workflow_id}")

    async def list_executions(
        self, workflow_id: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if workflow_id is not None:
            params["workflowId"] = workflow_id
        resp = await self._request("GET", "/api/v1/executions", params=params)
        return resp.json().get("data", [])
