"""
Explainer: N8nWorkflow -> plain English. Deterministic template strings,
no LLM — this is the confirmation step and it must not hallucinate.
"""
from src.agents.ai_ml.workflow_generator import (
    ParsedProcess,
    StepSpec,
    TriggerSpec,
    assemble,
    explain,
)


def make_wf(steps, trigger=None):
    wf, notes = assemble(ParsedProcess(
        trigger=trigger or TriggerSpec(kind="schedule", cron="0 9 * * 1"),
        steps=steps,
        confidence=0.9,
    ))
    return wf, notes


class TestExplainStructure:
    def test_output_is_numbered_list(self):
        wf, notes = make_wf([StepSpec(action="do thing", service="foo")])
        text = explain(wf, notes)
        assert "1." in text
        assert "2." in text

    def test_all_nodes_appear_in_order(self):
        wf, notes = make_wf([
            StepSpec(action="fetch data", service="api"),
            StepSpec(action="transform"),
            StepSpec(action="send", service="email"),
        ])
        text = explain(wf, notes)
        # trigger first, then steps in connection order
        pos_trigger = text.index("1.")
        pos_fetch = text.lower().index("fetch")
        pos_send = text.lower().index("send")
        assert pos_trigger < pos_fetch < pos_send

    def test_every_node_mentioned_exactly_once(self):
        wf, notes = make_wf([StepSpec(action=f"unique-{i}") for i in range(4)])
        text = explain(wf, notes)
        for i in range(4):
            assert text.lower().count(f"unique-{i}") == 1


class TestTriggerPhrasing:
    def test_schedule_trigger_mentions_schedule(self):
        wf, notes = make_wf(
            [StepSpec(action="work")],
            trigger=TriggerSpec(kind="schedule", cron="0 17 * * 5"),
        )
        text = explain(wf, notes).lower()
        assert "schedule" in text or "cron" in text or "0 17 * * 5" in text

    def test_webhook_trigger_mentions_webhook(self):
        wf, notes = make_wf(
            [StepSpec(action="handle")],
            trigger=TriggerSpec(kind="webhook", event_source="form"),
        )
        text = explain(wf, notes).lower()
        assert "webhook" in text or "incoming" in text

    def test_manual_trigger_mentions_manual(self):
        wf, notes = make_wf(
            [StepSpec(action="go")],
            trigger=TriggerSpec(kind="manual"),
        )
        text = explain(wf, notes).lower()
        assert "manual" in text or "on demand" in text


class TestNodeTypePhrasing:
    def test_http_fallback_names_the_service(self):
        wf, notes = make_wf([StepSpec(action="pull data", service="calendly")])
        text = explain(wf, notes)
        assert "calendly" in text.lower()

    def test_if_node_explains_condition(self):
        wf, notes = make_wf([
            StepSpec(action="check", condition="engagement < threshold"),
            StepSpec(action="alert", service="slack"),
        ])
        text = explain(wf, notes).lower()
        assert "if" in text or "when" in text or "check" in text

    def test_merge_node_explained(self):
        wf, notes = make_wf([
            StepSpec(action="A", service="x"),
            StepSpec(action="B", service="y"),
            StepSpec(action="combine", inputs_from=[0, 1]),
        ])
        text = explain(wf, notes).lower()
        assert "merge" in text or "combine" in text or "join" in text


class TestCustomizationSection:
    def test_notes_appear_in_footer(self):
        wf, notes = make_wf([StepSpec(action="fetch", service="stripe")])
        text = explain(wf, notes)
        assert "stripe" in text.lower()
        # notes come after the numbered steps
        assert text.lower().rindex("stripe") > text.rindex("2.")

    def test_no_notes_no_footer(self):
        wf, notes = make_wf([StepSpec(action="format"), StepSpec(action="shape")])
        assert notes == []
        text = explain(wf, notes)
        assert "configure" not in text.lower()
        assert "before this" not in text.lower()


class TestCalendlyExplanation:
    def test_spec_example_reads_coherently(self):
        wf, notes = make_wf(
            [
                StepSpec(action="export last week appointments", service="calendly"),
                StepSpec(action="fetch payments", service="stripe"),
                StepSpec(action="cross-reference", inputs_from=[0, 1]),
                StepSpec(action="keep no-shows", condition="payment_status == unpaid"),
                StepSpec(action="send reschedule link", service="email"),
            ],
            trigger=TriggerSpec(kind="schedule", cron="0 17 * * 5"),
        )
        text = explain(wf, notes)
        lower = text.lower()
        # Each business concept surfaces
        assert "calendly" in lower
        assert "stripe" in lower
        assert "reschedule" in lower
        # 6 nodes → 6 numbered lines
        for n in range(1, 7):
            assert f"{n}." in text
        # Config footer present
        assert "configure" in lower or "before this" in lower
