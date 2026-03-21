"""
Workflow intermediate representation.

Template-oriented abstraction for workflows where the structure is known and
parameters need customization. Distinct from ``ParsedProcess`` in
``workflow_generator.py`` which models LLM-parsed free-text descriptions.
The two converge at ``N8nWorkflow`` via different paths (renderer vs assembler).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParameterSpec:
    """A customizable parameter in a workflow template."""

    name: str
    type: str  # "string", "cron", "email", "url", "number"
    description: str
    required: bool = True
    default: str | None = None


@dataclass(frozen=True)
class TriggerNode:
    """Workflow trigger: cron, webhook, or event."""

    kind: str  # "cron", "webhook", "event"
    config: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ActionNode:
    """A single step in the workflow execution chain."""

    type: str  # "http", "email", "slack", "sheets", "set", "if"
    service: str | None = None
    config: dict = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    """Complete workflow IR ready for rendering or customization."""

    name: str
    description: str
    trigger: TriggerNode
    steps: list[ActionNode]
    parameters: dict[str, ParameterSpec]
