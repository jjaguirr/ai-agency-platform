"""
Tests for workflow specialist enhancements: contextual suggestions.

- List includes failure context from interaction_context
- Deploy suggests related workflows from catalog
- Suggestion respects cooldown
- Topic counting in ProactiveStateStore
- Usage-based suggestion at threshold
- Graceful degradation without context
"""
import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock

from src.agents.base.specialist import SpecialistTask, SpecialistStatus
from src.agents.context import InteractionContext, WorkflowSnapshot, CustomerPreferences
from src.agents.executive_assistant import BusinessContext
from src.agents.specialists.workflows import WorkflowSpecialist
from src.proactive.state import ProactiveStateStore
from src.workflows.store import WorkflowStore
from src.workflows.catalog import WorkflowTemplate


# --- Fixtures ---------------------------------------------------------------

CUSTOMER_ID = "cust_wf_test"


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def proactive_store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def ctx():
    return BusinessContext(
        business_name="Acme Corp",
        industry="saas",
        current_tools=["HubSpot", "Slack", "n8n"],
    )


@pytest.fixture
def wf_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(wf_redis):
    return WorkflowStore(wf_redis)


@pytest.fixture
def n8n_client():
    m = AsyncMock()
    m.create_workflow = AsyncMock(return_value={"id": "wf_new", "name": "Created"})
    m.activate_workflow = AsyncMock()
    m.deactivate_workflow = AsyncMock()
    m.delete_workflow = AsyncMock()
    return m


_HUBSPOT_TEMPLATE = WorkflowTemplate(
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

_SLACK_TEMPLATE = WorkflowTemplate(
    id="slack_alerts",
    name="Slack Alert Pipeline",
    description="Send alerts to Slack channel on events",
    integrations=["slack"],
    category="notifications",
    tags=["alert", "slack", "notification", "report"],
    raw={
        "name": "Slack Alert Pipeline",
        "nodes": [],
        "connections": {},
        "active": False, "settings": {},
    },
    source="local",
)


@pytest.fixture
def catalog():
    m = AsyncMock()
    m.search_local = lambda q: (
        [_HUBSPOT_TEMPLATE]
        if any(k in q.lower() for k in ("hubspot", "pipeline", "report"))
        else [_SLACK_TEMPLATE]
        if any(k in q.lower() for k in ("slack", "alert"))
        else []
    )
    m.list_local = lambda: [_HUBSPOT_TEMPLATE, _SLACK_TEMPLATE]
    m.search_community = AsyncMock(return_value=[])
    return m


@pytest.fixture
async def specialist(store, n8n_client, catalog, proactive_store):
    await store.set_config(CUSTOMER_ID, base_url="http://n8n.test", api_key="k")
    return WorkflowSpecialist(
        store=store,
        catalog=catalog,
        n8n_client_factory=lambda base_url, api_key: n8n_client,
        proactive_state=proactive_store,
    )


def _task(desc, ctx, *, interaction_context=None, prior_turns=None):
    return SpecialistTask(
        description=desc,
        customer_id=CUSTOMER_ID,
        business_context=ctx,
        domain_memories=[],
        prior_turns=prior_turns or [],
        interaction_context=interaction_context,
    )


# --- ProactiveStateStore: topic tracking ------------------------------------

class TestTopicCounting:
    @pytest.mark.asyncio
    async def test_increment_and_get_topic_counts(self, proactive_store):
        await proactive_store.increment_topic_count(CUSTOMER_ID, "reporting")
        await proactive_store.increment_topic_count(CUSTOMER_ID, "reporting")
        await proactive_store.increment_topic_count(CUSTOMER_ID, "alerts")

        counts = await proactive_store.get_topic_counts(CUSTOMER_ID)
        assert counts["reporting"] == 2
        assert counts["alerts"] == 1

    @pytest.mark.asyncio
    async def test_empty_topic_counts(self, proactive_store):
        counts = await proactive_store.get_topic_counts(CUSTOMER_ID)
        assert counts == {}


# --- List: failure context ---------------------------------------------------

class TestListFailureContext:
    @pytest.mark.asyncio
    async def test_list_includes_failure_context(self, specialist, store, ctx):
        """When workflow_snapshot has recent_failures, list summary mentions them."""
        await store.add_workflow(CUSTOMER_ID, "wf1", "Monday Report", "active")

        ic = InteractionContext(
            workflow_snapshot=WorkflowSnapshot(
                active_count=1,
                workflow_names=["Monday Report"],
                recent_failures=[
                    {"name": "Monday Report", "error": "SMTP timeout", "timestamp": "2026-03-20T08:00:00"},
                ],
            ),
        )

        task = _task("what automations do I have?", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        # _failure_note produces "Heads up: recent issues with {names}."
        assert "recent issues" in result.summary_for_ea.lower()
        assert "Monday Report" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_list_no_failure_mention_when_clean(self, specialist, store, ctx):
        """No failures → no failure mention."""
        await store.add_workflow(CUSTOMER_ID, "wf1", "Monday Report", "active")

        ic = InteractionContext(
            workflow_snapshot=WorkflowSnapshot(
                active_count=1,
                workflow_names=["Monday Report"],
                recent_failures=[],
            ),
        )

        task = _task("what automations do I have?", ctx, interaction_context=ic)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        summary_lower = result.summary_for_ea.lower()
        assert "fail" not in summary_lower and "error" not in summary_lower

    @pytest.mark.asyncio
    async def test_list_works_without_context(self, specialist, store, ctx):
        """No interaction_context → existing behavior."""
        await store.add_workflow(CUSTOMER_ID, "wf1", "Monday Report", "active")

        task = _task("what automations do I have?", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "Monday Report" in result.summary_for_ea


# --- Deploy: related suggestions --------------------------------------------

class TestDeploySuggestions:
    @pytest.mark.asyncio
    async def test_deploy_suggests_related_template(self, specialist, ctx, proactive_store):
        """After deploying a report workflow, suggest the related alert workflow."""
        task = _task(
            "send me my HubSpot pipeline every Monday at 9am to user@example.com",
            ctx,
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        # Must contain both: deployment confirmation AND related suggestion
        assert "deployed and active" in result.summary_for_ea.lower()
        assert "you might also like" in result.summary_for_ea.lower()

    @pytest.mark.asyncio
    async def test_deploy_records_cooldown_after_suggestion(self, specialist, ctx, proactive_store):
        """After suggesting a related template, cooldown is recorded."""
        task = _task(
            "send me my HubSpot pipeline every Monday at 9am to user@example.com",
            ctx,
        )
        await specialist.execute_task(task)

        # The suggested template should now be cooling down
        # HubSpot template shares "report"/"weekly" tags — one of the other templates
        # got suggested; check that its cooldown key was set
        is_cooling = await proactive_store.is_cooling_down(
            CUSTOMER_ID, "wf_suggest:slack_alerts",
        )
        assert is_cooling

    @pytest.mark.asyncio
    async def test_suggestion_respects_cooldown(self, specialist, ctx, proactive_store):
        """If we already suggested a template recently, don't suggest again."""
        # Pre-set cooldown for the slack template
        await proactive_store.record_cooldown(
            CUSTOMER_ID, "wf_suggest:slack_alerts", 86400,
        )

        task = _task(
            "send me my HubSpot pipeline every Monday at 9am to user@example.com",
            ctx,
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        # Should NOT suggest — all other templates are cooling down
        assert "you might also like" not in result.summary_for_ea.lower()


# --- Graceful degradation ---------------------------------------------------

class TestSuggestionError:
    @pytest.mark.asyncio
    async def test_catalog_error_in_suggest_does_not_crash_deploy(
        self, store, n8n_client, proactive_store, ctx,
    ):
        """If catalog.list_local() raises during suggestion, deploy still succeeds."""
        await store.set_config(CUSTOMER_ID, base_url="http://n8n.test", api_key="k")

        broken_catalog = AsyncMock()
        broken_catalog.search_local = lambda q: [_HUBSPOT_TEMPLATE]
        broken_catalog.list_local = lambda: (_ for _ in ()).throw(RuntimeError("catalog broken"))
        broken_catalog.search_community = AsyncMock(return_value=[])

        specialist = WorkflowSpecialist(
            store=store,
            catalog=broken_catalog,
            n8n_client_factory=lambda base_url, api_key: n8n_client,
            proactive_state=proactive_store,
        )
        task = _task(
            "send me my HubSpot pipeline every Monday at 9am to user@example.com",
            ctx,
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        # Deploy succeeded but no suggestion (error swallowed)
        assert "deployed and active" in result.summary_for_ea.lower()
        assert "you might also like" not in result.summary_for_ea.lower()


class TestWorkflowGracefulDegradation:
    @pytest.mark.asyncio
    async def test_list_works_without_proactive_state(self, store, n8n_client, catalog, ctx):
        """No proactive_state → list still works."""
        await store.set_config(CUSTOMER_ID, base_url="http://n8n.test", api_key="k")
        await store.add_workflow(CUSTOMER_ID, "wf1", "Monday Report", "active")

        specialist = WorkflowSpecialist(
            store=store,
            catalog=catalog,
            n8n_client_factory=lambda base_url, api_key: n8n_client,
        )
        task = _task("what automations do I have?", ctx)
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
        assert "Monday Report" in result.summary_for_ea

    @pytest.mark.asyncio
    async def test_deploy_without_proactive_state(self, store, n8n_client, catalog, ctx):
        """No proactive_state → deploy still works, no suggestion crash."""
        await store.set_config(CUSTOMER_ID, base_url="http://n8n.test", api_key="k")

        specialist = WorkflowSpecialist(
            store=store,
            catalog=catalog,
            n8n_client_factory=lambda base_url, api_key: n8n_client,
        )
        task = _task(
            "send me my HubSpot pipeline every Monday at 9am to user@example.com",
            ctx,
        )
        result = await specialist.execute_task(task)

        assert result.status == SpecialistStatus.COMPLETED
