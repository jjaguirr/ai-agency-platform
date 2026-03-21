"""
WorkflowCustomizer — parameter substitution into a raw template.

Input: raw n8n JSON template with {{CONFIGURE: ...}} placeholders.
Output: deployable JSON with placeholders replaced by customer values.

Two contract obligations:
  - identify_missing() returns what the EA needs to ask for
  - apply() refuses to produce output until every required param is filled
"""
import copy

import pytest

from src.workflows.customizer import WorkflowCustomizer, IncompleteCustomizationError


# --- Template fixture -------------------------------------------------------

@pytest.fixture
def report_template():
    """Mirrors templates/n8n/report_generation.json shape —
    {{CONFIGURE: label}} placeholders in string parameters."""
    return {
        "name": "Weekly Business Report",
        "nodes": [
            {
                "id": "schedule", "name": "Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2, "position": [0, 0],
                "parameters": {
                    "rule": {"interval": [
                        {"field": "cronExpression",
                         "expression": "{{CONFIGURE: cron schedule}}"}
                    ]}
                },
            },
            {
                "id": "fetch", "name": "Fetch",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2, "position": [200, 0],
                "parameters": {
                    "method": "GET",
                    "url": "{{CONFIGURE: metrics API endpoint}}",
                },
            },
            {
                "id": "email", "name": "Email",
                "type": "n8n-nodes-base.emailSend",
                "typeVersion": 2.1, "position": [400, 0],
                "parameters": {
                    "toEmail": "{{CONFIGURE: recipient email}}",
                    "fromEmail": "reports@platform.co",  # NOT a placeholder
                    "subject": "Weekly Report",
                },
            },
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Fetch", "type": "main", "index": 0}]]},
            "Fetch": {"main": [[{"node": "Email", "type": "main", "index": 0}]]},
        },
        "active": False,
        "settings": {},
    }


@pytest.fixture
def customizer(report_template):
    return WorkflowCustomizer(report_template)


# --- Placeholder discovery --------------------------------------------------

class TestIdentifyMissing:
    def test_finds_all_placeholders(self, customizer):
        missing = customizer.identify_missing({})
        assert set(missing) == {
            "cron schedule", "metrics API endpoint", "recipient email"
        }

    def test_excludes_already_provided(self, customizer):
        missing = customizer.identify_missing({
            "cron schedule": "0 9 * * 1",
            "recipient email": "exec@acme.co",
        })
        assert missing == ["metrics API endpoint"]

    def test_empty_when_all_provided(self, customizer):
        missing = customizer.identify_missing({
            "cron schedule": "0 9 * * 1",
            "metrics API endpoint": "https://api.x.co/metrics",
            "recipient email": "exec@acme.co",
        })
        assert missing == []

    def test_non_placeholder_values_not_reported(self, customizer):
        """fromEmail has a real value, not a placeholder — never 'missing'."""
        missing = customizer.identify_missing({})
        assert "reports@platform.co" not in missing
        assert "fromEmail" not in missing

    def test_no_placeholders_template(self):
        t = {"name": "Static", "nodes": [
            {"id": "x", "name": "X", "type": "n8n-nodes-base.manualTrigger",
             "typeVersion": 1, "position": [0, 0], "parameters": {"foo": "bar"}}
        ], "connections": {}}
        assert WorkflowCustomizer(t).identify_missing({}) == []


# --- Apply ------------------------------------------------------------------

class TestApply:
    def test_substitutes_placeholders(self, customizer):
        out = customizer.apply({
            "cron schedule": "0 9 * * 1",
            "metrics API endpoint": "https://api.x.co/metrics",
            "recipient email": "exec@acme.co",
        })
        email_node = next(n for n in out["nodes"] if n["name"] == "Email")
        assert email_node["parameters"]["toEmail"] == "exec@acme.co"
        fetch_node = next(n for n in out["nodes"] if n["name"] == "Fetch")
        assert fetch_node["parameters"]["url"] == "https://api.x.co/metrics"

    def test_nested_placeholder_substituted(self, customizer):
        """cron is buried in parameters.rule.interval[0].expression."""
        out = customizer.apply({
            "cron schedule": "0 9 * * 1",
            "metrics API endpoint": "https://api.x.co/m",
            "recipient email": "e@x.co",
        })
        trig = next(n for n in out["nodes"] if n["name"] == "Trigger")
        assert trig["parameters"]["rule"]["interval"][0]["expression"] == "0 9 * * 1"

    def test_raises_when_required_missing(self, customizer):
        with pytest.raises(IncompleteCustomizationError) as exc:
            customizer.apply({"cron schedule": "0 9 * * 1"})
        # error names what's missing so the EA can ask
        msg = str(exc.value)
        assert "metrics API endpoint" in msg
        assert "recipient email" in msg

    def test_does_not_mutate_original_template(self, customizer, report_template):
        original = copy.deepcopy(report_template)
        customizer.apply({
            "cron schedule": "0 9 * * 1",
            "metrics API endpoint": "https://x",
            "recipient email": "e@x.co",
        })
        assert report_template == original

    def test_preserves_non_placeholder_fields(self, customizer):
        out = customizer.apply({
            "cron schedule": "0 9 * * 1",
            "metrics API endpoint": "https://x",
            "recipient email": "e@x.co",
        })
        email = next(n for n in out["nodes"] if n["name"] == "Email")
        assert email["parameters"]["fromEmail"] == "reports@platform.co"
        assert email["parameters"]["subject"] == "Weekly Report"

    def test_preserves_structure(self, customizer):
        """Connections, settings, positions — all untouched."""
        out = customizer.apply({
            "cron schedule": "0 9 * * 1",
            "metrics API endpoint": "https://x",
            "recipient email": "e@x.co",
        })
        assert out["connections"] == {
            "Trigger": {"main": [[{"node": "Fetch", "type": "main", "index": 0}]]},
            "Fetch": {"main": [[{"node": "Email", "type": "main", "index": 0}]]},
        }
        assert out["active"] is False

    def test_custom_name_override(self, customizer):
        """Customer's instance gets their own name, not the template's."""
        out = customizer.apply(
            {"cron schedule": "x", "metrics API endpoint": "y", "recipient email": "z"},
            name="Jose's Monday Report",
        )
        assert out["name"] == "Jose's Monday Report"
