"""
Structural validation for generated n8n workflows.

The validator is the gate between the assembler and the customer. If it passes,
the JSON is importable into n8n. These tests define what "importable" means in
practice: unique names (connections key by name), every wire points somewhere
real, exactly one trigger, nothing orphaned.
"""
import pytest
from pydantic import ValidationError

from src.agents.ai_ml.n8n_schema import N8nNode, N8nWorkflow, TRIGGER_TYPES


def node(name, type="n8n-nodes-base.set", pos_x=250):
    return N8nNode(
        id=f"id-{name}",
        name=name,
        type=type,
        typeVersion=1.0,
        position=(pos_x, 300),
        parameters={},
    )


def trigger(name="Trigger"):
    return node(name, type="n8n-nodes-base.manualTrigger")


def connect(source, target, output_index=0):
    """One wire: source.main[output_index] -> target.main[0]"""
    return {source: {"main": [[{"node": target, "type": "main", "index": 0}]] if output_index == 0
                     else [[] for _ in range(output_index)] + [[{"node": target, "type": "main", "index": 0}]]}}


# --- happy path -------------------------------------------------------------

class TestValidWorkflows:
    def test_minimal_linear_chain_validates(self):
        wf = N8nWorkflow(
            name="Minimal",
            nodes=[trigger(), node("Step")],
            connections=connect("Trigger", "Step"),
        )
        assert len(wf.nodes) == 2

    def test_three_node_chain_validates(self):
        wf = N8nWorkflow(
            name="Chain",
            nodes=[trigger(), node("A"), node("B")],
            connections={
                "Trigger": {"main": [[{"node": "A", "type": "main", "index": 0}]]},
                "A": {"main": [[{"node": "B", "type": "main", "index": 0}]]},
            },
        )
        assert wf.name == "Chain"

    def test_branch_and_merge_validates(self):
        # Trigger -> A -> {B, C} -> D
        wf = N8nWorkflow(
            name="Diamond",
            nodes=[trigger(), node("A"), node("B"), node("C"), node("D")],
            connections={
                "Trigger": {"main": [[{"node": "A", "type": "main", "index": 0}]]},
                "A": {"main": [[{"node": "B", "type": "main", "index": 0},
                                {"node": "C", "type": "main", "index": 0}]]},
                "B": {"main": [[{"node": "D", "type": "main", "index": 0}]]},
                "C": {"main": [[{"node": "D", "type": "main", "index": 0}]]},
            },
        )
        assert len(wf.nodes) == 5

    def test_if_node_two_output_branches_validates(self):
        # IF has main[0]=true, main[1]=false
        wf = N8nWorkflow(
            name="Conditional",
            nodes=[trigger(), node("Check", type="n8n-nodes-base.if"),
                   node("YesPath"), node("NoPath")],
            connections={
                "Trigger": {"main": [[{"node": "Check", "type": "main", "index": 0}]]},
                "Check": {"main": [
                    [{"node": "YesPath", "type": "main", "index": 0}],
                    [{"node": "NoPath", "type": "main", "index": 0}],
                ]},
            },
        )
        assert len(wf.connections["Check"]["main"]) == 2

    def test_trigger_only_workflow_validates(self):
        # Degenerate but legal — trigger with no downstream nodes
        wf = N8nWorkflow(name="TriggerOnly", nodes=[trigger()], connections={})
        assert len(wf.nodes) == 1


# --- structural violations --------------------------------------------------

class TestDuplicateNames:
    def test_duplicate_node_names_rejected(self):
        with pytest.raises(ValidationError, match="duplicate"):
            N8nWorkflow(
                name="Dup",
                nodes=[trigger(), node("Same"), node("Same")],
                connections=connect("Trigger", "Same"),
            )


class TestConnectionIntegrity:
    def test_connection_source_not_a_node_rejected(self):
        with pytest.raises(ValidationError, match="Ghost"):
            N8nWorkflow(
                name="BadSource",
                nodes=[trigger(), node("Real")],
                connections={
                    "Trigger": {"main": [[{"node": "Real", "type": "main", "index": 0}]]},
                    "Ghost": {"main": [[{"node": "Real", "type": "main", "index": 0}]]},
                },
            )

    def test_connection_target_not_a_node_rejected(self):
        with pytest.raises(ValidationError, match="Nowhere"):
            N8nWorkflow(
                name="BadTarget",
                nodes=[trigger(), node("Real")],
                connections={
                    "Trigger": {"main": [[{"node": "Nowhere", "type": "main", "index": 0}]]},
                },
            )


class TestTriggerCardinality:
    def test_zero_triggers_rejected(self):
        with pytest.raises(ValidationError, match="trigger"):
            N8nWorkflow(
                name="NoTrigger",
                nodes=[node("A"), node("B")],
                connections=connect("A", "B"),
            )

    def test_two_triggers_rejected(self):
        with pytest.raises(ValidationError, match="trigger"):
            N8nWorkflow(
                name="TwoTriggers",
                nodes=[trigger("T1"), trigger("T2"), node("A")],
                connections=connect("T1", "A"),
            )

    def test_schedule_trigger_recognized(self):
        assert "n8n-nodes-base.scheduleTrigger" in TRIGGER_TYPES
        wf = N8nWorkflow(
            name="Scheduled",
            nodes=[node("Cron", type="n8n-nodes-base.scheduleTrigger"), node("Work")],
            connections=connect("Cron", "Work"),
        )
        assert wf.nodes[0].type == "n8n-nodes-base.scheduleTrigger"

    def test_webhook_trigger_recognized(self):
        assert "n8n-nodes-base.webhook" in TRIGGER_TYPES


class TestReachability:
    def test_orphan_node_rejected(self):
        # "Island" has no inbound edge from anywhere
        with pytest.raises(ValidationError, match="Island"):
            N8nWorkflow(
                name="Orphan",
                nodes=[trigger(), node("Connected"), node("Island")],
                connections=connect("Trigger", "Connected"),
            )

    def test_disconnected_subgraph_rejected(self):
        # A->B exists but neither is reachable from Trigger
        with pytest.raises(ValidationError, match="unreachable"):
            N8nWorkflow(
                name="TwoIslands",
                nodes=[trigger(), node("Main"), node("A"), node("B")],
                connections={
                    "Trigger": {"main": [[{"node": "Main", "type": "main", "index": 0}]]},
                    "A": {"main": [[{"node": "B", "type": "main", "index": 0}]]},
                },
            )


# --- serialization ----------------------------------------------------------

class TestSerialization:
    def test_model_dump_produces_n8n_shape(self):
        wf = N8nWorkflow(
            name="Export",
            nodes=[trigger(), node("Step")],
            connections=connect("Trigger", "Step"),
        )
        d = wf.model_dump()
        assert d["name"] == "Export"
        assert "nodes" in d and "connections" in d and "settings" in d
        assert isinstance(d["nodes"][0]["position"], (list, tuple))
        # Connection target uses the n8n object form
        target = d["connections"]["Trigger"]["main"][0][0]
        assert target["node"] == "Step"
        assert target["type"] == "main"

    def test_round_trip_validates(self):
        wf = N8nWorkflow(
            name="RoundTrip",
            nodes=[trigger(), node("A"), node("B")],
            connections={
                "Trigger": {"main": [[{"node": "A", "type": "main", "index": 0}]]},
                "A": {"main": [[{"node": "B", "type": "main", "index": 0}]]},
            },
        )
        dumped = wf.model_dump()
        rebuilt = N8nWorkflow.model_validate(dumped)
        assert rebuilt.name == wf.name
        assert len(rebuilt.nodes) == 3
