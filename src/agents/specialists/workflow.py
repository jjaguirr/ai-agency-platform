"""
Workflow specialist agent.

Fourth specialist in the delegation framework. Handles workflow discovery,
deployment, management (pause/delete/update), and listing. All n8n I/O goes
through an ``N8nClient`` Protocol seam. Template search uses a
``TemplateCatalog``. Workflow ownership is tracked per-customer in Redis via
``WorkflowTracker``.

Routing tension: "set up a weekly report" is workflows, not scheduling
(no calendar event). "Schedule a recurring payment" is finance. The negative
guards in ``assess_task`` damp confidence when automation keywords co-occur
with another domain's action nouns.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import Any, Optional, TYPE_CHECKING

from src.agents.base.specialist import (
    SpecialistAgent,
    SpecialistResult,
    SpecialistStatus,
    SpecialistTask,
    TaskAssessment,
)

if TYPE_CHECKING:
    from src.agents.executive_assistant import BusinessContext
    from src.integrations.n8n.catalog import TemplateCatalog
    from src.integrations.n8n.client import N8nClient
    from src.integrations.n8n.tracking import WorkflowTracker

logger = logging.getLogger(__name__)


# --- Assessment vocabulary --------------------------------------------------

_UNAMBIGUOUS_PHRASES = ["workflow", "automation", "n8n"]

_STRONG_PHRASES = [
    "set up a recurring", "automate my", "automatically send",
    "automatically generate", "set up automatic", "create an automation",
    "build an automation", "every week send", "every day run",
    "every month send",
]

_WEAK_PHRASES = [
    "every week", "every day", "every month", "recurring",
    "automatically", "automate", "template", "trigger",
]

# Damping: automation signal + another domain's action noun → confidence -= _DAMP
_SCHEDULING_ACTION_NOUNS = {"meeting", "appointment", "call", "calendar"}
_SOCIAL_ACTION_NOUNS = {"post", "tweet", "reel", "story", "hashtag", "content"}
_FINANCE_ACTION_NOUNS = {"payment", "invoice", "expense", "payroll", "deposit"}
_DAMP = 0.50

_AUTOMATION_TOOLS = {"n8n", "Zapier", "Make", "Integromat", "IFTTT", "Power Automate"}

_STRATEGIC_PATTERNS = [
    r"\bshould i automate\b",
    r"\bis it worth\b.*\bautomat",
    r"\bworth it\b.*\bautomat",
    r"\bshould i set up\b.*\bautomat",
]

# Management intent keywords
_LIST_PHRASES = ["list", "show me", "what automations", "my workflows", "my automations",
                 "what workflows", "active workflows", "running automations"]
_PAUSE_PHRASES = ["pause", "stop", "deactivate", "disable", "turn off"]
_DELETE_PHRASES = ["delete", "remove", "get rid of"]
_UPDATE_PHRASES = ["change", "update", "modify", "switch to", "make it"]
_DISCOVER_PHRASES = ["find", "search", "discover", "template", "what can i automate",
                     "browse", "suggest"]
_DEPLOY_PHRASES = ["set up", "create", "deploy", "build", "install", "activate"]


class WorkflowSpecialist(SpecialistAgent):

    def __init__(
        self,
        n8n_client: Optional["N8nClient"] = None,
        catalog: Optional["TemplateCatalog"] = None,
        tracker: Optional["WorkflowTracker"] = None,
    ):
        self._n8n = n8n_client
        self._catalog = catalog
        self._tracker = tracker

    @property
    def domain(self) -> str:
        return "workflows"

    # --- Assessment ---------------------------------------------------------

    def assess_task(
        self, task_description: str, context: "BusinessContext",
    ) -> TaskAssessment:
        text = task_description.lower()
        confidence = 0.0

        # Unambiguous phrases
        for phrase in _UNAMBIGUOUS_PHRASES:
            if phrase in text:
                confidence += 0.60
                break

        # Strong phrases
        for phrase in _STRONG_PHRASES:
            if phrase in text:
                confidence += 0.35

        # Weak phrases
        weak_hits = sum(1 for p in _WEAK_PHRASES if p in text)
        confidence += min(0.25, weak_hits * 0.15)

        # Management intents also boost confidence
        if any(p in text for p in _LIST_PHRASES + _PAUSE_PHRASES + _DELETE_PHRASES):
            if "workflow" in text or "automation" in text:
                confidence += 0.35

        # Damp when automation keywords co-occur with another domain's nouns
        has_auto = "automat" in text or any(p in text for p in ("every week", "every day", "recurring"))
        if has_auto:
            has_anchor = any(p in text for p in _UNAMBIGUOUS_PHRASES)
            if not has_anchor:
                words = set(re.findall(r"\b\w+\b", text))
                if (words & _SCHEDULING_ACTION_NOUNS
                        or words & _SOCIAL_ACTION_NOUNS
                        or words & _FINANCE_ACTION_NOUNS):
                    confidence -= _DAMP

        # Context boost: customer uses automation tools
        if confidence > 0:
            tools = set(context.current_tools or [])
            if tools & _AUTOMATION_TOOLS:
                confidence += 0.15
            opp = " ".join(getattr(context, "automation_opportunities", None) or []).lower()
            pain = " ".join(context.pain_points or []).lower()
            if "automat" in opp or "automat" in pain:
                confidence += 0.10

        confidence = max(0.0, min(0.95, confidence))

        # Strategic gate
        is_strategic = any(re.search(p, text) for p in _STRATEGIC_PATTERNS)

        return TaskAssessment(confidence=confidence, is_strategic=is_strategic)

    # --- Intent classification ----------------------------------------------

    def _classify_intent(self, text: str) -> str:
        t = text.lower()
        if any(p in t for p in _LIST_PHRASES):
            return "list"
        if any(p in t for p in _PAUSE_PHRASES):
            return "pause"
        if any(p in t for p in _DELETE_PHRASES):
            return "delete"
        if any(p in t for p in _UPDATE_PHRASES):
            return "update"
        if any(p in t for p in _DISCOVER_PHRASES):
            return "discover"
        if any(p in t for p in _DEPLOY_PHRASES):
            return "deploy"
        return "discover"

    # --- Execution ----------------------------------------------------------

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        intent = self._classify_intent(task.description)
        handler = {
            "discover": self._handle_discover,
            "deploy": self._handle_deploy,
            "list": self._handle_list,
            "pause": self._handle_pause,
            "delete": self._handle_delete,
            "update": self._handle_update,
        }.get(intent, self._handle_discover)
        return await handler(task)

    # --- Handlers -----------------------------------------------------------

    async def _handle_discover(self, task: SpecialistTask) -> SpecialistResult:
        if self._catalog is None:
            return self._failed("Template catalog not configured")
        results = self._catalog.search_local(task.description)
        templates = [
            {"name": r.name, "description": r.description, "category": r.category}
            for r in results
        ]
        summary = None
        if templates:
            names = ", ".join(t["name"] for t in templates[:3])
            summary = f"I found {len(templates)} matching template(s): {names}."
        else:
            summary = "I couldn't find any matching templates for that."
        return self._completed(
            {"templates": templates, "count": len(templates)},
            summary=summary,
        )

    async def _handle_deploy(self, task: SpecialistTask) -> SpecialistResult:
        if self._n8n is None:
            return self._failed("n8n connection not configured")
        # Placeholder: deploy requires customization flow integration.
        # For now, signal that the specialist can handle this intent.
        return self._completed(
            {"action": "deploy", "description": task.description},
            summary="I can set up this automation for you. Let me find the right template.",
        )

    async def _handle_list(self, task: SpecialistTask) -> SpecialistResult:
        if self._tracker is None:
            return self._failed("Workflow tracking not configured")
        workflows = await self._tracker.list_workflows(task.customer_id)
        wf_data = [
            {"workflow_id": w.workflow_id, "name": w.name, "status": w.status}
            for w in workflows
        ]
        count = len(wf_data)
        if count:
            names = ", ".join(w["name"] for w in wf_data)
            summary = f"You have {count} automation(s): {names}."
        else:
            summary = "You don't have any automations set up yet."
        return self._completed({"workflows": wf_data, "count": count}, summary=summary)

    async def _handle_pause(self, task: SpecialistTask) -> SpecialistResult:
        if self._n8n is None or self._tracker is None:
            return self._failed("n8n connection or workflow tracking not configured")
        matches = await self._tracker.find_by_name(task.customer_id, task.description)
        # Also try extracting a name from the message
        if not matches:
            all_wfs = await self._tracker.list_workflows(task.customer_id)
            for word in task.description.lower().split():
                for wf in all_wfs:
                    if word in wf.name.lower() and wf not in matches:
                        matches.append(wf)
        if not matches:
            return self._completed(
                {"action": "pause", "found": False},
                summary="I couldn't find a matching workflow to pause.",
            )
        if len(matches) > 1:
            names = ", ".join(f'"{m.name}"' for m in matches)
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={"candidates": [m.name for m in matches]},
                confidence=0.8,
                clarification_question=f"I found multiple matches: {names}. Which one should I pause?",
            )
        wf = matches[0]
        await self._n8n.deactivate_workflow(wf.workflow_id)
        await self._tracker.update_status(task.customer_id, wf.workflow_id, "inactive")
        return self._completed(
            {"workflow_id": wf.workflow_id, "name": wf.name, "action": "paused"},
            summary=f'Done. "{wf.name}" has been paused.',
        )

    async def _handle_delete(self, task: SpecialistTask) -> SpecialistResult:
        if self._n8n is None or self._tracker is None:
            return self._failed("n8n connection or workflow tracking not configured")
        matches = await self._tracker.find_by_name(task.customer_id, task.description)
        if not matches:
            all_wfs = await self._tracker.list_workflows(task.customer_id)
            for word in task.description.lower().split():
                for wf in all_wfs:
                    if word in wf.name.lower() and wf not in matches:
                        matches.append(wf)
        if not matches:
            return self._completed(
                {"action": "delete", "found": False},
                summary="I couldn't find a matching workflow to delete.",
            )
        if len(matches) > 1:
            names = ", ".join(f'"{m.name}"' for m in matches)
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={"candidates": [m.name for m in matches]},
                confidence=0.8,
                clarification_question=f"I found multiple matches: {names}. Which one should I delete?",
            )
        wf = matches[0]
        await self._n8n.delete_workflow(wf.workflow_id)
        await self._tracker.remove(task.customer_id, wf.workflow_id)
        return self._completed(
            {"workflow_id": wf.workflow_id, "name": wf.name, "action": "deleted"},
            summary=f'Done. "{wf.name}" has been deleted.',
        )

    async def _handle_update(self, task: SpecialistTask) -> SpecialistResult:
        if self._n8n is None or self._tracker is None:
            return self._failed("n8n connection or workflow tracking not configured")
        return self._completed(
            {"action": "update", "description": task.description},
            summary="I can update that automation. What would you like to change?",
        )

    # --- Helpers ------------------------------------------------------------

    def _completed(
        self, payload: dict[str, Any], summary: str | None = None,
    ) -> SpecialistResult:
        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.9,
            summary_for_ea=summary,
        )

    def _failed(self, error: str) -> SpecialistResult:
        return SpecialistResult(
            status=SpecialistStatus.FAILED,
            domain=self.domain,
            payload={},
            confidence=0.0,
            error=error,
        )
