# Workflow Generation from Conversation — Design

**Date:** 2026-03-05
**Status:** Approved
**Related:** `src/agents/ai_ml/workflow_template_matcher.py`, `src/agents/executive_assistant.py:378-559` (WorkflowCreator)

## Problem

The EA matches customer process descriptions against ~7 static templates. When a customer describes something off-template — "every Friday export Calendly appointments, cross-reference with Stripe payments, flag no-shows, email reschedule links" — the system has nothing to offer. The steps are clear, the tools are known, n8n can do it. The EA just can't produce the workflow.

## Goal

When the template matcher comes up empty (or weak), generate a valid n8n workflow JSON from the customer's description. Valid means: importable into n8n, structurally sound, correct node types, properly wired connections, no orphans. It won't run without credentials — that's expected.

## Non-goals

- Deploying to a live n8n instance
- Visual workflow editor
- Expanding the static template library
- Generating JavaScript for `code` nodes

---

## Architecture

**Stateless generator. EA owns the clarification loop.**

Single module `src/agents/ai_ml/workflow_generator.py` with one public entry point. When the generator can't produce a confident workflow, it returns `NeedsClarification` with targeted questions and a partial parse. The EA's existing LangGraph clarification node (`executive_assistant.py:1275`) handles the turn, stashes the partial in `ConversationState`, and re-calls the generator with the merged answer. The generator never holds state between calls.

```
                           ┌─────────────────────────────────┐
                           │  WorkflowCreator (EA)           │
                           │  orchestrates, owns state       │
                           └────────────┬────────────────────┘
                                        │
              template match ≥ 0.8      │     match < 0.5 or no match
            ┌───────────────────────────┼───────────────────────────┐
            ▼                           ▼                           ▼
   load templates/*.json     template_hint = matched       template_hint = None
   (already n8n format)      template's trigger/actions
            │                           │                           │
            │                           └───────────┬───────────────┘
            │                                       ▼
            │                         ┌──────────────────────────────┐
            │                         │  generate(desc, insights,    │
            │                         │           template_hint)     │
            │                         └─────────────┬────────────────┘
            │                                       │
            │                    ┌──────────────────┼──────────────────┐
            │                    ▼                  ▼                  ▼
            │              Generated        NeedsClarification    (retry on
            │          (workflow, expl,     (questions, partial)   merged input)
            │           customization)              │
            │                    │                  ▼
            │                    │         EA._handle_clarification
            ▼                    ▼
         return              return
```

### Module layout

```
src/agents/ai_ml/
  n8n_schema.py          Pydantic models + structural validators
  n8n_catalog.py         Node type registry, resolver, param builders
  workflow_generator.py  ProcessParser, WorkflowAssembler, WorkflowExplainer, generate()

templates/n8n/           Lifted templates (real n8n JSON)
  report_generation.json
  invoice_generation.json
```

---

## Data models

### n8n schema (`n8n_schema.py`)

The validation target. Built from the working example at `docs/architecture/LAUNCH-Bot-Architecture.md:137-280`.

```python
class N8nNode(BaseModel):
    id: str
    name: str                      # unique within workflow — connection key
    type: str                      # "n8n-nodes-base.xxx"
    typeVersion: float
    position: tuple[int, int]
    parameters: dict[str, Any]

class N8nConnectionTarget(BaseModel):
    node: str                      # target node NAME, not id
    type: Literal["main"] = "main"
    index: int = 0

class N8nWorkflow(BaseModel):
    name: str
    nodes: list[N8nNode]
    connections: dict[str, dict[str, list[list[N8nConnectionTarget]]]]
    #            ^^^ source node name
    settings: dict = {}
    active: bool = False

    @model_validator(mode="after")
    def validate_structure(self):
        # unique node names
        # connection source keys ∈ node names
        # connection target.node ∈ node names
        # exactly one node with type in TRIGGER_TYPES
        # every non-trigger node is reachable from the trigger
```

**Note:** the existing `WorkflowCreator._generate_n8n_workflow` at `executive_assistant.py:532` keys connections by UUID — that's wrong. n8n keys by node name. This design fixes that.

### Parsed process — LLM structured output schema

```python
class TriggerSpec(BaseModel):
    kind: Literal["schedule", "webhook", "manual"]
    cron: str | None = None          # "0 17 * * 5" for "every Friday at 5pm"
    event_source: str | None = None  # for webhook: "stripe", "form"

class StepSpec(BaseModel):
    action: str                      # "fetch appointments", "filter no-shows"
    service: str | None = None       # "calendly", "stripe" — drives node resolution
    inputs_from: list[int] = []      # prior step indices; [] → previous step; [1,2] → merge
    condition: str | None = None     # "payment_status == 'unpaid'" → IF node

class ParsedProcess(BaseModel):
    trigger: TriggerSpec
    steps: list[StepSpec]
    confidence: float                # model self-assessment, 0.0-1.0
    gaps: list[str]                  # "unclear what 'flag' means — notify? tag? both?"
```

`inputs_from` is the data-flow graph. Default `[]` means linear (connect to previous). Multiple entries trigger a merge node. This is what lets the assembler build branches, not just chains.

`gaps` is the clarification driver. Non-empty or `confidence < 0.6` → return `NeedsClarification(questions=gaps, partial=parsed)`.

### Result union

```python
class Generated(BaseModel):
    workflow: N8nWorkflow
    explanation: str
    customization_required: list[str]   # "Configure Calendly API endpoint in node 'Fetch Appointments'"

class NeedsClarification(BaseModel):
    questions: list[str]
    partial: ParsedProcess              # EA stashes this, merges answer, re-calls

class UseTemplate(BaseModel):
    template_id: str
    confidence: float

GenerationResult = Generated | NeedsClarification | UseTemplate
```

---

## Node catalog (`n8n_catalog.py`)

Static data. No LLM. ~10 entries.

```python
@dataclass
class NodeSpec:
    n8n_type: str
    type_version: float
    param_builder: Callable[[StepSpec], dict]
    is_trigger: bool = False
```

| Key | n8n type | Resolver rule |
|---|---|---|
| `schedule` | `n8n-nodes-base.scheduleTrigger` v1.2 | `trigger.kind == "schedule"` |
| `webhook` | `n8n-nodes-base.webhook` v2 | `trigger.kind == "webhook"` |
| `manual` | `n8n-nodes-base.manualTrigger` v1 | fallback trigger |
| `http` | `n8n-nodes-base.httpRequest` v4.2 | **default for any step.service** |
| `if` | `n8n-nodes-base.if` v2 | `step.condition is not None` |
| `merge` | `n8n-nodes-base.merge` v3 | `len(step.inputs_from) > 1` |
| `set` | `n8n-nodes-base.set` v3.4 | transform step, no service |
| `email` | `n8n-nodes-base.emailSend` v2.1 | service ∈ {email, gmail, smtp} |
| `slack` | `n8n-nodes-base.slack` v2.2 | service == slack |
| `sheets` | `n8n-nodes-base.googleSheets` v4.5 | service ∈ {google sheets, sheets, spreadsheet} |

### Resolver

```python
def resolve_node(step: StepSpec) -> tuple[NodeSpec, list[str]]:
    # returns (spec, customization_notes)
```

Precedence:
1. `condition` set → `if`
2. `len(inputs_from) > 1` → `merge`
3. `service` in known service map → that node
4. `service` set but unknown → `http` + `["Configure {service} API endpoint in node '{name}'"]`
5. no service → `set`

Calendly and Stripe both hit rule 4. The `http` param builder emits:
```json
{"method": "GET", "url": "{{CONFIGURE: calendly endpoint}}", "authentication": "none"}
```
Importable. Obviously unfinished. The `{{CONFIGURE:}}` marker is greppable.

---

## Components

### ProcessParser

```python
async def parse(
    description: str,
    business_insights: dict,      # from BusinessLearningEngine
    template_hint: dict | None,   # {"triggers": [...], "actions": [...]} from matched template
    llm: BaseChatModel,
) -> ParsedProcess
```

Single gpt-4o call with `response_format=ParsedProcess` (langchain structured output). The prompt includes:

- The customer's description verbatim
- Tool entities pre-extracted by `BusinessLearningEngine` ("customer mentioned: calendly, stripe")
- If `template_hint`: "The likely shape is {hint}. Use this as a skeleton; override where the customer's description differs."
- Instructions: populate `gaps` with anything you had to guess. If the description is "automate my marketing," gaps should be long and confidence should be near zero.

No regex post-processing. The model's self-assessed `gaps`/`confidence` is the signal. This is a deliberate bet — the failure mode is the model being overconfident, which we catch in tests with adversarial vague inputs.

### WorkflowAssembler

```python
def assemble(parsed: ParsedProcess) -> tuple[N8nWorkflow, list[str]]
```

Deterministic. No LLM.

1. Build trigger node from `parsed.trigger` via catalog. Position `[250, 300]`.
2. For each `step[i]`:
   - `resolve_node(step)` → NodeSpec + customization notes
   - Build `N8nNode(name=titlecase(step.action), type=spec.n8n_type, ...)`, position `[250 + (i+1)*200, 300]`
   - Collect customization notes
3. Wire connections:
   - `inputs_from == []` → connect previous node's output here
   - `inputs_from == [j, k]` → both `steps[j]` and `steps[k]` get a connection entry pointing here
   - `if` nodes emit two output branches (`main[0]` = true, `main[1]` = false); next step after an IF wires to `main[0]` by default, the step after that to `main[1]` if its `inputs_from` references the IF
4. Construct `N8nWorkflow(...)` — validators fire here. Assembly either succeeds or raises `ValidationError`.

Returns `(workflow, customization_required)`.

### WorkflowExplainer

```python
def explain(workflow: N8nWorkflow, customization: list[str]) -> str
```

Deterministic template strings. No LLM — this is the human-in-the-loop confirmation and we don't want it to hallucinate.

Walks nodes in connection order (BFS from trigger):
```
Here's what I built:

1. Every Friday at 5pm (schedule trigger)
2. Fetch appointments from Calendly
3. Fetch payments from Stripe
4. Cross-reference appointments with payments (merge)
5. Keep only unpaid appointments (filter)
6. Send reschedule email

Before this can run, you'll need to:
- Configure Calendly API endpoint in node 'Fetch Appointments'
- Configure Stripe API endpoint in node 'Fetch Payments'
- Set up SMTP credentials for email sending
```

Node-type → verb phrase map lives next to the catalog.

### Orchestration — `generate()`

```python
async def generate(
    description: str,
    business_insights: dict,
    template_hint: dict | None = None,
    llm: BaseChatModel | None = None,
) -> GenerationResult:
    parsed = await parse(description, business_insights, template_hint, llm)

    if parsed.gaps or parsed.confidence < 0.6:
        return NeedsClarification(questions=parsed.gaps, partial=parsed)

    workflow, customization = assemble(parsed)  # raises on invalid — caller's bug if so
    explanation = explain(workflow, customization)

    return Generated(workflow=workflow, explanation=explanation,
                     customization_required=customization)
```

---

## Integration with `WorkflowCreator`

Replace the guts of `WorkflowCreator.create_workflow_from_conversation` (`executive_assistant.py:389-428`):

```python
async def create_workflow_from_conversation(self, description, context, business_insights):
    # 1. Template fast path
    match = await self.template_matcher.recommend_templates(business_insights)
    top = match["template_recommendations"][0] if match["template_recommendations"] else None

    if top and top["match_confidence"] >= 0.8:
        workflow = load_n8n_template(top["template_id"])  # templates/n8n/*.json
        return Generated(workflow=workflow, explanation=..., customization_required=[])

    # 2. Generation, possibly template-hinted
    hint = load_template_metadata(top["template_id"]) if top and top["match_confidence"] >= 0.5 else None
    result = await generate(description, business_insights, template_hint=hint, llm=self.llm)

    # 3. NeedsClarification bubbles up to LangGraph, which routes to _handle_clarification
    return result
```

Delete the old `_generate_n8n_workflow`, `_analyze_process_for_automation`, `_match_template_to_process` stubs.

The LangGraph needs a small change: when `create_workflow_from_conversation` returns `NeedsClarification`, the graph stashes `result.partial` on `ConversationState`, sets `requires_clarification=True`, and the `_handle_clarification` node asks `result.questions`. On the next turn, the merged description + partial go back into `generate()`.

---

## Template lifting

Convert `templates/report_generation.json` and `templates/invoice_generation.json` to real n8n workflows under `templates/n8n/`. Use `LAUNCH-Bot-Architecture.md:137-280` as the structural reference.

These serve three purposes:
1. Template fast-path payload (matcher confidence ≥ 0.8 → return this JSON directly)
2. Validator test fixtures (known-good workflows that must pass `N8nWorkflow` validation)
3. Reference for param_builder implementations

The other 5 templates stay as `{triggers, actions}` metadata — they still work as `template_hint` for the parser. Lift them later if needed.

---

## Testing

**Unit (`tests/unit/ai_ml/`)** — no services, no LLM:
- `test_n8n_schema.py` — validators: reject duplicate names, orphan nodes, dangling connection targets, zero triggers, two triggers. Accept the two lifted templates.
- `test_n8n_catalog.py` — resolver precedence, each param_builder produces a dict with required keys.
- `test_workflow_assembler.py` — fixture `ParsedProcess` objects → assert output validates. Cover: linear chain, branch (IF), merge, httpRequest fallback, customization notes populated.
- `test_workflow_explainer.py` — deterministic output for fixture workflows.
- `test_workflow_generator.py` — mock LLM returning fixture `ParsedProcess`. Low-confidence parse → `NeedsClarification`. High-confidence → `Generated`. Template hint reaches the parser prompt.

**Integration (`tests/integration/`)** — real LLM, marked `@pytest.mark.real_api`:
- `test_workflow_generation_e2e.py` — the Calendly/Stripe description produces a valid workflow with schedule trigger, ≥2 http nodes, a merge, an if, an emailSend. "Automate my marketing" produces `NeedsClarification`. Variation on report_generation uses the hint.

Existing coverage floor is 80% (`pyproject.toml:132`). New modules must clear it.

---

## Risks

| Risk | Mitigation |
|---|---|
| gpt-4o overconfident on vague inputs, returns empty `gaps` | Adversarial test cases ("automate stuff", "help with marketing"). Tune the parser prompt against them. If unsalvageable, add a secondary heuristic: `len(steps) < 2 and no services` → force clarification regardless. |
| n8n node typeVersions drift | Pin versions in catalog. They're already version-specific (httpRequest v4.2 ≠ v3). Document source of truth. |
| IF-node branch wiring is underspecified in `inputs_from` | Start with linear-after-IF (true branch only). Full branch support is a follow-up if customers describe else-cases. |
| LLM cost per generation | One call per description, not per turn. Clarification rounds re-parse the full merged text — 2-3 calls worst case. Acceptable for a workflow-creation flow. |
