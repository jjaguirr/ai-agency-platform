"""
Pydantic models for n8n workflow JSON with structural validation.

n8n's import accepts a fairly loose shape, but broken connections or duplicate
node names fail silently or produce unrunnable workflows. These validators
catch the classes of error an LLM-driven assembler can realistically produce:
wiring to a misspelled node name, forgetting to connect a node, emitting two
triggers. They do NOT validate node parameter semantics — that's per-node-type
and out of scope.

Reference shape: docs/architecture/LAUNCH-Bot-Architecture.md:137-280
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TRIGGER_TYPES: frozenset[str] = frozenset({
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.cron",
})


class N8nNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    type: str
    typeVersion: float
    position: tuple[int, int]
    parameters: dict[str, Any] = Field(default_factory=dict)


class N8nConnectionTarget(BaseModel):
    node: str
    type: Literal["main"] = "main"
    index: int = 0


# n8n connection shape:
#   connections[source_name]["main"][output_idx] = [target, target, ...]
# The outer list indexes output pins (IF nodes have main[0]=true, main[1]=false).
# The inner list is fan-out from that pin.
N8nConnections = dict[str, dict[str, list[list[N8nConnectionTarget]]]]


class N8nWorkflow(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    nodes: list[N8nNode]
    connections: N8nConnections = Field(default_factory=dict)
    active: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_structure(self) -> "N8nWorkflow":
        names = [n.name for n in self.nodes]
        name_set = set(names)

        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate node names: {sorted(dupes)}")

        triggers = [n for n in self.nodes if n.type in TRIGGER_TYPES]
        if len(triggers) != 1:
            raise ValueError(
                f"workflow must have exactly one trigger node, found {len(triggers)}"
            )

        for source, ports in self.connections.items():
            if source not in name_set:
                raise ValueError(f"connection source '{source}' is not a node")
            for output_pins in ports.values():
                for pin in output_pins:
                    for target in pin:
                        if target.node not in name_set:
                            raise ValueError(
                                f"connection target '{target.node}' is not a node"
                            )

        # Reachability: BFS from the trigger, every non-trigger node must be visited.
        trigger_name = triggers[0].name
        reachable = {trigger_name}
        frontier = [trigger_name]
        while frontier:
            current = frontier.pop()
            for output_pins in self.connections.get(current, {}).values():
                for pin in output_pins:
                    for target in pin:
                        if target.node not in reachable:
                            reachable.add(target.node)
                            frontier.append(target.node)

        unreachable = name_set - reachable
        if unreachable:
            raise ValueError(f"unreachable nodes: {sorted(unreachable)}")

        return self
