"""
Assembler: ParsedProcess -> N8nWorkflow. Pure function, no LLM.

Every assembled workflow must pass N8nWorkflow's structural validators,
so we don't re-test reachability etc. here — we test that the wiring
reflects the parse.
"""
import pytest

from src.agents.ai_ml.n8n_schema import N8nWorkflow
from src.agents.ai_ml.workflow_generator import (
    ParsedProcess,
    StepSpec,
    TriggerSpec,
    assemble,
)


def schedule_friday():
    return TriggerSpec(kind="schedule", cron="0 17 * * 5")


# --- linear chains ----------------------------------------------------------

class TestLinearAssembly:
    def test_single_step_produces_two_nodes(self):
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[StepSpec(action="fetch data", service="airtable")],
            confidence=0.9,
        )
        wf, notes = assemble(parsed)
        assert isinstance(wf, N8nWorkflow)
        assert len(wf.nodes) == 2
        assert wf.nodes[0].type == "n8n-nodes-base.scheduleTrigger"
        assert wf.nodes[1].type == "n8n-nodes-base.httpRequest"
        # airtable is unknown → one config note
        assert len(notes) == 1

    def test_three_step_linear_chain_wires_sequentially(self):
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="fetch", service="calendly"),
                StepSpec(action="transform"),
                StepSpec(action="notify", service="email"),
            ],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)
        assert len(wf.nodes) == 4
        # trigger -> step0 -> step1 -> step2
        # 3 connection entries (last node has no outgoing)
        assert len(wf.connections) == 3
        # trigger's only downstream is the first step
        trigger_targets = wf.connections[wf.nodes[0].name]["main"][0]
        assert len(trigger_targets) == 1
        assert trigger_targets[0].node == wf.nodes[1].name

    def test_node_names_are_unique(self):
        # Two steps with the same action text should not collide
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="fetch", service="stripe"),
                StepSpec(action="fetch", service="calendly"),
            ],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)  # validator would raise on dup names
        names = [n.name for n in wf.nodes]
        assert len(names) == len(set(names))

    def test_positions_increase_monotonically(self):
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[StepSpec(action=f"s{i}") for i in range(5)],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)
        x_positions = [n.position[0] for n in wf.nodes]
        assert x_positions == sorted(x_positions)


# --- branching --------------------------------------------------------------

class TestConditionalAssembly:
    def test_step_with_condition_becomes_if_node(self):
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="fetch", service="instagram"),
                StepSpec(action="check drop", condition="engagement < last * 0.9"),
                StepSpec(action="alert", service="slack"),
            ],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)
        if_nodes = [n for n in wf.nodes if n.type == "n8n-nodes-base.if"]
        assert len(if_nodes) == 1
        # condition text surfaces in params
        assert "engagement" in str(if_nodes[0].parameters)

    def test_if_node_true_branch_wires_to_next_step(self):
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="check", condition="x > 0"),
                StepSpec(action="handle true"),
            ],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)
        if_node = next(n for n in wf.nodes if n.type == "n8n-nodes-base.if")
        # main[0] is the true branch
        true_targets = wf.connections[if_node.name]["main"][0]
        assert len(true_targets) == 1
        assert true_targets[0].node == wf.nodes[-1].name


# --- merge ------------------------------------------------------------------

class TestMergeAssembly:
    def test_multi_input_step_becomes_merge(self):
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="fetch A", service="calendly"),     # step 0
                StepSpec(action="fetch B", service="stripe"),       # step 1
                StepSpec(action="join", inputs_from=[0, 1]),        # step 2
            ],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)
        merge_nodes = [n for n in wf.nodes if n.type == "n8n-nodes-base.merge"]
        assert len(merge_nodes) == 1

    def test_merge_receives_connections_from_both_inputs(self):
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="fetch A", service="calendly"),
                StepSpec(action="fetch B", service="stripe"),
                StepSpec(action="join", inputs_from=[0, 1]),
            ],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)
        merge = next(n for n in wf.nodes if n.type == "n8n-nodes-base.merge")

        # Both "fetch A" and "fetch B" nodes should have the merge as a downstream target
        inbound_sources = [
            src for src, ports in wf.connections.items()
            if any(t.node == merge.name for pin in ports["main"] for t in pin)
        ]
        assert len(inbound_sources) == 2

    def test_merge_second_input_uses_distinct_pin(self):
        # n8n merge nodes expect inputs on separate pins (main[0], main[1])
        # not two targets on the same pin
        parsed = ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="A", service="x"),
                StepSpec(action="B", service="y"),
                StepSpec(action="merge", inputs_from=[0, 1]),
            ],
            confidence=0.9,
        )
        wf, _ = assemble(parsed)
        merge = next(n for n in wf.nodes if n.type == "n8n-nodes-base.merge")
        # Find which pin each source targets on the merge
        inbound = []
        for src, ports in wf.connections.items():
            for pin in ports["main"]:
                for t in pin:
                    if t.node == merge.name:
                        inbound.append((src, t.index))
        assert len(inbound) == 2
        # Two different input pins on the merge
        assert len({idx for _, idx in inbound}) == 2


# --- the spec's example -----------------------------------------------------

class TestCalendlyStripeExample:
    """The motivating case from the design doc."""

    @pytest.fixture
    def calendly_parse(self):
        return ParsedProcess(
            trigger=schedule_friday(),
            steps=[
                StepSpec(action="export last week appointments", service="calendly"),
                StepSpec(action="fetch payments", service="stripe"),
                StepSpec(action="cross-reference", inputs_from=[0, 1]),
                StepSpec(action="keep no-shows", condition="payment_status == unpaid"),
                StepSpec(action="send reschedule link", service="email"),
            ],
            confidence=0.85,
        )

    def test_assembles_without_validation_error(self, calendly_parse):
        wf, notes = assemble(calendly_parse)
        assert len(wf.nodes) == 6  # trigger + 5 steps

    def test_has_expected_node_types(self, calendly_parse):
        wf, _ = assemble(calendly_parse)
        types = [n.type for n in wf.nodes]
        assert types.count("n8n-nodes-base.httpRequest") == 2  # calendly + stripe
        assert types.count("n8n-nodes-base.merge") == 1
        assert types.count("n8n-nodes-base.if") == 1
        assert types.count("n8n-nodes-base.emailSend") == 1

    def test_collects_customization_notes(self, calendly_parse):
        _, notes = assemble(calendly_parse)
        notes_lower = " ".join(notes).lower()
        assert "calendly" in notes_lower
        assert "stripe" in notes_lower
        # email is known but needs SMTP
        assert "smtp" in notes_lower or "email" in notes_lower

    def test_json_serializable(self, calendly_parse):
        import json
        wf, _ = assemble(calendly_parse)
        payload = json.dumps(wf.model_dump())
        assert "scheduleTrigger" in payload
        assert "calendly" in payload.lower()


# --- customization notes ----------------------------------------------------

class TestCustomizationNotes:
    def test_no_unknown_services_no_http_notes(self):
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[StepSpec(action="format"), StepSpec(action="transform")],
            confidence=0.9,
        )
        _, notes = assemble(parsed)
        assert notes == []

    def test_notes_deduplicated(self):
        # Two steps hitting the same unknown service shouldn't produce
        # two identical notes
        parsed = ParsedProcess(
            trigger=TriggerSpec(kind="manual"),
            steps=[
                StepSpec(action="fetch page 1", service="notion"),
                StepSpec(action="fetch page 2", service="notion"),
            ],
            confidence=0.9,
        )
        _, notes = assemble(parsed)
        assert len(notes) == 1
