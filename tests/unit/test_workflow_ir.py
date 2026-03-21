"""
Tests for the Workflow IR models.

These models are the intermediate representation for template-based workflows,
distinct from ParsedProcess (which models LLM-parsed free-text descriptions).
"""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError

import pytest

from src.integrations.n8n.models import (
    ActionNode,
    ParameterSpec,
    TriggerNode,
    WorkflowDefinition,
)


# --- ParameterSpec ----------------------------------------------------------

class TestParameterSpec:
    def test_required_fields(self):
        p = ParameterSpec(name="email", type="email", description="Recipient")
        assert p.name == "email"
        assert p.type == "email"
        assert p.description == "Recipient"
        assert p.required is True
        assert p.default is None

    def test_optional_with_default(self):
        p = ParameterSpec(
            name="limit", type="number", description="Row limit",
            required=False, default="100",
        )
        assert p.required is False
        assert p.default == "100"

    def test_frozen(self):
        p = ParameterSpec(name="x", type="string", description="d")
        with pytest.raises(FrozenInstanceError):
            p.name = "y"


# --- TriggerNode ------------------------------------------------------------

class TestTriggerNode:
    def test_cron_trigger(self):
        t = TriggerNode(kind="cron", config={"cron": "0 9 * * 1"})
        assert t.kind == "cron"
        assert t.config["cron"] == "0 9 * * 1"

    def test_webhook_trigger(self):
        t = TriggerNode(kind="webhook", config={"path": "/hook"})
        assert t.kind == "webhook"

    def test_frozen(self):
        t = TriggerNode(kind="cron", config={"cron": "* * * * *"})
        with pytest.raises(FrozenInstanceError):
            t.kind = "webhook"


# --- ActionNode -------------------------------------------------------------

class TestActionNode:
    def test_with_service(self):
        a = ActionNode(type="email", service="gmail", config={"to": "a@b.com"})
        assert a.type == "email"
        assert a.service == "gmail"
        assert a.config["to"] == "a@b.com"

    def test_defaults(self):
        a = ActionNode(type="set")
        assert a.service is None
        assert a.config == {}

    def test_frozen(self):
        a = ActionNode(type="http")
        with pytest.raises(FrozenInstanceError):
            a.type = "slack"


# --- WorkflowDefinition ----------------------------------------------------

class TestWorkflowDefinition:
    def test_full_construction(self):
        wd = WorkflowDefinition(
            name="Weekly Report",
            description="Send weekly metrics report",
            trigger=TriggerNode(kind="cron", config={"cron": "0 9 * * 1"}),
            steps=[
                ActionNode(type="http", service="metrics_api", config={"url": "{{api_url}}"}),
                ActionNode(type="email", service="gmail", config={"to": "{{email}}"}),
            ],
            parameters={
                "email": ParameterSpec(name="email", type="email", description="Recipient email"),
                "api_url": ParameterSpec(name="api_url", type="url", description="Metrics endpoint"),
            },
        )
        assert wd.name == "Weekly Report"
        assert len(wd.steps) == 2
        assert len(wd.parameters) == 2

    def test_minimal_construction(self):
        wd = WorkflowDefinition(
            name="Simple",
            description="Minimal",
            trigger=TriggerNode(kind="webhook", config={}),
            steps=[ActionNode(type="set")],
            parameters={},
        )
        assert wd.name == "Simple"
        assert len(wd.steps) == 1
