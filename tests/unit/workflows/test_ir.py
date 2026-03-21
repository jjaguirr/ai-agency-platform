"""
Workflow intermediate representation.

The IR decouples the EA's understanding of "what a workflow does" from
n8n's node/connection JSON. A WorkflowDefinition is trigger + ordered
steps + parameter specs. The N8nRenderer is one way to serialize it;
others can come later without the specialist changing.

Spec requirement: IR converts to n8n JSON that passes the existing
N8nWorkflow pydantic validator (src/agents/ai_ml/n8n_schema.py).
"""
import pytest

from src.workflows.ir import (
    WorkflowDefinition,
    TriggerNode,
    ActionNode,
    ParameterSpec,
)
from src.workflows.renderer import N8nRenderer
from src.agents.ai_ml.n8n_schema import N8nWorkflow


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def cron_trigger():
    return TriggerNode(kind="cron", config={"expression": "0 9 * * 1"})


@pytest.fixture
def webhook_trigger():
    return TriggerNode(kind="webhook", config={"path": "/hook/abc"})


@pytest.fixture
def http_step():
    return ActionNode(
        kind="http_request",
        name="Fetch Pipeline",
        config={"method": "GET", "url": "https://api.hubspot.com/deals"},
    )


@pytest.fixture
def email_step():
    return ActionNode(
        kind="email",
        name="Send Report",
        config={"to": "exec@acme.co", "subject": "Weekly Pipeline"},
    )


@pytest.fixture
def weekly_report(cron_trigger, http_step, email_step):
    return WorkflowDefinition(
        name="Weekly HubSpot Pipeline",
        description="Email pipeline numbers every Monday",
        trigger=cron_trigger,
        steps=[http_step, email_step],
        parameters={
            "recipient": ParameterSpec(
                name="recipient",
                description="Who gets the report",
                required=True,
                node_path="Send Report.to",
            ),
            "cron": ParameterSpec(
                name="cron",
                description="When to run",
                required=True,
                node_path="__trigger__.expression",
            ),
        },
    )


# --- IR shape ---------------------------------------------------------------

class TestWorkflowDefinition:
    def test_holds_trigger_steps_params(self, weekly_report):
        assert weekly_report.name == "Weekly HubSpot Pipeline"
        assert weekly_report.trigger.kind == "cron"
        assert len(weekly_report.steps) == 2
        assert "recipient" in weekly_report.parameters

    def test_steps_are_ordered(self, weekly_report):
        assert weekly_report.steps[0].name == "Fetch Pipeline"
        assert weekly_report.steps[1].name == "Send Report"

    def test_parameter_spec_knows_where_it_lands(self, weekly_report):
        spec = weekly_report.parameters["recipient"]
        assert spec.node_path == "Send Report.to"
        assert spec.required is True

    def test_required_params_helper(self, weekly_report):
        assert set(weekly_report.required_params()) == {"recipient", "cron"}

    def test_optional_params_excluded_from_required(self, cron_trigger):
        wf = WorkflowDefinition(
            name="x", description="x", trigger=cron_trigger, steps=[],
            parameters={
                "opt": ParameterSpec(name="opt", description="", required=False,
                                     node_path="a.b"),
            },
        )
        assert wf.required_params() == []


class TestTriggerNode:
    def test_cron_trigger(self, cron_trigger):
        assert cron_trigger.kind == "cron"
        assert cron_trigger.config["expression"] == "0 9 * * 1"

    def test_webhook_trigger(self, webhook_trigger):
        assert webhook_trigger.kind == "webhook"

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="trigger kind"):
            TriggerNode(kind="carrier_pigeon", config={})


class TestActionNode:
    def test_holds_name_and_config(self, http_step):
        assert http_step.name == "Fetch Pipeline"
        assert http_step.config["method"] == "GET"

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="action kind"):
            ActionNode(kind="telepathy", name="x", config={})


# --- Renderer ---------------------------------------------------------------

class TestN8nRenderer:
    def test_render_produces_dict(self, weekly_report):
        out = N8nRenderer().render(weekly_report)
        assert isinstance(out, dict)
        assert out["name"] == "Weekly HubSpot Pipeline"

    def test_render_has_one_trigger_node(self, weekly_report):
        out = N8nRenderer().render(weekly_report)
        triggers = [n for n in out["nodes"]
                    if "Trigger" in n["type"] or "cron" in n["type"].lower()]
        assert len(triggers) == 1

    def test_render_node_count_is_trigger_plus_steps(self, weekly_report):
        out = N8nRenderer().render(weekly_report)
        assert len(out["nodes"]) == 1 + len(weekly_report.steps)

    def test_render_cron_expression_lands_in_trigger(self, weekly_report):
        out = N8nRenderer().render(weekly_report)
        trigger = out["nodes"][0]
        # n8n schedule trigger: parameters.rule.interval[0].expression
        rule = trigger["parameters"]["rule"]["interval"][0]
        assert rule["expression"] == "0 9 * * 1"

    def test_render_http_step_becomes_http_request_node(self, weekly_report):
        out = N8nRenderer().render(weekly_report)
        http = next(n for n in out["nodes"] if n["name"] == "Fetch Pipeline")
        assert http["type"] == "n8n-nodes-base.httpRequest"
        assert http["parameters"]["url"] == "https://api.hubspot.com/deals"

    def test_render_email_step_becomes_email_send_node(self, weekly_report):
        out = N8nRenderer().render(weekly_report)
        email = next(n for n in out["nodes"] if n["name"] == "Send Report")
        assert email["type"] == "n8n-nodes-base.emailSend"
        assert email["parameters"]["toEmail"] == "exec@acme.co"

    def test_render_connections_chain_linearly(self, weekly_report):
        out = N8nRenderer().render(weekly_report)
        conns = out["connections"]
        # trigger → step[0] → step[1]
        trigger_name = out["nodes"][0]["name"]
        assert conns[trigger_name]["main"][0][0]["node"] == "Fetch Pipeline"
        assert conns["Fetch Pipeline"]["main"][0][0]["node"] == "Send Report"
        # terminal step has no outgoing
        assert "Send Report" not in conns

    def test_render_output_passes_n8n_schema(self, weekly_report):
        """The whole point of the renderer: output is importable."""
        out = N8nRenderer().render(weekly_report)
        validated = N8nWorkflow.model_validate(out)
        assert validated.name == weekly_report.name

    def test_render_webhook_trigger(self, webhook_trigger, http_step):
        wf = WorkflowDefinition(
            name="Hook", description="", trigger=webhook_trigger,
            steps=[http_step], parameters={},
        )
        out = N8nRenderer().render(wf)
        trig = out["nodes"][0]
        assert trig["type"] == "n8n-nodes-base.webhook"
        N8nWorkflow.model_validate(out)  # still valid

    def test_render_zero_steps_is_valid(self, cron_trigger):
        """Trigger alone is a legal workflow (just fires)."""
        wf = WorkflowDefinition(
            name="Lonely", description="", trigger=cron_trigger,
            steps=[], parameters={},
        )
        out = N8nRenderer().render(wf)
        N8nWorkflow.model_validate(out)
        assert out["connections"] == {}

    def test_render_is_inactive_by_default(self, weekly_report):
        """Deployment activates; renderer emits inactive so create+activate
        are two discrete API calls."""
        out = N8nRenderer().render(weekly_report)
        assert out["active"] is False
