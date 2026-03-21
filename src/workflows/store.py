"""
Redis-backed workflow ownership tracking.

Key pattern follows ProactiveStateStore (src/proactive/state.py):
  n8n:{customer_id}:config     → hash {base_url, api_key}
  n8n:{customer_id}:workflows  → hash {workflow_id → json(record)}

The customer_id is baked into every key, so there is no API surface
that can read across tenants. GDPR deletion wildcards on n8n:{cid}:*.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _key(customer_id: str, *parts: str) -> str:
    return ":".join(["n8n", customer_id, *parts])


class WorkflowStore:

    def __init__(self, redis_client) -> None:
        self._r = redis_client

    # --- Config -------------------------------------------------------------

    async def get_config(self, customer_id: str) -> Optional[Dict[str, str]]:
        raw = await self._r.hgetall(_key(customer_id, "config"))
        if not raw:
            return None
        return {
            (k.decode() if isinstance(k, bytes) else k):
            (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }

    async def set_config(self, customer_id: str, *, base_url: str, api_key: str) -> None:
        await self._r.hset(
            _key(customer_id, "config"),
            mapping={"base_url": base_url, "api_key": api_key},
        )

    # --- Workflow tracking --------------------------------------------------

    async def add_workflow(
        self, customer_id: str, workflow_id: str, name: str, status: str
    ) -> None:
        record = {
            "workflow_id": workflow_id,
            "name": name,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._r.hset(
            _key(customer_id, "workflows"), workflow_id, json.dumps(record)
        )

    async def list_workflows(self, customer_id: str) -> List[Dict[str, Any]]:
        raw = await self._r.hgetall(_key(customer_id, "workflows"))
        out = []
        for v in raw.values():
            decoded = v.decode() if isinstance(v, bytes) else v
            out.append(json.loads(decoded))
        return out

    async def get_workflow(
        self, customer_id: str, workflow_id: str
    ) -> Optional[Dict[str, Any]]:
        raw = await self._r.hget(_key(customer_id, "workflows"), workflow_id)
        if raw is None:
            return None
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        return json.loads(decoded)

    async def update_status(
        self, customer_id: str, workflow_id: str, status: str
    ) -> None:
        record = await self.get_workflow(customer_id, workflow_id)
        if record is None:
            return
        record["status"] = status
        await self._r.hset(
            _key(customer_id, "workflows"), workflow_id, json.dumps(record)
        )

    async def remove_workflow(self, customer_id: str, workflow_id: str) -> None:
        await self._r.hdel(_key(customer_id, "workflows"), workflow_id)

    # --- Conversational lookup ----------------------------------------------

    async def find_by_name(
        self, customer_id: str, name_hint: str
    ) -> Optional[Dict[str, Any]]:
        """Fuzzy: exact match → substring → token overlap. Scoped to one
        customer's workflows so the search space is tiny (tens, not
        thousands)."""
        wfs = await self.list_workflows(customer_id)
        if not wfs:
            return None

        hint = name_hint.lower().strip()

        for wf in wfs:
            if wf["name"].lower() == hint:
                return wf

        for wf in wfs:
            name_lower = wf["name"].lower()
            if hint in name_lower or name_lower in hint:
                return wf

        hint_tokens = set(hint.split())
        best, best_score = None, 0
        for wf in wfs:
            name_tokens = set(wf["name"].lower().split())
            score = len(hint_tokens & name_tokens)
            if score > best_score:
                best, best_score = wf, score

        return best if best_score > 0 else None
