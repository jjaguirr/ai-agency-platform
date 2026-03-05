"""
Workflow generation from conversational process descriptions.

See docs/plans/2026-03-05-workflow-generation-design.md for the full picture.
This module is stateless: generate() takes a description and returns either a
workflow, a set of clarifying questions, or a template-match signal. The EA's
LangGraph owns the clarification loop.
"""
from typing import Literal

from pydantic import BaseModel, Field


# --- parsed process: LLM structured-output schema ---------------------------
# These models are both the Pydantic schema passed to the LLM and the input
# to the assembler. Keep them tight — every field here is something the model
# has to fill.


class TriggerSpec(BaseModel):
    kind: Literal["schedule", "webhook", "manual"]
    cron: str | None = None
    event_source: str | None = None


class StepSpec(BaseModel):
    action: str
    service: str | None = None
    inputs_from: list[int] = Field(default_factory=list)
    condition: str | None = None


class ParsedProcess(BaseModel):
    trigger: TriggerSpec
    steps: list[StepSpec]
    confidence: float = Field(ge=0.0, le=1.0)
    gaps: list[str] = Field(default_factory=list)


# --- assembly: ParsedProcess -> N8nWorkflow ---------------------------------

import uuid
from collections import defaultdict

from .n8n_schema import N8nConnectionTarget, N8nNode, N8nWorkflow

_SPACING_X = 200
_START_X = 250
_Y = 300


def _node_name(action: str, idx: int, used: set[str]) -> str:
    # n8n keys connections by name; truncate + titlecase, then suffix on collision
    base = action[:40].strip().title() or f"Step {idx}"
    if base not in used:
        return base
    n = 2
    while f"{base} {n}" in used:
        n += 1
    return f"{base} {n}"


def assemble(parsed: ParsedProcess) -> tuple[N8nWorkflow, list[str]]:
    """
    Build an N8nWorkflow from a parsed process. Deterministic, no LLM.

    Wiring: inputs_from non-empty → those steps are the sources. Empty →
    previous node in the list (trigger for step 0). Merge nodes receive each
    source on a distinct input pin.

    Raises pydantic.ValidationError if the result is structurally broken —
    that's a bug in this function, not user input.
    """
    # Deferred: n8n_catalog imports StepSpec/TriggerSpec from this module.
    from .n8n_catalog import resolve_step, resolve_trigger

    nodes: list[N8nNode] = []
    used_names: set[str] = set()
    notes_seen: set[str] = set()
    customization: list[str] = []

    def add_note(note: str) -> None:
        if note not in notes_seen:
            notes_seen.add(note)
            customization.append(note)

    # Trigger
    t_spec, t_params = resolve_trigger(parsed.trigger)
    trigger_name = _node_name("Trigger", -1, used_names)
    used_names.add(trigger_name)
    nodes.append(N8nNode(
        id=str(uuid.uuid4()),
        name=trigger_name,
        type=t_spec.n8n_type,
        typeVersion=t_spec.type_version,
        position=(_START_X, _Y),
        parameters=t_params,
    ))

    # Steps
    step_names: list[str] = []
    step_is_merge: list[bool] = []
    for i, step in enumerate(parsed.steps):
        spec, params, notes = resolve_step(step)
        for note in notes:
            add_note(note)
        name = _node_name(step.action, i, used_names)
        used_names.add(name)
        step_names.append(name)
        step_is_merge.append(spec.n8n_type == "n8n-nodes-base.merge")
        nodes.append(N8nNode(
            id=str(uuid.uuid4()),
            name=name,
            type=spec.n8n_type,
            typeVersion=spec.type_version,
            position=(_START_X + (i + 1) * _SPACING_X, _Y),
            parameters=params,
        ))

    # Connections: accumulate targets per (source, output_pin)
    #   edges[src][out_pin] = [ConnectionTarget, ...]
    edges: dict[str, dict[int, list[N8nConnectionTarget]]] = defaultdict(lambda: defaultdict(list))

    for i, step in enumerate(parsed.steps):
        target = step_names[i]
        if step.inputs_from:
            # Explicit sources. If this is a merge, each source lands on a
            # distinct input pin of the target.
            for pin, src_idx in enumerate(step.inputs_from):
                src = step_names[src_idx]
                input_pin = pin if step_is_merge[i] else 0
                edges[src][0].append(N8nConnectionTarget(node=target, index=input_pin))
        else:
            # Linear default: previous node (trigger for step 0)
            src = step_names[i - 1] if i > 0 else trigger_name
            edges[src][0].append(N8nConnectionTarget(node=target, index=0))

    # Collapse edges into n8n's {"main": [[pin0 targets], [pin1 targets], ...]} shape
    connections: dict[str, dict[str, list[list[N8nConnectionTarget]]]] = {}
    for src, by_pin in edges.items():
        max_pin = max(by_pin.keys())
        pins = [by_pin.get(p, []) for p in range(max_pin + 1)]
        connections[src] = {"main": pins}

    workflow = N8nWorkflow(
        name=(parsed.steps[0].action[:50].title() if parsed.steps else "Generated Workflow"),
        nodes=nodes,
        connections=connections,
    )
    return workflow, customization
