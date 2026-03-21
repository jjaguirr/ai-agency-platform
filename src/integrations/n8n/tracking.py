"""
Redis-backed workflow tracker: per-customer workflow ownership.

Key pattern: ``customer_workflows:{customer_id}`` (Redis hash).
Field = workflow_id, value = JSON-serialized TrackedWorkflow.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


def _key(customer_id: str) -> str:
    return f"customer_workflows:{customer_id}"


@dataclass
class TrackedWorkflow:
    workflow_id: str
    name: str
    status: str  # "active", "inactive", "deleted"
    created_at: str  # ISO timestamp

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str | bytes) -> "TrackedWorkflow":
        data = json.loads(raw if isinstance(raw, str) else raw.decode())
        return cls(**data)


class WorkflowTracker:
    def __init__(self, redis_client: Any) -> None:
        self._r = redis_client

    async def track(self, customer_id: str, workflow: TrackedWorkflow) -> None:
        await self._r.hset(
            _key(customer_id), workflow.workflow_id, workflow.to_json(),
        )

    async def list_workflows(self, customer_id: str) -> list[TrackedWorkflow]:
        raw = await self._r.hgetall(_key(customer_id))
        if not raw:
            return []
        return [TrackedWorkflow.from_json(v) for v in raw.values()]

    async def update_status(
        self, customer_id: str, workflow_id: str, status: str,
    ) -> None:
        raw = await self._r.hget(_key(customer_id), workflow_id)
        if raw is None:
            return
        wf = TrackedWorkflow.from_json(raw)
        wf.status = status
        await self._r.hset(_key(customer_id), workflow_id, wf.to_json())

    async def remove(self, customer_id: str, workflow_id: str) -> None:
        await self._r.hdel(_key(customer_id), workflow_id)

    async def find_by_name(
        self, customer_id: str, query: str,
    ) -> list[TrackedWorkflow]:
        all_wfs = await self.list_workflows(customer_id)
        q = query.lower()
        return [wf for wf in all_wfs if q in wf.name.lower()]
