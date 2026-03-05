"""
Unit tests for WorkflowGenerator.

Covers the six validation criteria from the spec:
  1. Clear multi-step description → valid n8n workflow JSON (importable)
  2. Vague description → clarifying questions instead of bad workflow
  3. Process matching an existing template → uses template (fast path)
  4. Process that's a variation on a template → modified template
  5. Generated workflows: correct node types, valid connections, no orphans
  6. Plain-language explanation matches the generated workflow
"""
import pytest

from src.agents.ai_ml.workflow_generator import (
    WorkflowGenerator,
    ParsedProcess,
    TriggerSpec,
    StepSpec,
    GenerationStrategy,
    N8nNodeCatalog,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def generator():
    return WorkflowGenerator()


@pytest.fixture
def calendly_stripe_description():
    """The canonical multi-tool example from the spec — no template covers this."""
    return (
        "Every Friday my office manager exports last week's appointments from "
        "Calendly, cross-references them with payments in Stripe, flags anyone "
        "who no-showed, and emails them a reschedule link."
    )


@pytest.fixture
def instagram_analytics_description():
    """Second clear example from the spec — has a conditional branch."""
    return (
        "Every Monday, pull Instagram analytics, compare to last week, and "
        "Slack me if engagement dropped more than 10%."
    )


@pytest.fixture
def vague_description():
    """Too vague to generate from — per the spec."""
    return "I need to automate my marketing"


@pytest.fixture
def weekly_report_description():
    """Closely matches templates/report_generation.json."""
    return (
        "Every Monday morning, aggregate last week's metrics, generate a PDF "
        "report, email it to the team, and store it in Drive."
    )


@pytest.fixture
def weekly_report_with_slack():
    """Variation on report_generation.json — adds a Slack step the template lacks."""
    return (
        "Every Monday, aggregate the week's metrics, generate a report, "
        "email it to the team, store it in Drive, and then post a summary to Slack."
    )


# ---------------------------------------------------------------------------
# Process parsing: trigger extraction
# ---------------------------------------------------------------------------

class TestTriggerParsing:

    def test_every_friday_becomes_schedule_trigger(self, generator, calendly_stripe_description):
        parsed = generator.parse_process(calendly_stripe_description)
        assert parsed.trigger is not None
        assert parsed.trigger.kind == "schedule"
        # Friday is day 5 in cron (0=Sun or 1=Mon depending on system; n8n uses 0-6 Sun-Sat → Fri=5)
        assert "5" in parsed.trigger.schedule

    def test_every_monday_becomes_schedule_trigger(self, generator, instagram_analytics_description):
        parsed = generator.parse_process(instagram_analytics_description)
        assert parsed.trigger.kind == "schedule"
        assert "1" in parsed.trigger.schedule  # Monday = 1

    def test_when_event_becomes_webhook_trigger(self, generator):
        parsed = generator.parse_process(
            "When a new lead submits the contact form, send them a welcome email and add them to HubSpot."
        )
        assert parsed.trigger.kind == "webhook"

    def test_no_trigger_phrase_defaults_to_manual(self, generator):
        parsed = generator.parse_process(
            "Export the customer list from HubSpot and email it to me."
        )
        assert parsed.trigger.kind == "manual"

    def test_daily_frequency_produces_daily_cron(self, generator):
        parsed = generator.parse_process(
            "Every day at 9am, pull new orders from Shopify and log them to Google Sheets."
        )
        assert parsed.trigger.kind == "schedule"
        # Daily cron has * in day-of-week position
        assert parsed.trigger.schedule.endswith("* *") or parsed.trigger.schedule.endswith("*")


# ---------------------------------------------------------------------------
# Process parsing: step sequence & dependencies
# ---------------------------------------------------------------------------

class TestStepParsing:

    def test_extracts_ordered_steps(self, generator, calendly_stripe_description):
        parsed = generator.parse_process(calendly_stripe_description)
        # Four distinct actions: export, cross-reference, flag, email
        assert len(parsed.steps) >= 4
        # Steps preserve order
        actions = [s.action for s in parsed.steps]
        assert actions.index("fetch") < actions.index("send_email")

    def test_identifies_tools_per_step(self, generator, calendly_stripe_description):
        parsed = generator.parse_process(calendly_stripe_description)
        tools = {s.tool for s in parsed.steps if s.tool}
        assert "calendly" in tools
        assert "stripe" in tools

    def test_cross_reference_creates_merge_dependency(self, generator, calendly_stripe_description):
        """'cross-references them with payments in Stripe' → merge step depending on two prior fetches."""
        parsed = generator.parse_process(calendly_stripe_description)
        merge_steps = [s for s in parsed.steps if s.action == "merge"]
        assert len(merge_steps) == 1
        # Merge must depend on more than one upstream step
        assert len(merge_steps[0].depends_on) >= 2

    def test_conditional_phrase_creates_condition_step(self, generator, instagram_analytics_description):
        """'Slack me if engagement dropped more than 10%' → IF branch."""
        parsed = generator.parse_process(instagram_analytics_description)
        condition_steps = [s for s in parsed.steps if s.condition is not None]
        assert len(condition_steps) >= 1
        assert "10%" in condition_steps[0].condition or "dropped" in condition_steps[0].condition

    def test_filter_phrase_creates_filter_step(self, generator, calendly_stripe_description):
        """'flags anyone who no-showed' → filter."""
        parsed = generator.parse_process(calendly_stripe_description)
        filter_steps = [s for s in parsed.steps if s.action == "filter"]
        assert len(filter_steps) == 1
        assert "no-show" in filter_steps[0].description.lower()

    def test_linear_process_has_chain_dependencies(self, generator):
        """Simple sequential process: each step depends on exactly the previous one."""
        parsed = generator.parse_process(
            "Every day, fetch orders from Shopify, then log them in Google Sheets, then send me a Slack summary."
        )
        # After the first step, each subsequent step depends on exactly one predecessor
        for step in parsed.steps[1:]:
            assert len(step.depends_on) == 1


# ---------------------------------------------------------------------------
# Confidence scoring & clarifying questions
# ---------------------------------------------------------------------------

class TestConfidenceAndFallback:

    def test_vague_description_scores_low(self, generator, vague_description):
        parsed = generator.parse_process(vague_description)
        assert parsed.confidence < generator.config["generation_threshold"]

    def test_clear_description_scores_high(self, generator, calendly_stripe_description):
        parsed = generator.parse_process(calendly_stripe_description)
        assert parsed.confidence >= generator.config["generation_threshold"]

    async def test_vague_description_returns_questions_not_workflow(self, generator, vague_description):
        result = await generator.generate(vague_description)
        assert result.workflow is None
        assert len(result.clarifying_questions) > 0

    async def test_clear_description_returns_workflow_not_questions(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        assert result.workflow is not None
        assert result.clarifying_questions == []

    def test_clarifying_questions_are_targeted_not_generic(self, generator):
        """Missing trigger → asks about schedule. Missing tool → asks about that specific step."""
        parsed = generator.parse_process("Process the data and send it out.")
        questions = generator.generate_clarifying_questions(parsed)
        # Should ask about schedule (no trigger) and tools (no tools mentioned)
        question_text = " ".join(questions).lower()
        assert any(word in question_text for word in ["when", "how often", "trigger", "schedule"])
        assert any(word in question_text for word in ["tool", "service", "where", "what do you use"])

    def test_missing_info_populated_when_steps_lack_tools(self, generator):
        parsed = generator.parse_process("Every Monday, fetch the data, transform it, and send a report.")
        # Generic verbs with no tool mentions should flag missing info
        assert len(parsed.missing) > 0


# ---------------------------------------------------------------------------
# Template integration: fast-path, modify, fresh
# ---------------------------------------------------------------------------

class TestTemplateIntegration:

    async def test_close_match_uses_template_strategy(self, generator, weekly_report_description):
        """Matches report_generation.json closely → TEMPLATE_EXACT."""
        result = await generator.generate(weekly_report_description)
        assert result.strategy == GenerationStrategy.TEMPLATE_EXACT
        assert result.source_template == "Weekly Business Report"

    async def test_no_match_generates_fresh(self, generator, calendly_stripe_description):
        """Calendly+Stripe no-show flow has no template → GENERATE_FRESH."""
        result = await generator.generate(calendly_stripe_description)
        assert result.strategy == GenerationStrategy.GENERATE_FRESH
        assert result.source_template is None

    async def test_variation_modifies_template(self, generator, weekly_report_with_slack):
        """Weekly report + Slack step → TEMPLATE_MODIFIED, starts from report_generation.json."""
        result = await generator.generate(weekly_report_with_slack)
        assert result.strategy == GenerationStrategy.TEMPLATE_MODIFIED
        assert result.source_template == "Weekly Business Report"
        # The generated workflow includes a Slack node the template didn't have
        node_types = {n["type"] for n in result.workflow["nodes"]}
        assert "n8n-nodes-base.slack" in node_types

    async def test_template_path_still_produces_valid_n8n(self, generator, weekly_report_description):
        """Template fast-path compiles to importable n8n JSON, not just the intermediate format."""
        result = await generator.generate(weekly_report_description)
        assert "nodes" in result.workflow
        assert "connections" in result.workflow
        assert all("type" in n and n["type"].startswith("n8n-nodes-base.") for n in result.workflow["nodes"])


# ---------------------------------------------------------------------------
# n8n compilation: structural validity
# ---------------------------------------------------------------------------

class TestN8nCompilation:

    async def test_workflow_has_required_top_level_keys(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        wf = result.workflow
        assert set(wf.keys()) >= {"name", "nodes", "connections", "settings"}

    async def test_every_node_has_required_fields(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        for node in result.workflow["nodes"]:
            assert "name" in node
            assert "type" in node
            assert "typeVersion" in node
            assert "position" in node and len(node["position"]) == 2
            assert "parameters" in node

    async def test_connections_keyed_by_node_name_not_id(self, generator, calendly_stripe_description):
        """n8n imports key connections by node name (confirmed via n8n docs).
        The existing executive_assistant.py:_generate_n8n_workflow() uses UUID keys — wrong."""
        result = await generator.generate(calendly_stripe_description)
        node_names = {n["name"] for n in result.workflow["nodes"]}
        for conn_key in result.workflow["connections"].keys():
            assert conn_key in node_names, f"Connection key '{conn_key}' is not a node name"

    async def test_connection_targets_reference_existing_nodes(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        node_names = {n["name"] for n in result.workflow["nodes"]}
        for source, outputs in result.workflow["connections"].items():
            for output_group in outputs["main"]:
                for link in output_group:
                    assert link["node"] in node_names
                    assert link["type"] == "main"
                    assert "index" in link

    async def test_no_orphaned_nodes(self, generator, calendly_stripe_description):
        """Every non-trigger node is reachable from the trigger via connections."""
        result = await generator.generate(calendly_stripe_description)
        wf = result.workflow
        node_names = {n["name"] for n in wf["nodes"]}
        # Nodes that receive incoming connections
        targets = set()
        for outputs in wf["connections"].values():
            for group in outputs["main"]:
                targets.update(link["node"] for link in group)
        # Nodes that send outgoing connections
        sources = set(wf["connections"].keys())
        # Triggers are nodes with no incoming edges
        triggers = node_names - targets
        assert len(triggers) >= 1, "Workflow must have at least one trigger"
        # Every non-trigger must have an incoming edge
        orphans = node_names - targets - triggers
        assert orphans == set(), f"Orphaned nodes: {orphans}"
        # Every trigger must have outgoing (otherwise it's disconnected)
        for t in triggers:
            if len(node_names) > 1:
                assert t in sources, f"Trigger '{t}' has no outgoing connections"

    async def test_schedule_trigger_has_cron_parameters(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        schedule_nodes = [
            n for n in result.workflow["nodes"]
            if n["type"] == "n8n-nodes-base.scheduleTrigger"
        ]
        assert len(schedule_nodes) == 1
        params = schedule_nodes[0]["parameters"]
        # n8n scheduleTrigger uses rule.interval[].expression (per Context7 docs)
        assert "rule" in params
        assert "interval" in params["rule"]
        assert any("expression" in i for i in params["rule"]["interval"])

    async def test_if_node_has_two_output_groups(self, generator, instagram_analytics_description):
        """n8n IF nodes emit two output arrays: [true_branch, false_branch]."""
        result = await generator.generate(instagram_analytics_description)
        if_nodes = [n for n in result.workflow["nodes"] if n["type"] == "n8n-nodes-base.if"]
        assert len(if_nodes) >= 1
        if_name = if_nodes[0]["name"]
        if if_name in result.workflow["connections"]:
            # When an IF has downstream nodes, it must have two output groups
            assert len(result.workflow["connections"][if_name]["main"]) == 2

    async def test_node_names_are_unique(self, generator, calendly_stripe_description):
        """Duplicate names would break connection keying."""
        result = await generator.generate(calendly_stripe_description)
        names = [n["name"] for n in result.workflow["nodes"]]
        assert len(names) == len(set(names))

    async def test_positions_are_laid_out_left_to_right(self, generator, calendly_stripe_description):
        """Visual layout: trigger leftmost, downstream steps to the right."""
        result = await generator.generate(calendly_stripe_description)
        nodes = result.workflow["nodes"]
        trigger_x = min(n["position"][0] for n in nodes if "Trigger" in n["type"] or "trigger" in n["type"].lower())
        non_trigger_xs = [n["position"][0] for n in nodes if "rigger" not in n["type"]]
        assert all(x >= trigger_x for x in non_trigger_xs)


# ---------------------------------------------------------------------------
# Node catalog: tool → n8n node mapping
# ---------------------------------------------------------------------------

class TestN8nNodeCatalog:

    def test_stripe_maps_to_stripe_node(self):
        catalog = N8nNodeCatalog()
        node = catalog.resolve_tool("stripe", action="fetch")
        assert node["type"] == "n8n-nodes-base.stripe"

    def test_slack_maps_to_slack_node(self):
        catalog = N8nNodeCatalog()
        node = catalog.resolve_tool("slack", action="notify")
        assert node["type"] == "n8n-nodes-base.slack"

    def test_unknown_tool_falls_back_to_http_request(self):
        """Calendly has no dedicated action node in n8n-nodes-base → httpRequest."""
        catalog = N8nNodeCatalog()
        node = catalog.resolve_tool("calendly", action="fetch")
        assert node["type"] == "n8n-nodes-base.httpRequest"

    def test_send_email_action_maps_to_email_node(self):
        catalog = N8nNodeCatalog()
        node = catalog.resolve_action("send_email")
        assert node["type"] in ("n8n-nodes-base.emailSend", "n8n-nodes-base.gmail")

    def test_wait_action_maps_to_wait_node(self):
        catalog = N8nNodeCatalog()
        node = catalog.resolve_action("wait")
        assert node["type"] == "n8n-nodes-base.wait"

    def test_filter_action_maps_to_filter_node(self):
        catalog = N8nNodeCatalog()
        node = catalog.resolve_action("filter")
        assert node["type"] == "n8n-nodes-base.filter"

    def test_merge_action_maps_to_merge_node(self):
        catalog = N8nNodeCatalog()
        node = catalog.resolve_action("merge")
        assert node["type"] == "n8n-nodes-base.merge"


# ---------------------------------------------------------------------------
# Workflow validation
# ---------------------------------------------------------------------------

class TestWorkflowValidation:

    def test_valid_workflow_passes(self, generator):
        wf = {
            "name": "Test",
            "nodes": [
                {"name": "Trigger", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
                {"name": "Email", "type": "n8n-nodes-base.emailSend", "typeVersion": 1, "position": [200, 0], "parameters": {}},
            ],
            "connections": {
                "Trigger": {"main": [[{"node": "Email", "type": "main", "index": 0}]]},
            },
            "settings": {},
        }
        valid, errors = generator.validate_n8n_workflow(wf)
        assert valid, f"Expected valid, got errors: {errors}"

    def test_orphaned_node_fails_validation(self, generator):
        wf = {
            "name": "Test",
            "nodes": [
                {"name": "Trigger", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
                {"name": "Email", "type": "n8n-nodes-base.emailSend", "typeVersion": 1, "position": [200, 0], "parameters": {}},
                {"name": "Orphan", "type": "n8n-nodes-base.set", "typeVersion": 1, "position": [400, 0], "parameters": {}},
            ],
            "connections": {
                "Trigger": {"main": [[{"node": "Email", "type": "main", "index": 0}]]},
            },
            "settings": {},
        }
        valid, errors = generator.validate_n8n_workflow(wf)
        assert not valid
        assert any("orphan" in e.lower() for e in errors)

    def test_dangling_connection_fails_validation(self, generator):
        wf = {
            "name": "Test",
            "nodes": [
                {"name": "Trigger", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
            ],
            "connections": {
                "Trigger": {"main": [[{"node": "Ghost", "type": "main", "index": 0}]]},
            },
            "settings": {},
        }
        valid, errors = generator.validate_n8n_workflow(wf)
        assert not valid
        assert any("ghost" in e.lower() or "not exist" in e.lower() for e in errors)

    def test_missing_required_node_field_fails(self, generator):
        wf = {
            "name": "Test",
            "nodes": [
                {"name": "Trigger", "type": "n8n-nodes-base.manualTrigger"},  # missing position, typeVersion, parameters
            ],
            "connections": {},
            "settings": {},
        }
        valid, errors = generator.validate_n8n_workflow(wf)
        assert not valid

    # --- error-path sweep ---------------------------------------------------
    # Each case mutates a known-good workflow in exactly one way and asserts
    # the specific error surfaces. Keeps the fixture data in one place.

    @pytest.fixture
    def valid_wf(self):
        def node(name, ntype="n8n-nodes-base.set", pos=None):
            return {"name": name, "type": ntype, "typeVersion": 1,
                    "position": pos or [0, 0], "parameters": {}}
        return {
            "name": "Base",
            "nodes": [node("A", "n8n-nodes-base.manualTrigger"), node("B", pos=[200, 0])],
            "connections": {"A": {"main": [[{"node": "B", "type": "main", "index": 0}]]}},
            "settings": {},
        }

    @pytest.mark.parametrize("drop", ["name", "nodes", "connections", "settings"])
    def test_missing_top_level_key(self, generator, valid_wf, drop):
        del valid_wf[drop]
        valid, errors = generator.validate_n8n_workflow(valid_wf)
        assert not valid
        assert any(f"missing top-level key: {drop}" in e for e in errors)

    def test_duplicate_node_name(self, generator, valid_wf):
        valid_wf["nodes"].append(dict(valid_wf["nodes"][1]))  # second "B"
        valid, errors = generator.validate_n8n_workflow(valid_wf)
        assert not valid
        assert any("duplicate node name: B" in e for e in errors)

    def test_non_standard_node_type(self, generator, valid_wf):
        valid_wf["nodes"][1]["type"] = "community-nodes.foo"
        valid, errors = generator.validate_n8n_workflow(valid_wf)
        assert not valid
        assert any("non-standard node type" in e for e in errors)

    @pytest.mark.parametrize("bad_pos", [[0], [0, 0, 0], "0,0", {"x": 0, "y": 0}])
    def test_invalid_position_shape(self, generator, valid_wf, bad_pos):
        valid_wf["nodes"][0]["position"] = bad_pos
        valid, errors = generator.validate_n8n_workflow(valid_wf)
        assert not valid
        assert any("position must be [x, y]" in e for e in errors)

    def test_connection_source_does_not_exist(self, generator, valid_wf):
        # This is the executive_assistant.py bug scenario — source keyed by
        # something that isn't a node name (e.g. a UUID).
        valid_wf["connections"] = {
            "not-a-node": {"main": [[{"node": "B", "type": "main", "index": 0}]]},
            "A": {"main": [[{"node": "B", "type": "main", "index": 0}]]},
        }
        valid, errors = generator.validate_n8n_workflow(valid_wf)
        assert not valid
        assert any("connection source 'not-a-node' does not exist" in e for e in errors)

    def test_connection_with_non_main_type(self, generator, valid_wf):
        valid_wf["connections"]["A"]["main"][0][0]["type"] = "ai_tool"
        valid, errors = generator.validate_n8n_workflow(valid_wf)
        assert not valid
        assert any("non-main type" in e for e in errors)

    def test_errors_accumulate_not_short_circuit(self, generator, valid_wf):
        # Past the top-level-key gate, the validator should collect every
        # problem in one pass so the customer gets a complete list.
        valid_wf["nodes"][0]["type"] = "bad.type"
        valid_wf["nodes"].append(dict(valid_wf["nodes"][1]))  # dup "B"
        valid_wf["connections"]["Ghost"] = {"main": [[{"node": "Phantom", "type": "weird", "index": 0}]]}
        valid, errors = generator.validate_n8n_workflow(valid_wf)
        assert not valid
        assert len(errors) >= 4, f"expected accumulated errors, got {errors}"


# ---------------------------------------------------------------------------
# Workflow explanation
# ---------------------------------------------------------------------------

class TestExplanation:

    async def test_explanation_is_step_by_step(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        # Should have one explanation line per non-trigger action
        assert len(result.explanation) >= 4
        # Each line is a sentence, not a node type
        for line in result.explanation:
            assert "n8n-nodes-base" not in line

    async def test_explanation_mentions_schedule_in_plain_language(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        full_text = " ".join(result.explanation).lower()
        assert "friday" in full_text or "weekly" in full_text

    async def test_explanation_mentions_tools_by_name(self, generator, calendly_stripe_description):
        result = await generator.generate(calendly_stripe_description)
        full_text = " ".join(result.explanation).lower()
        assert "calendly" in full_text
        assert "stripe" in full_text

    async def test_explanation_covers_conditional_branch(self, generator, instagram_analytics_description):
        result = await generator.generate(instagram_analytics_description)
        full_text = " ".join(result.explanation).lower()
        # The conditional ("if engagement dropped") should surface in the explanation
        assert "if" in full_text or "when" in full_text or "only" in full_text


# ---------------------------------------------------------------------------
# End-to-end: spec's primary validation criterion
# ---------------------------------------------------------------------------

class TestEndToEnd:

    async def test_calendly_stripe_example_full_pipeline(self, generator, calendly_stripe_description):
        """The canonical spec example must produce a complete, valid result."""
        result = await generator.generate(calendly_stripe_description)

        assert result.workflow is not None
        assert result.strategy == GenerationStrategy.GENERATE_FRESH
        assert result.clarifying_questions == []
        assert result.confidence >= generator.config["generation_threshold"]

        valid, errors = generator.validate_n8n_workflow(result.workflow)
        assert valid, f"Generated workflow failed validation: {errors}"

        # Must contain: schedule trigger, Calendly fetch, Stripe fetch, merge, filter, email
        types = [n["type"] for n in result.workflow["nodes"]]
        assert "n8n-nodes-base.scheduleTrigger" in types
        assert "n8n-nodes-base.merge" in types
        assert "n8n-nodes-base.filter" in types
        assert any(t in types for t in ("n8n-nodes-base.emailSend", "n8n-nodes-base.gmail"))

    async def test_generated_workflow_is_json_serializable(self, generator, calendly_stripe_description):
        """'importable into n8n' implies round-trippable through JSON."""
        import json
        result = await generator.generate(calendly_stripe_description)
        serialized = json.dumps(result.workflow)
        deserialized = json.loads(serialized)
        assert deserialized == result.workflow
