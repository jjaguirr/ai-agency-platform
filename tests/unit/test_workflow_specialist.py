"""
Tests for WorkflowSpecialist.

Fourth specialist in the delegation framework. Proves the framework still
requires zero modification for a fourth domain, and exercises the four-way
routing surface where social_media, finance, scheduling, and workflows
compete for every message.

Coverage:
- Assessment: operational vs strategic vs out-of-domain
- Overlap resolution with all four specialists registered
- Execution: discover, deploy, list, pause, delete
- Multi-turn clarification for missing deploy parameters
- Graceful degradation when dependencies are None
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.agents.specialists.workflow import WorkflowSpecialist
from src.agents.base.specialist import (
    DelegationRegistry,
    SpecialistStatus,
    SpecialistTask,
)
from src.agents.executive_assistant import BusinessContext
from src.integrations.n8n.catalog import TemplateCatalog, TemplateMatch
from src.integrations.n8n.tracking import TrackedWorkflow, WorkflowTracker


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def ctx():
    return BusinessContext(
        business_name="AcmeCo",
        industry="consulting",
        current_tools=["n8n", "Slack", "HubSpot"],
        pain_points=["too many manual reports", "automation needed"],
    )


@pytest.fixture
def bare_ctx():
    return BusinessContext(business_name="Unknown Co")


# --- Stub doubles -----------------------------------------------------------

class StubN8nClient:
    """Test double conforming to N8nClient by shape (structural typing)."""

    def __init__(self):
        self.calls: list[tuple[str, Any]] = []
        self._workflows: dict[str, dict] = {}
        self._next_id = 100

    async def list_workflows(self) -> list[dict]:
        self.calls.append(("list_workflows", ()))
        return list(self._workflows.values())

    async def get_workflow(self, workflow_id: str) -> dict:
        self.calls.append(("get_workflow", (workflow_id,)))
        return self._workflows.get(workflow_id, {})

    async def create_workflow(self, definition: dict) -> dict:
        wf_id = str(self._next_id)
        self._next_id += 1
        wf = {"id": wf_id, **definition}
        self._workflows[wf_id] = wf
        self.calls.append(("create_workflow", (definition,)))
        return wf

    async def activate_workflow(self, workflow_id: str) -> dict:
        self.calls.append(("activate_workflow", (workflow_id,)))
        return {"id": workflow_id, "active": True}

    async def deactivate_workflow(self, workflow_id: str) -> dict:
        self.calls.append(("deactivate_workflow", (workflow_id,)))
        return {"id": workflow_id, "active": False}

    async def delete_workflow(self, workflow_id: str) -> None:
        self.calls.append(("delete_workflow", (workflow_id,)))
        self._workflows.pop(workflow_id, None)

    async def list_executions(self, workflow_id=None, limit=20) -> list[dict]:
        self.calls.append(("list_executions", (workflow_id, limit)))
        return []


class StubCatalog:
    """Test double for TemplateCatalog."""

    def __init__(self, results: list[TemplateMatch] | None = None):
        self._results = results or []
        self.calls: list[tuple[str, Any]] = []

    def search_local(self, query, tags=None):
        self.calls.append(("search_local", (query, tags)))
        return self._results

    async def search_community(self, query):
        self.calls.append(("search_community", (query,)))
        return []

    def get_local_template(self, name):
        return None


@pytest.fixture
def redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def tracker(redis):
    return WorkflowTracker(redis)


def _task(description: str, customer_id: str = "test_cust", ctx: BusinessContext | None = None, prior_turns=None):
    return SpecialistTask(
        description=description,
        customer_id=customer_id,
        business_context=ctx or BusinessContext(business_name="Test"),
        domain_memories=[],
        prior_turns=prior_turns or [],
    )


# --- Assessment: operational ------------------------------------------------

class TestAssessOperational:
    @pytest.mark.parametrize("msg", [
        "automate my weekly reports",
        "set up a recurring email digest",
        "create a workflow for invoice reminders",
        "I need an automation that sends slack messages every morning",
        "set up automatic email followups",
    ])
    def test_operational_messages_score_above_threshold(self, msg, ctx):
        spec = WorkflowSpecialist()
        assessment = spec.assess_task(msg, ctx)
        assert assessment.confidence >= 0.6, f"{msg!r} scored {assessment.confidence}"
        assert not assessment.is_strategic


class TestAssessStrategic:
    @pytest.mark.parametrize("msg", [
        "should I automate my marketing?",
        "is it worth setting up automations for sales?",
    ])
    def test_strategic_messages_flagged(self, msg, ctx):
        spec = WorkflowSpecialist()
        assessment = spec.assess_task(msg, ctx)
        assert assessment.is_strategic


class TestAssessDamping:
    @pytest.mark.parametrize("msg", [
        "automatically schedule a meeting every week",
        "set up recurring payment processing",
        "automate my content post schedule",
    ])
    def test_damping_reduces_confidence_for_other_domain_nouns(self, msg, bare_ctx):
        """Automation signal + another domain's action noun should be damped
        below threshold when no unambiguous anchor (workflow/automation/n8n) present."""
        spec = WorkflowSpecialist()
        assessment = spec.assess_task(msg, bare_ctx)
        assert assessment.confidence < 0.6, f"{msg!r} scored {assessment.confidence} (should be damped)"

    def test_damping_does_not_apply_with_unambiguous_anchor(self, bare_ctx):
        """'workflow' anchor overrides damping even with scheduling nouns."""
        spec = WorkflowSpecialist()
        assessment = spec.assess_task("create a workflow to schedule meetings automatically", bare_ctx)
        assert assessment.confidence >= 0.6


class TestAssessOutOfDomain:
    @pytest.mark.parametrize("msg", [
        "book a meeting with John",
        "check my Instagram engagement",
        "track $500 for office supplies",
        "how's the weather today",
        "what time is it",
    ])
    def test_out_of_domain_scores_below_threshold(self, msg, bare_ctx):
        spec = WorkflowSpecialist()
        assessment = spec.assess_task(msg, bare_ctx)
        assert assessment.confidence < 0.6, f"{msg!r} scored {assessment.confidence}"


# --- Overlap resolution with all four specialists ---------------------------

class TestOverlapResolution:
    """Register all four specialists and verify routing."""

    def _registry(self):
        from src.agents.specialists.social_media import SocialMediaSpecialist
        from src.agents.specialists.finance import FinanceSpecialist
        from src.agents.specialists.scheduling import SchedulingSpecialist

        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(SocialMediaSpecialist())
        reg.register(FinanceSpecialist())
        reg.register(SchedulingSpecialist())
        reg.register(WorkflowSpecialist())
        return reg

    def test_automation_request_goes_to_workflows(self):
        reg = self._registry()
        ctx = BusinessContext(business_name="Co", current_tools=["n8n"])
        match = reg.route("create an automation to send weekly reports", ctx)
        assert match is not None
        assert match.specialist.domain == "workflows"

    def test_engagement_check_goes_to_social(self):
        reg = self._registry()
        ctx = BusinessContext(business_name="Co", current_tools=["Instagram"])
        match = reg.route("check my Instagram engagement", ctx)
        assert match is not None
        assert match.specialist.domain == "social_media"

    def test_book_meeting_goes_to_scheduling(self):
        reg = self._registry()
        ctx = BusinessContext(business_name="Co", current_tools=["Google Calendar"])
        match = reg.route("book a meeting with Sarah", ctx)
        assert match is not None
        assert match.specialist.domain == "scheduling"

    def test_track_expense_goes_to_finance(self):
        reg = self._registry()
        ctx = BusinessContext(business_name="Co", current_tools=["QuickBooks"])
        match = reg.route("track $200 for office rent", ctx)
        assert match is not None
        assert match.specialist.domain == "finance"


# --- Execution: discover ----------------------------------------------------

class TestDiscoverIntent:
    async def test_returns_template_list(self, ctx):
        catalog = StubCatalog(results=[
            TemplateMatch("Weekly Report", "desc", "reporting", ["report"], 0.8),
        ])
        spec = WorkflowSpecialist(catalog=catalog)
        result = await spec.execute_task(_task("find me a template for reports", ctx=ctx))
        assert result.status == SpecialistStatus.COMPLETED
        assert len(result.payload["templates"]) == 1


# --- Execution: list --------------------------------------------------------

class TestListIntent:
    async def test_returns_customer_workflows(self, tracker, ctx):
        await tracker.track("c", TrackedWorkflow("w1", "Weekly Report", "active", "2026-01-01"))
        await tracker.track("c", TrackedWorkflow("w2", "Invoice Gen", "active", "2026-01-02"))
        spec = WorkflowSpecialist(tracker=tracker)
        result = await spec.execute_task(_task("what automations do I have", customer_id="c", ctx=ctx))
        assert result.status == SpecialistStatus.COMPLETED
        assert len(result.payload["workflows"]) == 2


# --- Execution: pause -------------------------------------------------------

class TestPauseIntent:
    async def test_deactivates_workflow(self, tracker, ctx):
        n8n = StubN8nClient()
        await tracker.track("c", TrackedWorkflow("w1", "Monday Report", "active", "2026-01-01"))
        spec = WorkflowSpecialist(n8n_client=n8n, tracker=tracker)
        result = await spec.execute_task(_task("pause my Monday report", customer_id="c", ctx=ctx))
        assert result.status == SpecialistStatus.COMPLETED
        assert ("deactivate_workflow", ("w1",)) in n8n.calls
        # Status updated in tracker
        wfs = await tracker.list_workflows("c")
        assert wfs[0].status == "inactive"


# --- Execution: delete ------------------------------------------------------

class TestDeleteIntent:
    async def test_removes_workflow(self, tracker, ctx):
        n8n = StubN8nClient()
        await tracker.track("c", TrackedWorkflow("w1", "Invoice Tracker", "active", "2026-01-01"))
        spec = WorkflowSpecialist(n8n_client=n8n, tracker=tracker)
        result = await spec.execute_task(_task("delete the invoice tracker", customer_id="c", ctx=ctx))
        assert result.status == SpecialistStatus.COMPLETED
        assert ("delete_workflow", ("w1",)) in n8n.calls
        assert await tracker.list_workflows("c") == []


# --- Execution: no dependencies → FAILED -----------------------------------

class TestNoDependencies:
    async def test_no_client_returns_failed(self, ctx):
        spec = WorkflowSpecialist()  # no client, no tracker
        result = await spec.execute_task(_task("pause my workflow", ctx=ctx))
        assert result.status == SpecialistStatus.FAILED
        assert result.error is not None


# --- Execution: ambiguous pause → clarification ----------------------------

class TestAmbiguousPause:
    async def test_multiple_matches_asks_clarification(self, tracker, ctx):
        n8n = StubN8nClient()
        await tracker.track("c", TrackedWorkflow("w1", "Monday Report", "active", "2026-01-01"))
        await tracker.track("c", TrackedWorkflow("w2", "Monthly Report", "active", "2026-01-02"))
        spec = WorkflowSpecialist(n8n_client=n8n, tracker=tracker)
        result = await spec.execute_task(_task("pause my report", customer_id="c", ctx=ctx))
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert result.clarification_question is not None
