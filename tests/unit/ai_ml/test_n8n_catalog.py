"""
Node catalog: which n8n node type a parsed step becomes, and what parameters
it gets. The resolver has a strict precedence order because a single step can
have multiple signals (a service AND a condition) and we need deterministic
output.
"""
import pytest

from src.agents.ai_ml.n8n_catalog import (
    CATALOG,
    NodeSpec,
    resolve_step,
    resolve_trigger,
)
from src.agents.ai_ml.workflow_generator import StepSpec, TriggerSpec


# --- trigger resolution -----------------------------------------------------

class TestResolveTrigger:
    def test_schedule_with_cron(self):
        spec, params = resolve_trigger(TriggerSpec(kind="schedule", cron="0 17 * * 5"))
        assert spec.n8n_type == "n8n-nodes-base.scheduleTrigger"
        assert spec.is_trigger
        # cron expression surfaces in parameters
        assert "0 17 * * 5" in str(params)

    def test_webhook(self):
        spec, params = resolve_trigger(TriggerSpec(kind="webhook", event_source="stripe"))
        assert spec.n8n_type == "n8n-nodes-base.webhook"
        assert params["httpMethod"] == "POST"

    def test_manual_fallback(self):
        spec, params = resolve_trigger(TriggerSpec(kind="manual"))
        assert spec.n8n_type == "n8n-nodes-base.manualTrigger"
        assert params == {}


# --- step resolution precedence ---------------------------------------------

class TestResolverPrecedence:
    def test_condition_wins_over_service(self):
        # A step that filters Stripe data: the IF-ness matters more than Stripe-ness
        step = StepSpec(action="keep unpaid", service="stripe", condition="amount_paid == 0")
        spec, _, _ = resolve_step(step)
        assert spec.n8n_type == "n8n-nodes-base.if"

    def test_merge_wins_over_service(self):
        # Joining two inputs: the merge-ness matters more than the service
        step = StepSpec(action="cross reference", service="stripe", inputs_from=[0, 1])
        spec, _, _ = resolve_step(step)
        assert spec.n8n_type == "n8n-nodes-base.merge"

    def test_condition_wins_over_merge(self):
        # Both multi-input and conditional — condition takes precedence
        # (this is an odd parse but the rule should still be deterministic)
        step = StepSpec(action="filter joined", condition="x > 0", inputs_from=[0, 1])
        spec, _, _ = resolve_step(step)
        assert spec.n8n_type == "n8n-nodes-base.if"

    def test_known_service_maps_directly(self):
        step = StepSpec(action="notify team", service="slack")
        spec, _, notes = resolve_step(step)
        assert spec.n8n_type == "n8n-nodes-base.slack"
        # slack is known but still needs workspace OAuth — that's a config note,
        # not an httpRequest fallback
        assert len(notes) == 1
        assert "slack" in notes[0].lower()

    def test_email_aliases_resolve_to_emailsend(self):
        for alias in ["email", "gmail", "smtp"]:
            step = StepSpec(action="send", service=alias)
            spec, _, _ = resolve_step(step)
            assert spec.n8n_type == "n8n-nodes-base.emailSend", f"alias {alias}"

    def test_sheets_aliases_resolve(self):
        for alias in ["google sheets", "sheets", "spreadsheet"]:
            step = StepSpec(action="log", service=alias)
            spec, _, _ = resolve_step(step)
            assert spec.n8n_type == "n8n-nodes-base.googleSheets", f"alias {alias}"

    def test_unknown_service_falls_back_to_http(self):
        step = StepSpec(action="fetch appointments", service="calendly")
        spec, params, notes = resolve_step(step)
        assert spec.n8n_type == "n8n-nodes-base.httpRequest"
        assert "calendly" in params["url"].lower()
        assert len(notes) == 1
        assert "calendly" in notes[0].lower()

    def test_unknown_service_case_insensitive(self):
        step = StepSpec(action="fetch", service="Stripe")
        spec, params, _ = resolve_step(step)
        assert spec.n8n_type == "n8n-nodes-base.httpRequest"
        assert "stripe" in params["url"].lower()

    def test_no_service_no_condition_resolves_to_set(self):
        step = StepSpec(action="format the output")
        spec, _, notes = resolve_step(step)
        assert spec.n8n_type == "n8n-nodes-base.set"
        assert notes == []


# --- param builder output ---------------------------------------------------

class TestParamBuilders:
    def test_http_fallback_has_required_fields(self):
        step = StepSpec(action="pull data", service="airtable")
        _, params, _ = resolve_step(step)
        assert "method" in params
        assert "url" in params
        assert "{{CONFIGURE:" in params["url"]  # greppable marker

    def test_if_params_carry_condition(self):
        step = StepSpec(action="check", condition="engagement < last_week * 0.9")
        _, params, _ = resolve_step(step)
        # the condition text should surface somewhere so the customer knows what to wire
        assert "engagement" in str(params)

    def test_merge_params_default_to_combine(self):
        step = StepSpec(action="join", inputs_from=[0, 1])
        _, params, _ = resolve_step(step)
        assert params.get("mode") == "combine"

    def test_email_params_have_placeholders(self):
        step = StepSpec(action="send reschedule link", service="email")
        _, params, notes = resolve_step(step)
        assert "toEmail" in params
        assert "subject" in params
        # email always needs config even though it's a known node
        assert any("email" in n.lower() or "smtp" in n.lower() for n in notes)

    def test_set_params_include_action_description(self):
        # the set node should carry the action text so the customer knows
        # what transform was intended
        step = StepSpec(action="compute week-over-week delta")
        _, params, _ = resolve_step(step)
        assert "week-over-week" in str(params)


# --- catalog completeness ---------------------------------------------------

class TestCatalogStructure:
    def test_all_entries_are_nodespecs(self):
        for key, spec in CATALOG.items():
            assert isinstance(spec, NodeSpec), key
            assert spec.n8n_type.startswith("n8n-nodes-base."), key
            assert spec.type_version > 0, key

    def test_trigger_entries_marked(self):
        assert CATALOG["schedule"].is_trigger
        assert CATALOG["webhook"].is_trigger
        assert CATALOG["manual"].is_trigger
        assert not CATALOG["http"].is_trigger
        assert not CATALOG["if"].is_trigger
