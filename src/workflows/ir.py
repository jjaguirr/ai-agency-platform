"""
Workflow intermediate representation.

The EA reasons about workflows at this level: "a thing that fires on a
trigger and runs steps in order, with some knobs to turn." The n8n JSON
shape — node positions, typeVersions, connection-pin indexing — is a
rendering concern that lives in renderer.py.

Keeping the IR narrow (cron/webhook/manual triggers, a handful of action
kinds) means the renderer stays small. Adding an action kind is one
entry in _ACTION_KINDS here plus one clause in the renderer — no
specialist changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


_TRIGGER_KINDS = frozenset({"cron", "webhook", "manual"})
_ACTION_KINDS = frozenset({"http_request", "email", "slack", "set", "code"})


@dataclass(frozen=True)
class TriggerNode:
    kind: str
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in _TRIGGER_KINDS:
            raise ValueError(
                f"unknown trigger kind '{self.kind}', "
                f"expected one of {sorted(_TRIGGER_KINDS)}"
            )


@dataclass(frozen=True)
class ActionNode:
    kind: str
    name: str
    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in _ACTION_KINDS:
            raise ValueError(
                f"unknown action kind '{self.kind}', "
                f"expected one of {sorted(_ACTION_KINDS)}"
            )


@dataclass(frozen=True)
class ParameterSpec:
    """Describes one knob the executive turns during customization.

    node_path locates where the value lands in the rendered workflow:
      "Send Report.to"       → step named "Send Report", config key "to"
      "__trigger__.expression" → trigger config key "expression"
    """
    name: str
    description: str
    required: bool
    node_path: str


@dataclass
class WorkflowDefinition:
    name: str
    description: str
    trigger: TriggerNode
    steps: List[ActionNode]
    parameters: Dict[str, ParameterSpec] = field(default_factory=dict)

    def required_params(self) -> List[str]:
        return [name for name, spec in self.parameters.items() if spec.required]
