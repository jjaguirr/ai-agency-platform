"""
WorkflowSpecialist — fourth specialist in the delegation framework.

Domain: automations. The routing tension is with scheduling:
  "set up a weekly report" → workflows (recurrence, no calendar event)
  "book a meeting" → scheduling (calendar event, one-shot)
  "schedule a weekly report" → workflows despite "schedule" verb

Spec cases:
  - "What automations do I have?" → list
  - "Pause my Monday reports" → deactivate
  - "Delete the invoice tracker" → delete
  - "Change my report to biweekly" → update schedule
  - "Send me my HubSpot pipeline every Monday" → discover→customize→deploy
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from src.agents.specialists.workflows import WorkflowSpecialist
from src.agents.specialists.scheduling import SchedulingSpecialist
from src.agents.specialists.social_media import SocialMediaSpecialist
from src.agents.specialists.finance import FinanceSpecialist
from src.agents.base.specialist import (
    SpecialistTask,
    SpecialistStatus,
    DelegationRegistry,
)
from src.agents.executive_assistant import BusinessContext
from src.workflows.store import WorkflowStore
from src.workflows.catalog import WorkflowTemplate


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def ctx():
    return BusinessContext(
        business_name="Acme Corp",
        industry="saas",
        current_tools=["HubSpot", "Slack", "n8n"],
        pain_points=["manual reporting"],
    )


@pytest.fixture
def bare_ctx():
    return BusinessContext(business_name="X")


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(redis):
    return WorkflowStore(redis)


@pytest.fixture
def n8n_client():
    """AsyncMock conforming to N8nClient shape."""
    m = AsyncMock()
    m.create_workflow = AsyncMock(return_value={"id": "wf_new", "name": "Created"})
    m.activate_workflow = AsyncMock()
    m.deactivate_workflow = AsyncMock()
    m.delete_workflow = AsyncMock()
    return m


@pytest.fixture
def catalog():
    """Catalog stub with one searchable template."""
    m = AsyncMock()
    template = WorkflowTemplate(
        id="hubspot_weekly",
        name="HubSpot Weekly Report",
        description="Email HubSpot pipeline on schedule",
        integrations=["hubspot", "email"],
        category="reporting",
        tags=["weekly", "report", "pipeline"],
        raw={
            "name": "HubSpot Weekly Report",
            "nodes": [
                {"id": "t", "name": "Trigger",
                 "type": "n8n-nodes-base.scheduleTrigger",
                 "typeVersion": 1.2, "position": [0, 0],
                 "parameters": {"rule": {"interval": [
                     {"field": "cronExpression",
                      "expression": "{{CONFIGURE: cron schedule}}"}]}}},
                {"id": "e", "name": "Email",
                 "type": "n8n-nodes-base.emailSend",
                 "typeVersion": 2.1, "position": [200, 0],
                 "parameters": {"toEmail": "{{CONFIGURE: recipient email}}"}},
            ],
            "connections": {
                "Trigger": {"main": [[{"node": "Email", "type": "main", "index": 0}]]},
            },
            "active": False, "settings": {},
        },
        source="local",
    )
    # search_local is sync, search_community is async
    m.search_local = lambda q: [template] if "hubspot" in q.lower() or "pipeline" in q.lower() or "report" in q.lower() else []
    m.search_community = AsyncMock(return_value=[])
    return m


@pytest.fixture
async def specialist(store, n8n_client, catalog):
    """Specialist with all seams injected. n8n config pre-set."""
    await store.set_config("cust_test", base_url="http://n8n.test", api_key="k")
    return WorkflowSpecialist(
        store=store,
        catalog=catalog,
        n8n_client_factory=lambda base_url, api_key: n8n_client,
    )


@pytest.fixture
async def specialist_with_workflows(specialist, store):
    """Customer already has two deployed workflows."""
    await store.add_workflow("cust_test", "wf1", "Monday Report", "active")
    await store.add_workflow("cust_test", "wf2", "Invoice Tracker", "active")
    return specialist


def _task(desc: str, ctx: BusinessContext, prior_turns=None) -> SpecialistTask:
    return SpecialistTask(
        description=desc, customer_id="cust_test",
        business_context=ctx, domain_memories=[],
        prior_turns=prior_turns or [],
    )


# --- Assessment: automation patterns route here ------------------------------

class TestAssessAutomation:
    """Recurrence + automation verbs → workflows."""

    @pytest.mark.parametrize("msg", [
        "set up a weekly HubSpot report",
        "automate my invoice tracking",
        "send me pipeline numbers every Monday",
        "what automations do I have running?",
        "pause my Monday reports",
        "set up a recurring sync from HubSpot to Slack",
        "automatically send a digest every Friday",
    ])
    def test_confident_and_not_strategic(self, ctx, msg):
        spec = WorkflowSpecialist()
        a = spec.assess_task(msg, ctx)
        assert a.confidence >= 0.6
        assert a.is_strategic is False

    @pytest.mark.parametrize("msg", [
        "hello",
        "what's the weather",
        "how are you",
    ])
    def test_unrelated_low_confidence(self, bare_ctx, msg):
        spec = WorkflowSpecialist()
        assert spec.assess_task(msg, bare_ctx).confidence < 0.3


class TestAssessStrategic:
    @pytest.mark.parametrize("msg", [
        "should I automate my reporting?",
        "is it worth setting up automated invoicing?",
        "does it make sense to automate this?",
    ])
    def test_advisory_flagged_strategic(self, ctx, msg):
        spec = WorkflowSpecialist()
        a = spec.assess_task(msg, ctx)
        assert a.is_strategic is True


# --- Routing overlap: workflows vs scheduling -------------------------------

@pytest.fixture
def registry_four_way():
    """All four specialists — the real routing surface."""
    reg = DelegationRegistry(confidence_threshold=0.6)
    reg.register(SocialMediaSpecialist())
    reg.register(FinanceSpecialist())
    reg.register(SchedulingSpecialist())
    reg.register(WorkflowSpecialist())
    return reg


class TestRoutingOverlap:
    """Spec: 'set up a weekly report' → workflows, 'book a meeting' → scheduling."""

    def test_weekly_report_goes_to_workflows(self, registry_four_way, ctx):
        match = registry_four_way.route("set up a weekly report", ctx)
        assert match is not None
        assert match.specialist.domain == "workflows"

    def test_book_meeting_goes_to_scheduling(self, registry_four_way, ctx):
        match = registry_four_way.route("book a meeting with John tomorrow", ctx)
        assert match is not None
        assert match.specialist.domain == "scheduling"

    def test_every_monday_goes_to_workflows(self, registry_four_way, ctx):
        """'every X' is the automation signal — scheduling never recurs."""
        match = registry_four_way.route(
            "send me my HubSpot pipeline every Monday", ctx
        )
        assert match is not None
        assert match.specialist.domain == "workflows"

    def test_appointment_goes_to_scheduling(self, registry_four_way, ctx):
        match = registry_four_way.route("schedule an appointment", ctx)
        assert match.specialist.domain == "scheduling"

    def test_automatically_goes_to_workflows(self, registry_four_way, ctx):
        match = registry_four_way.route(
            "automatically notify me when a deal closes", ctx
        )
        assert match is not None
        assert match.specialist.domain == "workflows"

    def test_what_automations_goes_to_workflows(self, registry_four_way, ctx):
        match = registry_four_way.route("what automations do I have?", ctx)
        assert match.specialist.domain == "workflows"

    def test_schedule_weekly_report_is_workflows_not_scheduling(
        self, registry_four_way, ctx
    ):
        """The hard case: 'schedule' verb + recurrence noun. Recurrence wins."""
        wf = WorkflowSpecialist()
        sched = SchedulingSpecialist()
        wf_a = wf.assess_task("schedule a weekly report", ctx)
        sched_a = sched.assess_task("schedule a weekly report", ctx)
        assert wf_a.confidence > sched_a.confidence


# --- Execute: list ----------------------------------------------------------

class TestList:
    async def test_lists_active_workflows(self, specialist_with_workflows, ctx):
        result = await specialist_with_workflows.execute_task(
            _task("what automations do I have running?", ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert len(result.payload["workflows"]) == 2
        names = {w["name"] for w in result.payload["workflows"]}
        assert names == {"Monday Report", "Invoice Tracker"}

    async def test_empty_list(self, specialist, ctx):
        result = await specialist.execute_task(
            _task("what automations do I have?", ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["workflows"] == []
        assert "no automations" in result.summary_for_ea.lower() or \
               "none" in result.summary_for_ea.lower()


# --- Execute: pause/deactivate ----------------------------------------------

class TestPause:
    async def test_deactivates_by_name(
        self, specialist_with_workflows, n8n_client, store, ctx
    ):
        result = await specialist_with_workflows.execute_task(
            _task("pause my Monday reports", ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        n8n_client.deactivate_workflow.assert_awaited_once_with("wf1")
        # store reflects new status
        wf = await store.get_workflow("cust_test", "wf1")
        assert wf["status"] == "inactive"

    async def test_pause_unknown_asks_clarification(
        self, specialist_with_workflows, ctx
    ):
        result = await specialist_with_workflows.execute_task(
            _task("pause my Tuesday digest", ctx)
        )
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert "which" in result.clarification_question.lower()


# --- Execute: delete --------------------------------------------------------

class TestDelete:
    async def test_deletes_by_name(
        self, specialist_with_workflows, n8n_client, store, ctx
    ):
        result = await specialist_with_workflows.execute_task(
            _task("delete the invoice tracker", ctx)
        )
        assert result.status == SpecialistStatus.COMPLETED
        n8n_client.delete_workflow.assert_awaited_once_with("wf2")
        # removed from store
        assert await store.get_workflow("cust_test", "wf2") is None


# --- Execute: create/deploy -------------------------------------------------

class TestDeploy:
    async def test_missing_params_trigger_clarification(self, specialist, ctx):
        """'set up a hubspot report' finds the template but lacks recipient
        and cron — EA needs to ask."""
        result = await specialist.execute_task(
            _task("set up a hubspot pipeline report", ctx)
        )
        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        # clarification mentions what's needed
        q = result.clarification_question.lower()
        assert "email" in q or "recipient" in q or "cron" in q or "when" in q
        # payload carries state so the multi-turn can resume
        assert result.payload.get("template_id") == "hubspot_weekly"

    async def test_full_params_deploy(self, specialist, n8n_client, store, ctx):
        """Prior turns carry the answers → deploy succeeds."""
        prior = [
            {"role": "assistant", "content": "What email should I send to?"},
            {"role": "user", "content": "exec@acme.co"},
            {"role": "assistant", "content": "When should it run?"},
            {"role": "user", "content": "every Monday at 9am"},
        ]
        result = await specialist.execute_task(
            _task("set up a hubspot pipeline report", ctx, prior_turns=prior)
        )
        assert result.status == SpecialistStatus.COMPLETED
        n8n_client.create_workflow.assert_awaited_once()
        n8n_client.activate_workflow.assert_awaited_once_with("wf_new")
        # store tracks ownership
        wfs = await store.list_workflows("cust_test")
        assert any(w["workflow_id"] == "wf_new" for w in wfs)

    async def test_no_template_match(self, specialist, ctx):
        """Catalog has nothing for 'mine bitcoin' — fail cleanly."""
        result = await specialist.execute_task(
            _task("set up automatic bitcoin mining", ctx)
        )
        assert result.status == SpecialistStatus.FAILED
        assert "template" in result.error.lower() or \
               "find" in result.error.lower()


# --- Execute: n8n not configured --------------------------------------------

class TestNoConfig:
    async def test_no_n8n_config_fails_gracefully(self, store, catalog, ctx):
        """Customer without n8n config → can't deploy. Clear error."""
        spec = WorkflowSpecialist(
            store=store, catalog=catalog,
            n8n_client_factory=lambda **_: AsyncMock(),
        )
        result = await spec.execute_task(
            _task("what automations do I have?", ctx)
        )
        # List works without n8n (reads store), but we still want an empty
        # result since nothing's been deployed.
        assert result.status == SpecialistStatus.COMPLETED
        assert result.payload["workflows"] == []


# --- Domain property --------------------------------------------------------

class TestContract:
    def test_domain_is_workflows(self):
        assert WorkflowSpecialist().domain == "workflows"

    def test_default_construction_works(self):
        """No-arg constructor so EA registration loop can instantiate it.
        Seams default to None; execute degrades gracefully."""
        spec = WorkflowSpecialist()
        assert spec.domain == "workflows"


# --- EA registration --------------------------------------------------------

class TestEARegistration:
    """Proves the framework needs zero modification for a fourth domain."""

    def test_workflow_specialist_registered_in_ea(self):
        from unittest.mock import patch
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory"), \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"):
            from src.agents.executive_assistant import ExecutiveAssistant
            ea = ExecutiveAssistant(customer_id="c")
            assert ea.delegation_registry.get("workflows") is not None
