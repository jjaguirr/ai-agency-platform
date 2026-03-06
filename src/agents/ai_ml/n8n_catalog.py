"""
Static catalog mapping parsed steps to n8n node types.

~10 node types. Unknown services fall back to httpRequest with a
{{CONFIGURE:}} marker in the URL — structurally valid, obviously unfinished.
The resolver has strict precedence because one step can signal multiple
things (a Stripe step with a condition is an IF node, not an httpRequest).
"""
from dataclasses import dataclass
from typing import Any, Callable

from .workflow_generator import StepSpec, TriggerSpec


@dataclass(frozen=True)
class NodeSpec:
    n8n_type: str
    type_version: float
    is_trigger: bool = False


# --- param builders ---------------------------------------------------------

def _schedule_params(trigger: TriggerSpec) -> dict[str, Any]:
    cron = trigger.cron or "0 9 * * *"
    return {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}}


def _webhook_params(trigger: TriggerSpec) -> dict[str, Any]:
    path = f"/{trigger.event_source or 'trigger'}"
    return {"path": path, "httpMethod": "POST", "responseMode": "onReceived"}


def _http_params(step: StepSpec) -> dict[str, Any]:
    service = (step.service or "external service").lower()
    return {
        "method": "GET",
        "url": f"{{{{CONFIGURE: {service} endpoint}}}}",
        "authentication": "none",
    }


def _if_params(step: StepSpec) -> dict[str, Any]:
    # n8n IF v2 uses a conditions structure; we emit a placeholder carrying
    # the parsed condition text so the customer knows what comparison to wire.
    return {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": ""},
            "conditions": [{
                "leftValue": f"{{{{CONFIGURE: {step.condition}}}}}",
                "rightValue": "",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        }
    }


def _merge_params(step: StepSpec) -> dict[str, Any]:
    return {"mode": "combine", "combineBy": "combineAll"}


def _set_params(step: StepSpec) -> dict[str, Any]:
    # Carry the action description so the customer knows the intended transform.
    return {
        "mode": "manual",
        "fields": {"values": [{
            "name": "note",
            "type": "string",
            "value": f"TODO: {step.action}",
        }]},
    }


def _email_params(step: StepSpec) -> dict[str, Any]:
    return {
        "fromEmail": "{{CONFIGURE: sender}}",
        "toEmail": "={{ $json.email }}",
        "subject": step.action,
        "emailType": "text",
        "message": "={{ JSON.stringify($json) }}",
    }


def _slack_params(step: StepSpec) -> dict[str, Any]:
    return {
        "resource": "message",
        "operation": "post",
        "channel": "{{CONFIGURE: channel}}",
        "text": f"={{ $json }} — {step.action}",
    }


def _sheets_params(step: StepSpec) -> dict[str, Any]:
    return {
        "operation": "append",
        "documentId": "{{CONFIGURE: spreadsheet id}}",
        "sheetName": "{{CONFIGURE: sheet name}}",
    }


# --- catalog ----------------------------------------------------------------

CATALOG: dict[str, NodeSpec] = {
    "schedule": NodeSpec("n8n-nodes-base.scheduleTrigger", 1.2, is_trigger=True),
    "webhook":  NodeSpec("n8n-nodes-base.webhook",         2.0, is_trigger=True),
    "manual":   NodeSpec("n8n-nodes-base.manualTrigger",   1.0, is_trigger=True),
    "http":     NodeSpec("n8n-nodes-base.httpRequest",     4.2),
    "if":       NodeSpec("n8n-nodes-base.if",              2.0),
    "merge":    NodeSpec("n8n-nodes-base.merge",           3.0),
    "set":      NodeSpec("n8n-nodes-base.set",             3.4),
    "email":    NodeSpec("n8n-nodes-base.emailSend",       2.1),
    "slack":    NodeSpec("n8n-nodes-base.slack",           2.2),
    "sheets":   NodeSpec("n8n-nodes-base.googleSheets",    4.5),
}

_SERVICE_ALIASES: dict[str, str] = {
    "email": "email", "gmail": "email", "smtp": "email",
    "slack": "slack",
    "google sheets": "sheets", "sheets": "sheets", "spreadsheet": "sheets",
}

_STEP_PARAM_BUILDERS: dict[str, Callable[[StepSpec], dict[str, Any]]] = {
    "http": _http_params,
    "if": _if_params,
    "merge": _merge_params,
    "set": _set_params,
    "email": _email_params,
    "slack": _slack_params,
    "sheets": _sheets_params,
}

# Nodes that need customer config even when the service is recognized.
_ALWAYS_NEEDS_CONFIG: dict[str, str] = {
    "email": "Configure SMTP credentials and sender address",
    "slack": "Connect Slack workspace and pick a channel",
    "sheets": "Connect Google account and set spreadsheet ID",
}


# --- resolvers --------------------------------------------------------------

def resolve_trigger(trigger: TriggerSpec) -> tuple[NodeSpec, dict[str, Any]]:
    if trigger.kind == "schedule":
        return CATALOG["schedule"], _schedule_params(trigger)
    if trigger.kind == "webhook":
        return CATALOG["webhook"], _webhook_params(trigger)
    return CATALOG["manual"], {}


def resolve_step(step: StepSpec) -> tuple[NodeSpec, dict[str, Any], list[str]]:
    """
    Returns (node spec, parameters, customization notes).

    Precedence: condition > merge > known service > unknown service (http) > set.
    """
    if step.condition is not None:
        return CATALOG["if"], _if_params(step), []

    if len(step.inputs_from) > 1:
        return CATALOG["merge"], _merge_params(step), []

    if step.service:
        service = step.service.lower()
        catalog_key = _SERVICE_ALIASES.get(service)
        if catalog_key:
            spec = CATALOG[catalog_key]
            params = _STEP_PARAM_BUILDERS[catalog_key](step)
            notes = [_ALWAYS_NEEDS_CONFIG[catalog_key]] if catalog_key in _ALWAYS_NEEDS_CONFIG else []
            return spec, params, notes
        # Unknown service → httpRequest fallback
        return (
            CATALOG["http"],
            _http_params(step),
            [f"Configure {step.service} API endpoint and authentication"],
        )

    return CATALOG["set"], _set_params(step), []
