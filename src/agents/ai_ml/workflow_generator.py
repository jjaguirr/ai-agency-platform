"""
Workflow generation from conversational process descriptions.

See docs/plans/2026-03-05-workflow-generation-design.md for the full picture.
This module is stateless: generate() takes a description and returns either a
workflow, a set of clarifying questions, or a template-match signal. The EA's
LangGraph owns the clarification loop.
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="after")
    def _check_semantics(self) -> "ParsedProcess":
        # LLM structured output guarantees shape, not sense. Catch the cases
        # that would otherwise crash assemble() or silently produce garbage.
        if self.trigger.kind == "schedule" and not self.trigger.cron:
            raise ValueError("schedule trigger requires cron")
        n = len(self.steps)
        for i, step in enumerate(self.steps):
            for j in step.inputs_from:
                if not (0 <= j < n) or j == i:
                    raise ValueError(
                        f"step {i} inputs_from references invalid step {j}"
                    )
        return self


# --- assembly: ParsedProcess -> N8nWorkflow ---------------------------------

import re
import uuid
from collections import defaultdict

from .n8n_schema import TRIGGER_TYPES, N8nConnectionTarget, N8nNode, N8nWorkflow

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


# --- explain: N8nWorkflow -> plain English ----------------------------------

_CONFIGURE_RE = re.compile(r"\{\{CONFIGURE:\s*(.+?)\}\}")


def _extract_marker(s: str) -> str | None:
    m = _CONFIGURE_RE.search(s)
    return m.group(1).strip() if m else None


def _describe(node: N8nNode) -> str:
    t = node.type
    p = node.parameters
    if t == "n8n-nodes-base.scheduleTrigger":
        return "runs on a schedule"
    if t == "n8n-nodes-base.webhook":
        return "waits for an incoming webhook"
    if t == "n8n-nodes-base.manualTrigger":
        return "runs manually on demand"
    if t == "n8n-nodes-base.httpRequest":
        detail = _extract_marker(p.get("url", ""))
        return f"calls {detail}" if detail else "calls an external API"
    if t == "n8n-nodes-base.if":
        cond = _extract_marker(str(p))
        return f"branches when {cond}" if cond else "checks a condition"
    if t == "n8n-nodes-base.merge":
        return "merges the incoming branches"
    if t == "n8n-nodes-base.set":
        return "transforms the data"
    if t == "n8n-nodes-base.emailSend":
        return "sends an email"
    if t == "n8n-nodes-base.slack":
        return "posts to Slack"
    if t == "n8n-nodes-base.googleSheets":
        return "writes to a spreadsheet"
    return "runs"


def explain(workflow: N8nWorkflow, customization: list[str]) -> str:
    """
    Plain-English numbered walkthrough. Deterministic — no LLM. This is the
    confirmation step shown to the customer before deploy; it must not
    hallucinate.
    """
    by_name = {n.name: n for n in workflow.nodes}
    trigger = next(n for n in workflow.nodes if n.type in TRIGGER_TYPES)

    # BFS from trigger through the connection graph
    order: list[str] = [trigger.name]
    seen = {trigger.name}
    frontier = [trigger.name]
    while frontier:
        current = frontier.pop(0)
        for pin in workflow.connections.get(current, {}).get("main", []):
            for tgt in pin:
                if tgt.node not in seen:
                    seen.add(tgt.node)
                    order.append(tgt.node)
                    frontier.append(tgt.node)

    lines = [
        f"{i}. {name} — {_describe(by_name[name])}"
        for i, name in enumerate(order, 1)
    ]

    if customization:
        lines.append("")
        lines.append("Before this runs:")
        lines.extend(f"- {note}" for note in customization)

    return "\n".join(lines)


# --- result union -----------------------------------------------------------

class Generated(BaseModel):
    workflow: N8nWorkflow
    explanation: str
    customization_required: list[str]


class NeedsClarification(BaseModel):
    questions: list[str]
    partial: ParsedProcess


class UseTemplate(BaseModel):
    # Emitted by WorkflowCreator's template fast-path, not by generate().
    template_id: str
    confidence: float


GenerationResult = Generated | NeedsClarification | UseTemplate


# --- parse: description -> ParsedProcess (LLM) ------------------------------

_CONFIDENCE_THRESHOLD = 0.6


def _build_parse_prompt(
    description: str,
    insights: dict,
    hint: dict | None,
) -> str:
    parts = [
        "Extract the workflow structure from this customer process description.",
        "",
        f"Customer said: {description}",
    ]

    tools = insights.get("tools_mentioned") or []
    if tools:
        parts.append(f"Tools the customer has mentioned: {', '.join(tools)}")

    if hint is not None:
        parts.append("")
        parts.append(
            f"Likely skeleton (use as a starting shape, override where the "
            f"description differs): {hint}"
        )

    parts.extend([
        "",
        "Populate `gaps` with anything you had to guess. If the description "
        "is vague, gaps should be long and confidence near zero.",
    ])
    return "\n".join(parts)


async def parse(
    description: str,
    business_insights: dict,
    template_hint: dict | None,
    llm,
) -> ParsedProcess:
    """Single structured-output LLM call. Caller supplies the model."""
    prompt = _build_parse_prompt(description, business_insights, template_hint)
    structured = llm.with_structured_output(ParsedProcess)
    return await structured.ainvoke(prompt)


# --- generate: orchestrator -------------------------------------------------

async def generate(
    description: str,
    *,
    business_insights: dict | None = None,
    template_hint: dict | None = None,
    llm,
) -> Generated | NeedsClarification:
    """
    Stateless. One call, one result. On NeedsClarification the EA stashes
    the partial, merges the customer's answer into a new description, and
    calls again.
    """
    parsed = await parse(description, business_insights or {}, template_hint, llm)

    # Overconfidence check: model extracted ≤1 step but claims high
    # confidence. Real processes have multiple steps; this is almost
    # certainly under-parsing ("automate my marketing" → 1 vague step).
    suspicious = parsed.confidence > 0.7 and len(parsed.steps) <= 1

    if parsed.gaps or parsed.confidence < _CONFIDENCE_THRESHOLD or suspicious:
        questions = parsed.gaps or [
            "Can you walk me through the process step by step?"
        ]
        return NeedsClarification(questions=questions, partial=parsed)

    workflow, customization = assemble(parsed)
    explanation = explain(workflow, customization)
    return Generated(
        workflow=workflow,
        explanation=explanation,
        customization_required=customization,
    )
