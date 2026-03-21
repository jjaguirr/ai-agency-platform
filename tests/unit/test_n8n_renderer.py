"""
Tests for N8nRenderer: WorkflowDefinition IR -> N8nWorkflow.

Validates that the renderer produces structurally valid n8n workflows
by reusing the existing n8n_catalog resolvers.
"""
from __future__ import annotations

import pytest

from src.agents.ai_ml.n8n_schema import TRIGGER_TYPES, N8nWorkflow
from src.integrations.n8n.models import (
    ActionNode,
    TriggerNode,
    WorkflowDefinition,
)
from src.integrations.n8n.renderer import render


# --- Helpers ----------------------------------------------------------------

def _simple_definition(
    trigger_kind: str = "cron",
    trigger_config: dict | None = None,
    steps: list[ActionNode] | None = None,
    name: str = "Test Workflow",
) -> WorkflowDefinition:
    return WorkflowDefinition(
        name=name,
        description="Test",
        trigger=TriggerNode(
            kind=trigger_kind,
            config=trigger_config or {"cron": "0 9 * * 1"},
        ),
        steps=steps or [ActionNode(type="set")],
        parameters={},
    )


# --- Trigger rendering ------------------------------------------------------

class TestTriggerRendering:
    def test_cron_trigger_produces_schedule_trigger_node(self):
        defn = _simple_definition(trigger_kind="cron", trigger_config={"cron": "0 8 * * *"})
        wf, _ = render(defn)
        triggers = [n for n in wf.nodes if n.type in TRIGGER_TYPES]
        assert len(triggers) == 1
        assert triggers[0].type == "n8n-nodes-base.scheduleTrigger"

    def test_webhook_trigger_produces_webhook_node(self):
        defn = _simple_definition(
            trigger_kind="webhook",
            trigger_config={"path": "/incoming"},
        )
        wf, _ = render(defn)
        triggers = [n for n in wf.nodes if n.type in TRIGGER_TYPES]
        assert triggers[0].type == "n8n-nodes-base.webhook"

    def test_event_trigger_falls_back_to_manual(self):
        defn = _simple_definition(
            trigger_kind="event",
            trigger_config={"event_source": "hubspot"},
        )
        wf, _ = render(defn)
        triggers = [n for n in wf.nodes if n.type in TRIGGER_TYPES]
        assert triggers[0].type == "n8n-nodes-base.manualTrigger"


# --- Step rendering ---------------------------------------------------------

class TestStepRendering:
    def test_linear_steps_produce_connected_chain(self):
        defn = _simple_definition(steps=[
            ActionNode(type="http", service="hubspot"),
            ActionNode(type="set"),
        ])
        wf, _ = render(defn)
        # 1 trigger + 2 steps = 3 nodes
        assert len(wf.nodes) == 3
        # All nodes must be reachable (validated by N8nWorkflow)
        assert isinstance(wf, N8nWorkflow)

    def test_email_step_uses_email_catalog_entry(self):
        defn = _simple_definition(steps=[
            ActionNode(type="email", service="email"),
        ])
        wf, _ = render(defn)
        email_nodes = [n for n in wf.nodes if "email" in n.type.lower()]
        assert len(email_nodes) == 1
        assert email_nodes[0].type == "n8n-nodes-base.emailSend"

    def test_slack_step_uses_slack_catalog_entry(self):
        defn = _simple_definition(steps=[
            ActionNode(type="slack", service="slack"),
        ])
        wf, _ = render(defn)
        slack_nodes = [n for n in wf.nodes if "slack" in n.type.lower()]
        assert len(slack_nodes) == 1

    def test_unknown_service_falls_back_to_http(self):
        defn = _simple_definition(steps=[
            ActionNode(type="http", service="stripe"),
        ])
        wf, notes = render(defn)
        http_nodes = [n for n in wf.nodes if n.type == "n8n-nodes-base.httpRequest"]
        assert len(http_nodes) == 1
        assert any("stripe" in n.lower() for n in notes)


# --- Structural validation --------------------------------------------------

class TestStructuralValidity:
    def test_rendered_workflow_passes_n8n_schema_validation(self):
        """N8nWorkflow's model_validator checks: exactly 1 trigger, no dupes,
        all connections valid, all nodes reachable."""
        defn = _simple_definition(steps=[
            ActionNode(type="http", service="hubspot"),
            ActionNode(type="set"),
            ActionNode(type="email", service="email"),
        ])
        wf, _ = render(defn)
        # If we got here, validation passed. Double-check type.
        assert isinstance(wf, N8nWorkflow)

    def test_customization_notes_include_credentials_reminders(self):
        defn = _simple_definition(steps=[
            ActionNode(type="email", service="email"),
            ActionNode(type="slack", service="slack"),
        ])
        _, notes = render(defn)
        assert any("SMTP" in n or "sender" in n for n in notes)
        assert any("Slack" in n for n in notes)

    def test_workflow_name_from_definition(self):
        defn = _simple_definition(name="My Custom Report")
        wf, _ = render(defn)
        assert wf.name == "My Custom Report"
