"""Workflow failure detection — poll n8n execution status per heartbeat tick.

Kept out of behaviors.py because it transitively imports httpx via
N8nClient. The other behaviors are dependency-light; this one isn't.

Client construction is deferred to a factory because each customer has
their own n8n instance (base_url + api_key in WorkflowStore). The
behavior can't hold a single client — it builds one per customer per
tick and closes it when done.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Protocol

from src.workflows.client import N8nError
from src.workflows.store import WorkflowStore
from .state import ProactiveStateStore
from .triggers import Priority, ProactiveTrigger

logger = logging.getLogger(__name__)

_FAILURE_STATUSES = frozenset({"error", "failed"})


class _N8nLike(Protocol):
    async def list_executions(self, workflow_id: str) -> List[Dict[str, Any]]: ...
    async def aclose(self) -> None: ...


N8nClientFactory = Callable[[str, str], _N8nLike]


class WorkflowFailureBehavior:

    def __init__(
        self,
        workflow_store: WorkflowStore,
        state_store: ProactiveStateStore,
        client_factory: N8nClientFactory,
    ) -> None:
        self._wf = workflow_store
        self._state = state_store
        self._make_client = client_factory

    async def check(self, customer_id: str) -> List[ProactiveTrigger]:
        config = await self._wf.get_config(customer_id)
        if config is None:
            return []
        workflows = await self._wf.list_workflows(customer_id)
        if not workflows:
            return []

        client = self._make_client(config["base_url"], config["api_key"])
        try:
            triggers: list[ProactiveTrigger] = []
            for wf in workflows:
                triggers.extend(
                    await self._check_workflow(customer_id, wf, client)
                )
            return triggers
        finally:
            # Must run even when a workflow's list_executions raises —
            # otherwise each tick leaks an httpx client.
            await client.aclose()

    async def _check_workflow(
        self, customer_id: str, wf: Dict[str, Any], client: _N8nLike,
    ) -> List[ProactiveTrigger]:
        wf_id = wf["workflow_id"]
        wf_name = wf.get("name", wf_id)

        try:
            executions = await client.list_executions(wf_id)
        except N8nError as e:
            logger.warning(
                "n8n list_executions failed for customer=%s workflow=%s: %s",
                customer_id, wf_id, e,
            )
            return []

        if not executions:
            return []

        last_seen = await self._state.get_last_seen_execution(customer_id, wf_id)

        # Walk newest-first until we hit the boundary. Everything before
        # the boundary is new-to-us, regardless of status.
        new_execs: list[dict] = []
        for ex in executions:
            if ex.get("id") == last_seen:
                break
            new_execs.append(ex)

        # Advance the boundary to the newest execution we just saw —
        # success or failure, it's been processed.
        newest_id = executions[0].get("id")
        if newest_id is not None and newest_id != last_seen:
            await self._state.set_last_seen_execution(customer_id, wf_id, newest_id)

        return [
            self._to_trigger(wf_id, wf_name, ex)
            for ex in new_execs
            if ex.get("status") in _FAILURE_STATUSES
        ]

    @staticmethod
    def _to_trigger(wf_id: str, wf_name: str, execution: dict) -> ProactiveTrigger:
        exec_id = execution.get("id", "unknown")
        return ProactiveTrigger(
            domain="workflow",
            trigger_type="workflow_failure",
            priority=Priority.HIGH,
            title=f"Workflow failed: {wf_name}",
            payload={
                "workflow_id": wf_id,
                "workflow_name": wf_name,
                "execution_id": exec_id,
                "status": execution.get("status"),
            },
            suggested_message=(
                f"Your '{wf_name}' automation just failed "
                f"(execution {exec_id}). Want me to dig into what went wrong?"
            ),
            cooldown_key=f"workflow_failure:{wf_id}:{exec_id}",
        )
