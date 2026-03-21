"""
Tests for WorkflowCustomizer: parameter substitution on IR templates.
"""
from __future__ import annotations

import pytest

from src.integrations.n8n.customizer import customize
from src.integrations.n8n.models import (
    ActionNode,
    ParameterSpec,
    TriggerNode,
    WorkflowDefinition,
)


# --- Helpers ----------------------------------------------------------------

def _report_template() -> WorkflowDefinition:
    return WorkflowDefinition(
        name="{{report_name}}",
        description="Weekly report to {{email}}",
        trigger=TriggerNode(kind="cron", config={"cron": "{{schedule}}"}),
        steps=[
            ActionNode(type="http", service="metrics", config={"url": "{{api_url}}"}),
            ActionNode(type="email", service="email", config={"to": "{{email}}"}),
        ],
        parameters={
            "report_name": ParameterSpec(
                name="report_name", type="string", description="Report title",
            ),
            "email": ParameterSpec(
                name="email", type="email", description="Recipient email",
            ),
            "schedule": ParameterSpec(
                name="schedule", type="cron", description="Cron schedule",
            ),
            "api_url": ParameterSpec(
                name="api_url", type="url", description="Metrics API URL",
                required=False, default="https://api.example.com/metrics",
            ),
        },
    )


# --- Tests ------------------------------------------------------------------

class TestCustomize:
    def test_replaces_cron_parameter(self):
        result = customize(_report_template(), {
            "report_name": "Sales Report",
            "email": "ceo@co.com",
            "schedule": "0 9 * * 1",
        })
        assert result.definition.trigger.config["cron"] == "0 9 * * 1"
        assert result.definition.trigger.kind == "cron"

    def test_replaces_email_in_step_config(self):
        result = customize(_report_template(), {
            "report_name": "Sales Report",
            "email": "ceo@co.com",
            "schedule": "0 9 * * 1",
        })
        assert result.definition.steps[1].config["to"] == "ceo@co.com"

    def test_replaces_name_and_description(self):
        result = customize(_report_template(), {
            "report_name": "Sales Report",
            "email": "ceo@co.com",
            "schedule": "0 9 * * 1",
        })
        assert result.definition.name == "Sales Report"
        assert "ceo@co.com" in result.definition.description

    def test_reports_missing_required_params(self):
        result = customize(_report_template(), {"report_name": "X"})
        assert "email" in result.missing_params
        assert "schedule" in result.missing_params
        assert "api_url" not in result.missing_params  # optional

    def test_uses_defaults_for_optional_params(self):
        result = customize(_report_template(), {
            "report_name": "R",
            "email": "a@b.com",
            "schedule": "* * * * *",
        })
        # api_url was not provided but has a default
        assert result.definition.steps[0].config["url"] == "https://api.example.com/metrics"
        assert "api_url" not in result.missing_params

    def test_returns_all_applied_params(self):
        result = customize(_report_template(), {
            "report_name": "R",
            "email": "a@b.com",
            "schedule": "0 9 * * 1",
            "api_url": "https://custom.api/v1",
        })
        assert set(result.applied_params) == {"report_name", "email", "schedule", "api_url"}

    def test_with_no_placeholders_is_noop(self):
        defn = WorkflowDefinition(
            name="Static",
            description="No params",
            trigger=TriggerNode(kind="cron", config={"cron": "0 9 * * *"}),
            steps=[ActionNode(type="set", config={"value": "hello"})],
            parameters={},
        )
        result = customize(defn, {})
        assert result.definition.name == "Static"
        assert result.missing_params == []

    def test_does_not_mutate_original_template(self):
        template = _report_template()
        original_cron = template.trigger.config["cron"]
        original_trigger_config_id = id(template.trigger.config)
        original_step_config_id = id(template.steps[0].config)
        result = customize(template, {
            "report_name": "Changed",
            "email": "new@co.com",
            "schedule": "0 0 * * *",
        })
        # Original template values unchanged
        assert template.trigger.config["cron"] == original_cron
        assert template.name == "{{report_name}}"
        # Result trigger config is a different dict object (deep copy)
        assert id(result.definition.trigger.config) != original_trigger_config_id
        assert id(result.definition.steps[0].config) != original_step_config_id
