"""
Workflow specialist — automations through n8n.

Fourth specialist. The framework contract holds unchanged: assess_task
is cheap keyword scoring, execute_task is intent-dispatch. The new
routing tension is with scheduling: both domains hear "schedule," but
recurrence markers ("every week," "automatically," "recurring") are
ours, calendar nouns ("meeting," "appointment") are theirs.

Seams: WorkflowStore, WorkflowCatalog, and an N8nClient factory. All
optional — the no-arg constructor works so the EA's importlib loop can
instantiate it, but execute degrades to "not configured" until a store
is wired in.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from src.agents.base.specialist import (
    SpecialistAgent,
    SpecialistResult,
    SpecialistStatus,
    SpecialistTask,
    TaskAssessment,
)
from src.workflows.customizer import WorkflowCustomizer, IncompleteCustomizationError

if TYPE_CHECKING:
    from src.agents.executive_assistant import BusinessContext
    from src.workflows.store import WorkflowStore
    from src.workflows.catalog import WorkflowCatalog
    from src.workflows.client import N8nClient

logger = logging.getLogger(__name__)


# --- Assessment vocabulary --------------------------------------------------

# The unambiguous signals. One of these alone routes.
_UNAMBIGUOUS_PHRASES = [
    "automation", "automate", "automatically", "workflow",
    "recurring", "n8n",
]

# Strong: automation-adjacent actions.
_STRONG_PHRASES = [
    "set up a weekly", "set up a daily", "set up a monthly",
    "every monday", "every tuesday", "every wednesday", "every thursday",
    "every friday", "every saturday", "every sunday",
    "every week", "every day", "every month", "every hour",
    "pause my", "delete the", "delete my",
]

# Weak on their own, boost in combination.
_WEAK_PHRASES = [
    "sync", "integration", "trigger", "pipeline", "digest",
    "notify me when", "send me", "report",
]

# Calendar anchors that pull toward scheduling, not us. We damp when one
# appears without a recurrence marker — "schedule a meeting every week"
# stays ours, "schedule a meeting tomorrow" goes to scheduling.
_CALENDAR_NOUNS = {"meeting", "appointment", "calendar", "call with", "1:1"}
_RECURRENCE_MARKERS = {"every", "weekly", "daily", "monthly", "recurring",
                       "automatically", "automate"}
_DAMP = 0.50

_STRATEGIC_PATTERNS = [
    r"\bshould i (automate|set up|build)\b",
    r"\bis it worth (automating|setting up)\b",
    r"\bworth automating\b",
    r"\bdoes it make sense to automate\b",
    r"\bshould we automate\b",
]

_AUTOMATION_TOOLS = {"n8n", "Zapier", "Make", "IFTTT", "Workato"}


# --- Parameter extraction from conversation ---------------------------------

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# "every monday at 9am", "mondays at 9", "every day at 8:30"
_CRON_HINTS = {
    "monday": "1", "tuesday": "2", "wednesday": "3", "thursday": "4",
    "friday": "5", "saturday": "6", "sunday": "0",
}
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)


class WorkflowSpecialist(SpecialistAgent):

    def __init__(
        self,
        store: Optional["WorkflowStore"] = None,
        catalog: Optional["WorkflowCatalog"] = None,
        n8n_client_factory: Optional[Callable[..., "N8nClient"]] = None,
    ):
        self._store = store
        self._catalog = catalog
        self._client_factory = n8n_client_factory

    @property
    def domain(self) -> str:
        return "workflows"

    # --- Assessment ---------------------------------------------------------

    def assess_task(
        self, task_description: str, context: "BusinessContext"
    ) -> TaskAssessment:
        text = task_description.lower()

        confidence = 0.0

        for phrase in _UNAMBIGUOUS_PHRASES:
            if phrase in text:
                confidence += 0.60
                break
        for phrase in _STRONG_PHRASES:
            if phrase in text:
                confidence += 0.35
        weak_hits = sum(1 for p in _WEAK_PHRASES if p in text)
        confidence += min(0.30, weak_hits * 0.15)

        # Recurrence + "set up" / "send" is a strong automation signal even
        # without the word "automate."
        has_recurrence = any(m in text for m in _RECURRENCE_MARKERS)
        if has_recurrence and any(v in text for v in
                                  ("set up", "send me", "create a", "build a")):
            confidence += 0.30

        # Damp if calendar nouns anchor this without recurrence — that's
        # scheduling's territory.
        if any(n in text for n in _CALENDAR_NOUNS) and not has_recurrence:
            confidence -= _DAMP

        if confidence > 0:
            tools = set(context.current_tools or [])
            if tools & _AUTOMATION_TOOLS:
                confidence += 0.15

        confidence = max(0.0, min(0.9, confidence))

        is_strategic = False
        if confidence >= 0.4:
            is_strategic = any(re.search(p, text) for p in _STRATEGIC_PATTERNS)

        return TaskAssessment(confidence=confidence, is_strategic=is_strategic)

    # --- Execution ----------------------------------------------------------

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        if self._store is None:
            return self._failed("workflow store not configured")

        text = task.description.lower()
        intent = self._classify_intent(text)
        handler = {
            "list": self._handle_list,
            "pause": self._handle_pause,
            "resume": self._handle_resume,
            "delete": self._handle_delete,
            "deploy": self._handle_deploy,
        }[intent]
        return await handler(task, text)

    def _classify_intent(self, text: str) -> str:
        if any(p in text for p in ("what automation", "what workflow",
                                   "list my automation", "list my workflow",
                                   "automations do i have",
                                   "workflows do i have",
                                   "show my automation")):
            return "list"
        if any(p in text for p in ("pause", "deactivate", "turn off", "stop my")):
            return "pause"
        if any(p in text for p in ("resume", "reactivate", "turn on",
                                   "start my", "unpause")):
            return "resume"
        if any(p in text for p in ("delete", "remove", "get rid of")):
            return "delete"
        return "deploy"

    # --- List ---------------------------------------------------------------

    async def _handle_list(self, task: SpecialistTask, text: str) -> SpecialistResult:
        wfs = await self._store.list_workflows(task.customer_id)
        if not wfs:
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED,
                domain=self.domain,
                payload={"workflows": []},
                confidence=0.9,
                summary_for_ea="You have no automations running right now.",
            )
        active = [w for w in wfs if w["status"] == "active"]
        names = ", ".join(w["name"] for w in wfs)
        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={"workflows": wfs},
            confidence=0.9,
            summary_for_ea=(
                f"You have {len(wfs)} automation{'s' if len(wfs) != 1 else ''} "
                f"({len(active)} active): {names}."
            ),
        )

    # --- Pause / resume / delete --------------------------------------------

    async def _handle_pause(self, task: SpecialistTask, text: str) -> SpecialistResult:
        return await self._mutate(task, text, verb="pause",
                                  action=self._do_pause)

    async def _handle_resume(self, task: SpecialistTask, text: str) -> SpecialistResult:
        return await self._mutate(task, text, verb="resume",
                                  action=self._do_resume)

    async def _handle_delete(self, task: SpecialistTask, text: str) -> SpecialistResult:
        return await self._mutate(task, text, verb="delete",
                                  action=self._do_delete)

    async def _mutate(
        self, task: SpecialistTask, text: str, *, verb: str, action
    ) -> SpecialistResult:
        wf = await self._find_target(task.customer_id, text)
        if wf is None:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={},
                confidence=0.3,
                clarification_question=(
                    f"Which automation should I {verb}? I couldn't match "
                    f"that to anything you have running."
                ),
            )

        client = await self._get_client(task.customer_id)
        if client is None:
            return self._failed("n8n connection not configured")

        summary = await action(client, task.customer_id, wf)
        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={"workflow_id": wf["workflow_id"], "name": wf["name"]},
            confidence=0.85,
            summary_for_ea=summary,
        )

    async def _do_pause(self, client, customer_id: str, wf: Dict) -> str:
        await client.deactivate_workflow(wf["workflow_id"])
        await self._store.update_status(customer_id, wf["workflow_id"], "inactive")
        return f"Paused '{wf['name']}'. It'll stay off until you resume it."

    async def _do_resume(self, client, customer_id: str, wf: Dict) -> str:
        await client.activate_workflow(wf["workflow_id"])
        await self._store.update_status(customer_id, wf["workflow_id"], "active")
        return f"'{wf['name']}' is running again."

    async def _do_delete(self, client, customer_id: str, wf: Dict) -> str:
        await client.delete_workflow(wf["workflow_id"])
        await self._store.remove_workflow(customer_id, wf["workflow_id"])
        return f"Deleted '{wf['name']}'."

    async def _find_target(self, customer_id: str, text: str) -> Optional[Dict]:
        # Strip the intent verb and filler — what's left is the name hint.
        # "pause my Monday reports" → "monday reports"
        hint = re.sub(
            r"\b(pause|deactivate|turn off|stop|resume|reactivate|turn on|"
            r"start|delete|remove|get rid of|my|the)\b",
            "", text,
        ).strip()
        return await self._store.find_by_name(customer_id, hint)

    # --- Deploy -------------------------------------------------------------

    async def _handle_deploy(self, task: SpecialistTask, text: str) -> SpecialistResult:
        if self._catalog is None:
            return self._failed("template catalog not configured")

        # Prior-turn payload may carry the template we already picked.
        template_id = self._resume_template_id(task)
        templates = self._catalog.search_local(task.description)

        if template_id:
            template = next((t for t in self._catalog.list_local()
                            if t.id == template_id), None)
        elif templates:
            template = templates[0]
        else:
            return self._failed(
                "I couldn't find a template for that. Try describing what "
                "you want in terms of the tools involved (HubSpot, Slack, etc.)."
            )

        customizer = WorkflowCustomizer(template.raw)
        values = self._collect_params(task, customizer)
        missing = customizer.identify_missing(values)

        if missing:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={"template_id": template.id, "missing": missing,
                         "collected": values},
                confidence=0.6,
                clarification_question=self._ask_for(missing[0]),
            )

        client = await self._get_client(task.customer_id)
        if client is None:
            return self._failed("n8n connection not configured")

        definition = customizer.apply(values, name=template.name)
        created = await client.create_workflow(definition)
        wf_id = created["id"]
        await client.activate_workflow(wf_id)
        await self._store.add_workflow(
            task.customer_id, wf_id, template.name, "active"
        )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={"workflow_id": wf_id, "name": template.name,
                     "parameters": values},
            confidence=0.85,
            summary_for_ea=(
                f"Done. '{template.name}' is deployed and active. "
                f"You can manage it from the dashboard."
            ),
        )

    def _resume_template_id(self, task: SpecialistTask) -> Optional[str]:
        # The EA carries specialist payload forward in prior_turns during
        # multi-turn clarification. Look for our own breadcrumb.
        for turn in task.prior_turns:
            content = turn.get("content", "")
            if "template_id:" in content:
                m = re.search(r"template_id:\s*(\w+)", content)
                if m:
                    return m.group(1)
        return None

    def _collect_params(
        self, task: SpecialistTask, customizer: WorkflowCustomizer
    ) -> Dict[str, str]:
        """Scrape the full conversation corpus for parameter values.
        Email address → any param with 'email'/'recipient' in the label.
        Cron-like schedule → any param with 'cron'/'schedule' in the label."""
        corpus = task.description + " " + " ".join(
            t.get("content", "") for t in task.prior_turns
        )
        values: Dict[str, str] = {}

        for label in customizer.identify_missing({}):
            label_l = label.lower()
            if "email" in label_l or "recipient" in label_l:
                m = _EMAIL_RE.search(corpus)
                if m:
                    values[label] = m.group(0)
            elif "cron" in label_l or "schedule" in label_l or "when" in label_l:
                cron = self._parse_cron(corpus.lower())
                if cron:
                    values[label] = cron

        return values

    @staticmethod
    def _parse_cron(text: str) -> Optional[str]:
        """Best-effort: 'every monday at 9am' → '0 9 * * 1'."""
        dow = "*"
        for day, num in _CRON_HINTS.items():
            if day in text:
                dow = num
                break

        hour, minute = 9, 0
        for m in _TIME_RE.finditer(text):
            h = int(m.group(1))
            if m.group(3):  # has am/pm — definitely a time
                if m.group(3).lower() == "pm" and h < 12:
                    h += 12
                elif m.group(3).lower() == "am" and h == 12:
                    h = 0
                hour = h
                minute = int(m.group(2) or 0)
                break

        if dow == "*" and "every day" not in text and "daily" not in text:
            return None  # no schedule signal at all

        return f"{minute} {hour} * * {dow}"

    @staticmethod
    def _ask_for(label: str) -> str:
        label_l = label.lower()
        if "email" in label_l or "recipient" in label_l:
            return "What email address should I send to?"
        if "cron" in label_l or "schedule" in label_l:
            return "When should this run? (e.g. 'every Monday at 9am')"
        if "url" in label_l or "endpoint" in label_l:
            return f"What URL should I use for the {label}?"
        return f"What should I use for the {label}?"

    # --- Helpers ------------------------------------------------------------

    async def _get_client(self, customer_id: str) -> Optional[Any]:
        if self._client_factory is None:
            return None
        cfg = await self._store.get_config(customer_id)
        if cfg is None:
            return None
        return self._client_factory(
            base_url=cfg["base_url"], api_key=cfg["api_key"]
        )

    def _failed(self, msg: str) -> SpecialistResult:
        return SpecialistResult(
            status=SpecialistStatus.FAILED,
            domain=self.domain,
            payload={},
            confidence=0.0,
            error=msg,
        )
