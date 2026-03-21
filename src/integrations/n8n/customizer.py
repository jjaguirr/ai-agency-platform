"""
Workflow customizer: substitute parameters in a WorkflowDefinition template.

Walks trigger config, step configs, name, and description, replacing
``{{param_name}}`` placeholders with provided values. Reports missing
required parameters.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from .models import ActionNode, TriggerNode, WorkflowDefinition

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class CustomizationResult:
    definition: WorkflowDefinition
    missing_params: list[str]
    applied_params: list[str]


def _substitute(value: str, params: dict[str, str]) -> tuple[str, set[str]]:
    """Replace {{key}} placeholders in a string. Returns (result, keys_used)."""
    used: set[str] = set()

    def _repl(m: re.Match) -> str:
        key = m.group(1)
        if key in params:
            used.add(key)
            return params[key]
        return m.group(0)  # leave unreplaced

    return _PLACEHOLDER_RE.sub(_repl, value), used


def _substitute_dict(d: dict, params: dict[str, str]) -> tuple[dict, set[str]]:
    """Deep-substitute placeholders in all string values of a dict."""
    result = {}
    all_used: set[str] = set()
    for k, v in d.items():
        if isinstance(v, str):
            new_v, used = _substitute(v, params)
            result[k] = new_v
            all_used |= used
        elif isinstance(v, dict):
            new_v, used = _substitute_dict(v, params)
            result[k] = new_v
            all_used |= used
        else:
            result[k] = v
    return result, all_used


def customize(
    template: WorkflowDefinition, params: dict[str, str],
) -> CustomizationResult:
    """Produce a deployment-ready WorkflowDefinition from a template + params.

    Does not mutate the original template.
    """
    # Build effective params: supplied values + defaults for missing optional
    effective = dict(params)
    for name, spec in template.parameters.items():
        if name not in effective and not spec.required and spec.default is not None:
            effective[name] = spec.default

    applied: set[str] = set()

    # Name and description
    new_name, used = _substitute(template.name, effective)
    applied |= used
    new_desc, used = _substitute(template.description, effective)
    applied |= used

    # Trigger config (deep copy to avoid mutating frozen dataclass's dict)
    new_trigger_config, used = _substitute_dict(copy.deepcopy(template.trigger.config), effective)
    applied |= used
    new_trigger = TriggerNode(kind=template.trigger.kind, config=new_trigger_config)

    # Steps
    new_steps: list[ActionNode] = []
    for step in template.steps:
        new_config, used = _substitute_dict(copy.deepcopy(step.config), effective)
        applied |= used
        new_steps.append(ActionNode(type=step.type, service=step.service, config=new_config))

    # Missing required params
    missing = [
        name for name, spec in template.parameters.items()
        if spec.required and name not in applied
    ]

    return CustomizationResult(
        definition=WorkflowDefinition(
            name=new_name,
            description=new_desc,
            trigger=new_trigger,
            steps=new_steps,
            parameters=template.parameters,
        ),
        missing_params=missing,
        applied_params=sorted(applied),
    )
