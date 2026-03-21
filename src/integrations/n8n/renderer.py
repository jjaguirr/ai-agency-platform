"""
Render WorkflowDefinition IR into n8n-importable JSON.

Reuses the existing n8n_catalog resolvers (resolve_trigger, resolve_step)
and produces an N8nWorkflow that passes structural validation.
"""
from __future__ import annotations

import uuid

from src.agents.ai_ml.n8n_catalog import resolve_step, resolve_trigger
from src.agents.ai_ml.n8n_schema import N8nConnectionTarget, N8nNode, N8nWorkflow
from src.agents.ai_ml.workflow_generator import StepSpec, TriggerSpec

from .models import WorkflowDefinition

_SPACING_X = 200
_START_X = 250
_Y = 300


def _unique_name(base: str, used: set[str]) -> str:
    name = base[:40].strip().title() or "Step"
    if name not in used:
        return name
    n = 2
    while f"{name} {n}" in used:
        n += 1
    return f"{name} {n}"


def _ir_trigger_to_spec(trigger) -> TriggerSpec:
    """Map IR TriggerNode to the workflow_generator TriggerSpec."""
    kind = trigger.kind
    if kind == "cron":
        return TriggerSpec(kind="schedule", cron=trigger.config.get("cron", "0 9 * * *"))
    if kind == "webhook":
        return TriggerSpec(
            kind="webhook",
            event_source=trigger.config.get("event_source") or trigger.config.get("path"),
        )
    # event / unknown → manual
    return TriggerSpec(kind="manual")


def _ir_step_to_spec(step) -> StepSpec:
    """Map IR ActionNode to the workflow_generator StepSpec."""
    return StepSpec(action=step.type, service=step.service)


def render(definition: WorkflowDefinition) -> tuple[N8nWorkflow, list[str]]:
    """Convert a WorkflowDefinition IR into an n8n-importable workflow.

    Returns (workflow, customization_notes).
    """
    nodes: list[N8nNode] = []
    used_names: set[str] = set()
    notes_seen: set[str] = set()
    customization: list[str] = []

    def add_note(note: str) -> None:
        if note not in notes_seen:
            notes_seen.add(note)
            customization.append(note)

    # Trigger
    t_spec = _ir_trigger_to_spec(definition.trigger)
    catalog_spec, t_params = resolve_trigger(t_spec)
    trigger_name = _unique_name("Trigger", used_names)
    used_names.add(trigger_name)
    nodes.append(N8nNode(
        id=str(uuid.uuid4()),
        name=trigger_name,
        type=catalog_spec.n8n_type,
        typeVersion=catalog_spec.type_version,
        position=(_START_X, _Y),
        parameters=t_params,
    ))

    # Steps
    step_names: list[str] = []
    for i, step in enumerate(definition.steps):
        s_spec = _ir_step_to_spec(step)
        catalog_spec, s_params, notes = resolve_step(s_spec)
        for note in notes:
            add_note(note)
        name = _unique_name(step.service or step.type, used_names)
        used_names.add(name)
        step_names.append(name)
        nodes.append(N8nNode(
            id=str(uuid.uuid4()),
            name=name,
            type=catalog_spec.n8n_type,
            typeVersion=catalog_spec.type_version,
            position=(_START_X + (i + 1) * _SPACING_X, _Y),
            parameters=s_params,
        ))

    # Linear connections: trigger → step0 → step1 → ...
    connections: dict[str, dict[str, list[list[N8nConnectionTarget]]]] = {}
    prev = trigger_name
    for sn in step_names:
        connections[prev] = {"main": [[N8nConnectionTarget(node=sn)]]}
        prev = sn

    return N8nWorkflow(
        name=definition.name,
        nodes=nodes,
        connections=connections,
    ), customization
