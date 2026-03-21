"""Workflow health behavior — detects failed n8n workflow executions.

Runs as part of the heartbeat cycle. For each customer with n8n connected,
checks each tracked workflow's latest execution status. Generates a HIGH
priority trigger for failures so the customer is notified proactively.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .triggers import Priority, ProactiveTrigger

logger = logging.getLogger(__name__)

_FAILURE_STATUSES = {"error", "crashed"}


def _default_n8n_client_factory(base_url: str, api_key: str):
    from src.workflows.client import N8nClient
    return N8nClient(base_url, api_key)


class WorkflowHealthBehavior:

    def __init__(
        self,
        workflow_store,
        *,
        n8n_client_factory: Optional[Callable] = None,
    ) -> None:
        self._store = workflow_store
        self._client_factory = n8n_client_factory or _default_n8n_client_factory

    async def check(self, customer_id: str) -> List[ProactiveTrigger]:
        config = await self._store.get_config(customer_id)
        if config is None:
            return []

        workflows = await self._store.list_workflows(customer_id)
        if not workflows:
            return []

        client = self._client_factory(config["base_url"], config["api_key"])
        triggers: List[ProactiveTrigger] = []

        for wf in workflows:
            wf_id = wf["workflow_id"]
            wf_name = wf.get("name", wf_id)
            try:
                executions = await client.list_executions(wf_id)
            except Exception:
                logger.warning(
                    "Failed to list executions for workflow=%s customer=%s",
                    wf_id, customer_id,
                )
                continue

            if not executions:
                continue

            latest = executions[0]
            status = latest.get("status", "")
            if status in _FAILURE_STATUSES:
                triggers.append(ProactiveTrigger(
                    domain="workflows",
                    trigger_type="workflow_failure",
                    priority=Priority.HIGH,
                    title=f"Workflow failed: {wf_name}",
                    payload={
                        "workflow_id": wf_id,
                        "workflow_name": wf_name,
                        "execution_id": latest.get("id", ""),
                        "status": status,
                    },
                    suggested_message=(
                        f"Your \"{wf_name}\" workflow failed to run — "
                        f"want me to check what went wrong?"
                    ),
                    cooldown_key=f"workflow:failure:{wf_id}",
                ))

        return triggers
