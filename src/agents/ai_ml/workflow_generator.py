"""
Workflow Generator — natural-language process descriptions → n8n workflow JSON.

Pipeline:
    description ─► parse_process() ─► ParsedProcess(trigger, steps, confidence, missing)
                                           │
                       confidence < thresh ┴─► clarifying_questions (no workflow)
                                           │
                                  match_template() against templates/*.json
                                           │
                          ┌────────────────┼────────────────┐
                    TEMPLATE_EXACT   TEMPLATE_MODIFIED   GENERATE_FRESH
                          └────────────────┴────────────────┘
                                           │
                                  compile_to_n8n() ── N8nNodeCatalog
                                           │
                                  validate() ─► structural checks
                                           │
                                  explain()  ─► plain-language steps

This sits alongside BusinessLearningEngine (entity extraction) and
WorkflowTemplateMatcher (metadata recommendations). Where those stop at
"here's a template that might fit," this module produces an actual n8n
workflow JSON that imports cleanly — or, when the description is too vague,
a list of targeted questions to close the gaps.

n8n workflow schema (confirmed against n8n-io/n8n-docs):
    {
      "name": str,
      "nodes": [{"name", "type", "typeVersion", "position": [x,y], "parameters": {}}],
      "connections": {"<NodeName>": {"main": [[{"node": "<Target>", "type": "main", "index": 0}]]}},
      "settings": {},
      "active": bool
    }
Connections are keyed by node *name*, not id. IF nodes emit two output
groups (main[0] = true branch, main[1] = false branch).
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from templates.template_registry import list_templates

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intermediate representation
# ---------------------------------------------------------------------------

@dataclass
class TriggerSpec:
    """What starts the workflow."""
    kind: str                         # "schedule" | "webhook" | "manual"
    schedule: Optional[str] = None    # cron expression when kind == "schedule"
    event: Optional[str] = None       # event description when kind == "webhook"
    raw: str = ""                     # original text fragment, for explanation


@dataclass
class StepSpec:
    """One action in the process graph.

    `depends_on` holds indices into the steps list. A linear chain has each
    step depend on exactly the previous one; a merge step depends on two or
    more upstream fetches; a condition step carries a `condition` string and
    downstream steps may depend on its true-branch output.
    """
    action: str                       # canonical verb: fetch, merge, filter, send_email, notify, transform, wait, ...
    description: str                  # human-readable step summary (for explanation)
    tool: Optional[str] = None        # normalized tool name: stripe, slack, calendly, ...
    depends_on: List[int] = field(default_factory=list)
    condition: Optional[str] = None   # condition text when this step gates on a predicate
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedProcess:
    """Structured extraction of a natural-language process description."""
    trigger: Optional[TriggerSpec]
    steps: List[StepSpec]
    confidence: float
    missing: List[str] = field(default_factory=list)
    raw_description: str = ""


class GenerationStrategy(Enum):
    TEMPLATE_EXACT = "template_exact"
    TEMPLATE_MODIFIED = "template_modified"
    GENERATE_FRESH = "generate_fresh"


@dataclass
class GenerationResult:
    """Output of WorkflowGenerator.generate()."""
    workflow: Optional[Dict[str, Any]]
    explanation: List[str]
    clarifying_questions: List[str]
    strategy: Optional[GenerationStrategy]
    confidence: float
    source_template: Optional[str] = None
    parsed: Optional[ParsedProcess] = None


# ---------------------------------------------------------------------------
# N8n node catalog — tool & action → node type mapping
# ---------------------------------------------------------------------------

class N8nNodeCatalog:
    """Maps tool names and canonical actions to n8n node specs.

    Tools with dedicated n8n-nodes-base integrations get mapped directly.
    Everything else falls back to httpRequest — structurally sound, the
    customer wires credentials later.
    """

    # Tools that ship as n8n-nodes-base.* integrations. Keyed by normalized
    # tool name, value is (node_type, typeVersion, default_params_by_action).
    TOOL_NODES: Dict[str, Tuple[str, int, Dict[str, Dict]]] = {
        "stripe":        ("n8n-nodes-base.stripe",        1, {"fetch": {"resource": "charge", "operation": "getAll"}}),
        "slack":         ("n8n-nodes-base.slack",         2, {"notify": {"resource": "message", "operation": "post"}}),
        "gmail":         ("n8n-nodes-base.gmail",         2, {"send_email": {"resource": "message", "operation": "send"}}),
        "google sheets": ("n8n-nodes-base.googleSheets",  4, {"fetch": {"operation": "read"}, "append": {"operation": "append"}}),
        "hubspot":       ("n8n-nodes-base.hubspot",       2, {"fetch": {"resource": "contact", "operation": "getAll"}}),
        "salesforce":    ("n8n-nodes-base.salesforce",    1, {"fetch": {"resource": "lead", "operation": "getAll"}}),
        "airtable":      ("n8n-nodes-base.airtable",      2, {"fetch": {"operation": "list"}, "append": {"operation": "append"}}),
        "shopify":       ("n8n-nodes-base.shopify",       1, {"fetch": {"resource": "order", "operation": "getAll"}}),
        "mailchimp":     ("n8n-nodes-base.mailchimp",     1, {}),
        "trello":        ("n8n-nodes-base.trello",        1, {}),
        "asana":         ("n8n-nodes-base.asana",         1, {}),
        "notion":        ("n8n-nodes-base.notion",        2, {}),
        "discord":       ("n8n-nodes-base.discord",       1, {"notify": {"resource": "message"}}),
        "twilio":        ("n8n-nodes-base.twilio",        1, {"notify": {"resource": "sms", "operation": "send"}}),
        "google drive":  ("n8n-nodes-base.googleDrive",   3, {"store": {"operation": "upload"}}),
        "drive":         ("n8n-nodes-base.googleDrive",   3, {"store": {"operation": "upload"}}),
        "instagram":     ("n8n-nodes-base.facebookGraphApi", 1, {}),  # IG business API goes through FB Graph
        "quickbooks":    ("n8n-nodes-base.quickbooks",    1, {}),
    }

    # Canonical actions that map to core n8n utility nodes regardless of tool.
    ACTION_NODES: Dict[str, Tuple[str, int, Dict]] = {
        "wait":        ("n8n-nodes-base.wait",      1, {"resume": "timeInterval"}),
        "filter":      ("n8n-nodes-base.filter",    2, {}),
        "merge":       ("n8n-nodes-base.merge",     3, {"mode": "combine", "combinationMode": "mergeByPosition"}),
        "transform":   ("n8n-nodes-base.set",       3, {"mode": "manual"}),
        "send_email":  ("n8n-nodes-base.emailSend", 2, {}),
        "compare":     ("n8n-nodes-base.if",        2, {}),
        "aggregate":   ("n8n-nodes-base.aggregate", 1, {}),
    }

    def resolve_tool(self, tool: str, action: str = "fetch") -> Dict[str, Any]:
        """Return a node spec for a tool + action pair. Falls back to httpRequest."""
        tool = tool.lower().strip()
        if tool in self.TOOL_NODES:
            node_type, version, action_params = self.TOOL_NODES[tool]
            return {
                "type": node_type,
                "typeVersion": version,
                "parameters": dict(action_params.get(action, {})),
            }
        # No dedicated node — structurally valid httpRequest placeholder.
        return {
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4,
            "parameters": {
                "method": "GET",
                "url": f"https://api.{tool}.com/",
                "options": {},
            },
        }

    def resolve_action(self, action: str) -> Dict[str, Any]:
        """Return a node spec for a tool-agnostic action."""
        if action in self.ACTION_NODES:
            node_type, version, params = self.ACTION_NODES[action]
            return {"type": node_type, "typeVersion": version, "parameters": dict(params)}
        # Unknown action → noOp keeps the graph connected without side effects.
        return {"type": "n8n-nodes-base.noOp", "typeVersion": 1, "parameters": {}}

    def resolve_trigger(self, trigger: TriggerSpec) -> Dict[str, Any]:
        """Return a trigger node spec."""
        if trigger.kind == "schedule":
            return {
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1,
                "parameters": {
                    "rule": {"interval": [{"field": "cronExpression", "expression": trigger.schedule}]}
                },
            }
        if trigger.kind == "webhook":
            return {
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "parameters": {"httpMethod": "POST", "path": str(uuid.uuid4())[:8], "options": {}},
            }
        return {"type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}}


# ---------------------------------------------------------------------------
# Parsing: description → ParsedProcess
# ---------------------------------------------------------------------------

# Weekday → cron day-of-week (n8n uses 0=Sunday … 6=Saturday).
_WEEKDAYS = {
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}

# Known tool names — superset of BusinessLearningEngine's list plus tools
# customers actually mention (Calendly, Stripe, etc.).
_KNOWN_TOOLS = sorted(
    set(N8nNodeCatalog.TOOL_NODES.keys()) | {
        "calendly", "zoom", "excel", "facebook", "twitter", "linkedin",
        "zapier", "pipedrive", "zendesk", "intercom", "freshbooks",
        "paypal", "xero", "google calendar", "whatsapp", "email",
    },
    key=len, reverse=True,  # match longer names first ("google sheets" before "sheets")
)

# Verb → canonical action. Rule-based like BusinessLearningEngine's patterns.
# Order matters — first match wins.
_ACTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # merge — patterns that combine two data streams
    (re.compile(r"\bcross[-\s]?referenc", re.I), "merge"),
    (re.compile(r"\b(?:combin|join|match up|reconcil)\w*\b.*\bwith\b", re.I), "merge"),
    # filter — selecting a subset
    (re.compile(r"\b(?:flag|filter|find)\w*\b.*\b(?:who|that|where|anyone)\b", re.I), "filter"),
    (re.compile(r"\bonly\s+(?:keep|include|those)\b", re.I), "filter"),
    # compare — conditional branching
    (re.compile(r"\bcompar\w*\b", re.I), "compare"),
    # aggregate
    (re.compile(r"\b(?:aggregat|summari[sz]|total|sum up|tally)\w*\b", re.I), "aggregate"),
    # email
    (re.compile(r"\b(?:email|e-mail)\w*\b", re.I), "send_email"),
    # notify (Slack/SMS/etc.)
    (re.compile(r"\b(?:slack|notify|alert|ping|message|sms|text)\b", re.I), "notify"),
    # store / upload
    (re.compile(r"\b(?:stor|sav|upload|archiv)\w*\b", re.I), "store"),
    # append / log
    (re.compile(r"\b(?:log|append|record|add\s+to)\b", re.I), "append"),
    # wait
    (re.compile(r"\b(?:wait|delay|pause)\b", re.I), "wait"),
    # transform
    (re.compile(r"\b(?:generat|creat|build|transform|format|convert)\w*\b", re.I), "transform"),
    # fetch — broadest; keep last
    (re.compile(r"\b(?:export|fetch|pull|get|retriev|download|extract|read|load|list|grab)\w*\b", re.I), "fetch"),
]

# Phrases that mark a clause as conditional on a preceding check.
_CONDITION_MARKERS = re.compile(r"\b(?:if|when|unless|only if|only when)\b", re.I)

# Verbs too vague to act on — used for confidence penalty.
_VAGUE_VERBS = re.compile(r"\b(?:handle|deal with|manage|process|automate|streamline|improve|optimi[sz]e|help with|take care of)\b", re.I)


def _extract_trigger(text: str) -> Tuple[Optional[TriggerSpec], str]:
    """Pull the trigger clause off the front of the description.

    Returns (trigger, remaining_text).
    """
    lower = text.lower()

    # Schedule triggers: "every <weekday>", "every day", "each week", "daily", etc.
    # Try weekday first — most specific.
    for day, cron_dow in _WEEKDAYS.items():
        m = re.search(rf"\bevery\s+{day}\b(?:\s+(?:morning|afternoon|evening|at\s+\d+\s*(?:am|pm)?))?", lower)
        if m:
            hour = 9  # default morning
            hour_match = re.search(r"at\s+(\d+)\s*(am|pm)?", m.group(0))
            if hour_match:
                hour = int(hour_match.group(1))
                if hour_match.group(2) == "pm" and hour < 12:
                    hour += 12
            elif "afternoon" in m.group(0):
                hour = 14
            elif "evening" in m.group(0):
                hour = 18
            cron = f"0 {hour} * * {cron_dow}"
            remaining = text[:m.start()] + text[m.end():]
            return TriggerSpec(kind="schedule", schedule=cron, raw=text[m.start():m.end()]), remaining.strip(" ,.")

    # Every day / daily
    m = re.search(r"\b(?:every\s+day|daily|each\s+day)\b(?:\s+at\s+(\d+)\s*(am|pm)?)?", lower)
    if m:
        hour = 9
        if m.group(1):
            hour = int(m.group(1))
            if m.group(2) == "pm" and hour < 12:
                hour += 12
        return TriggerSpec(kind="schedule", schedule=f"0 {hour} * * *", raw=text[m.start():m.end()]), \
               (text[:m.start()] + text[m.end():]).strip(" ,.")

    # Every week / weekly (no specific day) → Monday by convention
    m = re.search(r"\b(?:every\s+week|weekly|each\s+week)\b", lower)
    if m:
        return TriggerSpec(kind="schedule", schedule="0 9 * * 1", raw=text[m.start():m.end()]), \
               (text[:m.start()] + text[m.end():]).strip(" ,.")

    # Every month / monthly → 1st of month
    m = re.search(r"\b(?:every\s+month|monthly|each\s+month)\b", lower)
    if m:
        return TriggerSpec(kind="schedule", schedule="0 9 1 * *", raw=text[m.start():m.end()]), \
               (text[:m.start()] + text[m.end():]).strip(" ,.")

    # Event triggers: "when X happens", "whenever X", "after X"
    m = re.search(r"\b(?:when(?:ever)?|after|as soon as|once)\s+(?:a\s+|an\s+|the\s+)?(.+?)(?:,|\bthen\b|$)", lower)
    if m:
        event = m.group(1).strip()
        return TriggerSpec(kind="webhook", event=event, raw=text[m.start():m.end()]), \
               (text[:m.start()] + text[m.end():]).strip(" ,.")

    # No trigger phrase → manual.
    return TriggerSpec(kind="manual", raw=""), text


def _split_into_clauses(text: str) -> List[str]:
    """Segment the post-trigger text into ordered action clauses.

    Splits on sequence markers and the Oxford-comma-and, preserving order.
    """
    # Normalize sequence markers to a single delimiter.
    text = re.sub(r"\s*;\s*", " || ", text)
    text = re.sub(r"\s*,\s*(?:and\s+)?then\s+", " || ", text, flags=re.I)
    text = re.sub(r"\s*\bthen\b\s+", " || ", text, flags=re.I)
    text = re.sub(r"\s*\b(?:next|after that|afterwards?|finally)\b\s*,?\s*", " || ", text, flags=re.I)
    # Split on ", and" / ", " between clauses — conservative: only split on
    # comma followed by a word that looks like a verb (avoids splitting
    # "appointments, payments" mid-clause).
    text = re.sub(
        r",\s+(?:and\s+)?(?=(?:export|fetch|pull|get|send|email|slack|notify|stor|sav|log|flag|filter|cross|compar|combin|join|aggregat|generat|creat|build|transform|check|post|upload|add|record|list|grab)\w*\b)",
        " || ", text, flags=re.I,
    )
    clauses = [c.strip(" ,.") for c in text.split("||") if c.strip(" ,.")]
    return clauses


def _classify_clause(clause: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (action, tool, condition) for one clause."""
    lower = clause.lower()

    # Tool: first known tool mentioned in the clause.
    tool = None
    for t in _KNOWN_TOOLS:
        if t in lower:
            tool = t
            break

    # Action: first matching pattern.
    action = "transform"  # fallback
    for pattern, act in _ACTION_PATTERNS:
        if pattern.search(clause):
            action = act
            break

    # Condition: clause contains "if/when/..." — capture the condition phrase.
    condition = None
    cm = _CONDITION_MARKERS.search(clause)
    if cm:
        condition = clause[cm.start():].strip()

    # Refinement: "Slack me" / "Slack the team" → tool is slack, action is notify.
    if tool == "slack" and action not in ("notify", "send_email"):
        action = "notify"
    # "email" in the tool list catches the verb "emails them" — that's an
    # action, not a service. Only treat it as a tool if it's clearly a noun
    # ("via email", "through email", "in email").
    if tool == "email":
        if action == "send_email" or not re.search(r"\b(?:via|through|in|from)\s+email\b", lower):
            tool = None
            if action == "transform":
                action = "send_email"
    if tool in ("drive", "google drive") and action == "transform":
        action = "store"

    return action, tool, condition


def _parse_steps(clauses: List[str]) -> List[StepSpec]:
    """Build the step list with dependencies wired.

    Default: each step depends on the immediately preceding step (linear chain).
    Merge steps depend on all prior fetch steps (they combine streams).
    A condition on a step gates the *downstream* step — but for simplicity
    we keep the condition on the step itself and let the compiler decide
    whether to emit an IF node.
    """
    steps: List[StepSpec] = []
    fetch_indices: List[int] = []

    for i, clause in enumerate(clauses):
        action, tool, condition = _classify_clause(clause)

        if action == "merge":
            # Merge combines prior data streams. If this clause also mentions a
            # tool ("cross-reference with Stripe"), that's an *additional* fetch
            # that feeds the merge.
            if tool:
                fetch_step = StepSpec(
                    action="fetch",
                    description=f"fetch data from {tool.title()}",
                    tool=tool,
                    depends_on=[len(steps) - 1] if steps else [],
                )
                steps.append(fetch_step)
                fetch_indices.append(len(steps) - 1)
            depends = list(fetch_indices) if len(fetch_indices) >= 2 else ([len(steps) - 1] if steps else [])
            steps.append(StepSpec(action="merge", description=clause, depends_on=depends))
            continue

        depends = [len(steps) - 1] if steps else []
        step = StepSpec(
            action=action,
            description=clause,
            tool=tool,
            depends_on=depends,
            condition=condition,
        )
        steps.append(step)
        if action == "fetch":
            fetch_indices.append(len(steps) - 1)

    return steps


def _score_confidence(trigger: Optional[TriggerSpec], steps: List[StepSpec], raw: str) -> Tuple[float, List[str]]:
    """Confidence ∈ [0,1] plus a list of concrete gaps.

    Heuristics mirror what the spec calls out: vague descriptions score low,
    specific multi-step descriptions with identified tools score high.
    """
    missing: List[str] = []
    score = 0.0

    # Trigger: scheduled/webhook triggers are explicit signals. A manual
    # trigger isn't wrong, but it's a gap worth asking about — the customer
    # may have just forgotten to mention the schedule.
    if trigger and trigger.kind in ("schedule", "webhook"):
        score += 0.25
    else:
        score += 0.05
        missing.append("trigger")

    # Steps: need at least two concrete actions to call this a "process".
    if len(steps) >= 2:
        score += 0.2
        # Reward identified tools on fetch/notify/store steps (the ones that
        # touch external systems).
        needs_tool = [s for s in steps if s.action in ("fetch", "notify", "store", "append", "send_email")]
        if needs_tool:
            with_tool = sum(1 for s in needs_tool if s.tool)
            score += 0.35 * (with_tool / len(needs_tool))
            for s in needs_tool:
                if not s.tool and s.action != "send_email":  # email doesn't strictly need a named tool
                    missing.append(f"tool for '{s.description[:40]}'")
        else:
            # No external touchpoints at all — probably too abstract.
            missing.append("tools")
    elif len(steps) == 1:
        score += 0.05
        missing.append("steps")
        if not steps[0].tool:
            missing.append("tools")
    else:
        missing.append("steps")
        missing.append("tools")

    # Penalize vague framing in the original text.
    vague_hits = len(_VAGUE_VERBS.findall(raw))
    score -= 0.1 * vague_hits

    # Reward sequence structure — multiple distinct actions in order.
    distinct_actions = len({s.action for s in steps})
    if distinct_actions >= 3:
        score += 0.15
    elif distinct_actions == 2:
        score += 0.08

    return max(0.0, min(1.0, score)), missing


# ---------------------------------------------------------------------------
# Template matching against templates/*.json
# ---------------------------------------------------------------------------

# Map intermediate-template action types (templates/template_validator.py) to
# our canonical actions, so parsed steps and template actions compare cleanly.
_TEMPLATE_ACTION_MAP = {
    "send_email": "send_email",
    "send_welcome": "send_email",
    "send_reminder": "send_email",
    "send_summary": "send_email",
    "notify_customer": "notify",
    "notify_sales": "notify",
    "generate_invoice": "transform",
    "generate_report": "transform",
    "generate_content": "transform",
    "aggregate_metrics": "aggregate",
    "log_crm": "append",
    "log_accounting": "append",
    "store_report": "store",
    "wait": "wait",
    "classify_lead": "transform",
    "enrich_data": "fetch",
    "route_lead": "filter",
    "check_availability": "fetch",
    "propose_times": "transform",
    "confirm_booking": "transform",
    "schedule_post": "transform",
    "schedule_discovery_call": "transform",
    "conduct_business_discovery": "transform",
    "create_first_automation": "transform",
}


def _template_trigger_kind(template: Dict) -> str:
    """Map a template's first trigger to our trigger kind."""
    triggers = template.get("triggers", [])
    if not triggers:
        return "manual"
    t = triggers[0].get("type", "")
    if t == "schedule":
        return "schedule"
    if t in ("webhook", "event", "message"):
        return "webhook"
    return "manual"


def _template_actions(template: Dict) -> List[str]:
    """Canonical action list for a template."""
    return [_TEMPLATE_ACTION_MAP.get(a.get("type", ""), "transform") for a in template.get("actions", [])]


def _match_against_templates(parsed: ParsedProcess, templates: List[Dict]) -> Tuple[Optional[Dict], float]:
    """Return (best_template, similarity) or (None, 0.0).

    Similarity = trigger match (0.3) + action-set Jaccard (0.7).
    This is deliberately structural — we're matching *what the process does*,
    not keywords, so a customer describing the same flow with different
    vocabulary still matches.
    """
    if not parsed.trigger or not parsed.steps:
        return None, 0.0

    parsed_actions = [s.action for s in parsed.steps]
    parsed_action_set = set(parsed_actions)
    best = None
    best_score = 0.0

    for tpl in templates:
        # Trigger alignment.
        trig_score = 0.3 if _template_trigger_kind(tpl) == parsed.trigger.kind else 0.0

        # Action overlap (Jaccard).
        tpl_actions = set(_template_actions(tpl))
        if not tpl_actions or not parsed_action_set:
            continue
        intersection = parsed_action_set & tpl_actions
        union = parsed_action_set | tpl_actions
        jaccard = len(intersection) / len(union)
        action_score = 0.7 * jaccard

        total = trig_score + action_score
        if total > best_score:
            best_score = total
            best = tpl

    return best, best_score


def _template_to_steps(template: Dict) -> List[StepSpec]:
    """Compile a template's intermediate actions into StepSpecs (linear chain)."""
    steps: List[StepSpec] = []
    for i, act in enumerate(template.get("actions", [])):
        atype = act.get("type", "")
        canonical = _TEMPLATE_ACTION_MAP.get(atype, "transform")
        # Try to infer a tool from the action params.
        tool = None
        for v in act.values():
            if isinstance(v, str) and v.lower() in _KNOWN_TOOLS:
                tool = v.lower()
                break
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item.lower() in _KNOWN_TOOLS:
                        tool = item.lower()
                        break
        steps.append(StepSpec(
            action=canonical,
            description=atype.replace("_", " "),
            tool=tool,
            depends_on=[i - 1] if i > 0 else [],
            params=dict(act),
        ))
    return steps


def _template_to_trigger(template: Dict) -> TriggerSpec:
    """Compile a template's first trigger into a TriggerSpec."""
    triggers = template.get("triggers", [])
    if not triggers:
        return TriggerSpec(kind="manual")
    t = triggers[0]
    ttype = t.get("type", "")
    if ttype == "schedule":
        return TriggerSpec(kind="schedule", schedule=t.get("cron", "0 9 * * 1"), raw=t.get("cron", ""))
    if ttype in ("webhook", "event", "message"):
        return TriggerSpec(kind="webhook", event=t.get("event") or t.get("source") or t.get("intent", ""), raw=ttype)
    return TriggerSpec(kind="manual")


# ---------------------------------------------------------------------------
# n8n compilation
# ---------------------------------------------------------------------------

def _if_node_spec(condition_text: str) -> Dict[str, Any]:
    """Build an n8n IF node. The condition text is preserved as a placeholder
    expression — the customer wires the actual field reference when they
    configure credentials. Structurally valid per n8n-nodes-base.if v2."""
    return {
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "parameters": {
            "conditions": {
                "combinator": "and",
                "conditions": [{
                    "leftValue": "={{ $json.value }}",
                    "rightValue": condition_text,
                    "operator": {"type": "string", "operation": "contains"},
                }],
            },
        },
    }


def _resolve_step_node(step: StepSpec, catalog: N8nNodeCatalog) -> Tuple[Dict[str, Any], str]:
    """Pick the n8n node for a step and a human-readable base name."""
    if step.tool:
        return catalog.resolve_tool(step.tool, step.action), step.tool.title()
    return catalog.resolve_action(step.action), step.action.replace("_", " ").title()


def _compile_to_n8n(
    name: str,
    trigger: TriggerSpec,
    steps: List[StepSpec],
    catalog: N8nNodeCatalog,
) -> Dict[str, Any]:
    """Emit an n8n workflow dict from trigger + steps.

    Layout: trigger at x=240, subsequent columns at +200px per dependency depth.
    Connections keyed by node name — n8n import requirement.
    """
    nodes: List[Dict[str, Any]] = []
    connections: Dict[str, Dict[str, List[List[Dict]]]] = {}
    used_names: Dict[str, int] = {}

    def unique_name(base: str) -> str:
        n = used_names.get(base, 0)
        used_names[base] = n + 1
        return base if n == 0 else f"{base} {n + 1}"

    # Trigger node.
    trig_spec = catalog.resolve_trigger(trigger)
    trigger_name = unique_name("Schedule Trigger" if trigger.kind == "schedule"
                               else "Webhook" if trigger.kind == "webhook"
                               else "Manual Trigger")
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": trigger_name,
        "type": trig_spec["type"],
        "typeVersion": trig_spec["typeVersion"],
        "position": [240, 300],
        "parameters": trig_spec["parameters"],
    })

    # Each step may emit one or two nodes:
    #   - Normally: one node for the action.
    #   - With a condition: an IF gate node + the action node on its true branch.
    #     ("Slack me if X" → IF(X) → Slack, not IF-as-Slack.)
    #
    # For downstream wiring we track two names per step:
    #   inbound[i]  — the node that receives edges *from* this step's dependencies
    #   outbound[i] — the node that sends edges *to* steps depending on this one
    # For unconditioned steps both point to the same node. For conditioned
    # steps, inbound is the IF gate and outbound is the action.
    inbound_name: List[str] = []
    outbound_name: List[str] = []
    outbound_is_if: List[bool] = []  # True when the outbound node is an IF (compare steps)
    if_node_names: List[str] = []    # all IF nodes, for ensuring two output groups

    # Layout depth per step (longest dependency chain) for x positioning.
    depth = [0] * len(steps)
    for i, s in enumerate(steps):
        depth[i] = 1 + max((depth[d] for d in s.depends_on), default=0)

    y_cursor: Dict[int, int] = {}  # depth → next free y slot

    def place(d: int) -> Tuple[int, int]:
        slot = y_cursor.get(d, 0)
        y_cursor[d] = slot + 1
        return 240 + 200 * d, 300 + 160 * slot

    def make_node(spec: Dict[str, Any], base_name: str, d: int) -> str:
        name = unique_name(base_name)
        x, y = place(d)
        nodes.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "type": spec["type"],
            "typeVersion": spec["typeVersion"],
            "position": [x, y],
            "parameters": spec["parameters"],
        })
        return name

    for i, step in enumerate(steps):
        d = depth[i]

        # A bare `compare` step IS the IF node — no separate action follows.
        # Any other step with a condition gets an IF gate in front of it.
        if step.action == "compare":
            if_name = make_node(_if_node_spec(step.condition or step.description), "If", d)
            if_node_names.append(if_name)
            inbound_name.append(if_name)
            outbound_name.append(if_name)
            outbound_is_if.append(True)
            continue

        if step.condition:
            # Gate first, action on its true branch one column to the right.
            if_name = make_node(_if_node_spec(step.condition), "If", d)
            if_node_names.append(if_name)
            action_spec, action_base = _resolve_step_node(step, catalog)
            action_name = make_node(action_spec, action_base, d + 1)
            # Wire the gate's true-branch to the action.
            connections.setdefault(if_name, {"main": [[], []]})
            connections[if_name]["main"][0].append({"node": action_name, "type": "main", "index": 0})
            inbound_name.append(if_name)
            outbound_name.append(action_name)
            outbound_is_if.append(False)
            continue

        spec, base = _resolve_step_node(step, catalog)
        node_name = make_node(spec, base, d)
        inbound_name.append(node_name)
        outbound_name.append(node_name)
        outbound_is_if.append(False)

    # Wire dependencies. Targets are inbound[i]; sources are outbound[dep].
    def add_edge(src: str, dst: str, src_is_if: bool):
        entry = connections.setdefault(src, {"main": [[], []] if src_is_if else [[]]})
        if src_is_if and len(entry["main"]) < 2:
            entry["main"].append([])
        entry["main"][0].append({"node": dst, "type": "main", "index": 0})

    for i, step in enumerate(steps):
        dst = inbound_name[i]
        if not step.depends_on:
            add_edge(trigger_name, dst, src_is_if=False)
        else:
            for dep_idx in step.depends_on:
                add_edge(outbound_name[dep_idx], dst, src_is_if=outbound_is_if[dep_idx])

    # Every IF node must expose two output groups even if one branch is empty.
    for if_name in if_node_names:
        entry = connections.setdefault(if_name, {"main": [[], []]})
        while len(entry["main"]) < 2:
            entry["main"].append([])

    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "active": False,
        "staticData": None,
    }


def _validate_n8n(workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Structural validation — the checks the spec calls out explicitly:
    correct node types, valid connections, no orphans, required params present.
    """
    errors: List[str] = []

    for key in ("name", "nodes", "connections", "settings"):
        if key not in workflow:
            errors.append(f"missing top-level key: {key}")
    if errors:
        return False, errors

    nodes = workflow["nodes"]
    connections = workflow["connections"]
    node_names = set()

    for n in nodes:
        for field_name in ("name", "type", "typeVersion", "position", "parameters"):
            if field_name not in n:
                errors.append(f"node missing '{field_name}': {n.get('name', '?')}")
        if "name" in n:
            if n["name"] in node_names:
                errors.append(f"duplicate node name: {n['name']}")
            node_names.add(n["name"])
        if "type" in n and not n["type"].startswith("n8n-nodes-base."):
            errors.append(f"non-standard node type: {n['type']}")
        if "position" in n and (not isinstance(n["position"], list) or len(n["position"]) != 2):
            errors.append(f"node '{n.get('name')}' position must be [x, y]")

    # Connections: source and target must exist.
    targets: set = set()
    for src, out in connections.items():
        if src not in node_names:
            errors.append(f"connection source '{src}' does not exist")
        for group in out.get("main", []):
            for link in group:
                tgt = link.get("node")
                if tgt not in node_names:
                    errors.append(f"connection target '{tgt}' does not exist")
                targets.add(tgt)
                if link.get("type") != "main":
                    errors.append(f"connection from '{src}' to '{tgt}' has non-main type")

    # Disconnected nodes: no inbound edge AND no outbound edge.
    # A real trigger has outbound, a real leaf has inbound — anything with
    # neither is floating and n8n will import it as dead weight.
    if len(node_names) > 1:
        sources = set(connections.keys())
        disconnected = node_names - targets - sources
        if disconnected:
            errors.append(f"orphaned nodes (no connections): {sorted(disconnected)}")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------

_CRON_DOW_NAMES = {str(v): k.capitalize() for k, v in _WEEKDAYS.items()}


def _explain_trigger(trigger: TriggerSpec) -> str:
    if trigger.kind == "schedule":
        if trigger.raw:
            return f"Runs {trigger.raw.lower()}."
        # Fall back to decoding the cron.
        parts = (trigger.schedule or "").split()
        if len(parts) == 5:
            minute, hour, dom, month, dow = parts
            if dow in _CRON_DOW_NAMES:
                return f"Runs every {_CRON_DOW_NAMES[dow]} at {hour}:00."
            if dow == "*" and dom == "*":
                return f"Runs every day at {hour}:00."
            if dom != "*":
                return f"Runs on day {dom} of each month at {hour}:00."
        return "Runs on a schedule."
    if trigger.kind == "webhook":
        return f"Starts when {trigger.event or 'an external event is received'}."
    return "Runs when you start it manually."


_ACTION_PHRASES = {
    "fetch":      "pull data from {tool}",
    "merge":      "combine the results",
    "filter":     "keep only the items that match",
    "compare":    "check the condition",
    "aggregate":  "roll the data up into a summary",
    "transform":  "build the output",
    "send_email": "send an email",
    "notify":     "send a {tool} notification",
    "store":      "save the result to {tool}",
    "append":     "log the result to {tool}",
    "wait":       "pause before continuing",
}


def _explain_steps(steps: List[StepSpec]) -> List[str]:
    lines: List[str] = []
    for i, s in enumerate(steps, 1):
        template = _ACTION_PHRASES.get(s.action, s.action.replace("_", " "))
        tool_name = (s.tool or "").title() or "the service"
        phrase = template.format(tool=tool_name)
        if s.condition:
            phrase = f"if the condition holds ({s.condition}), {phrase}"
        # Prefer the parsed description when it's more specific than the template.
        if s.description and len(s.description) > len(phrase) and s.action not in ("merge",):
            phrase = s.description
        lines.append(f"{i}. {phrase[0].upper()}{phrase[1:]}.")
    return lines


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

class WorkflowGenerator:
    """Turns conversational process descriptions into n8n workflows.

    Public surface:
        generate(description)            -> GenerationResult (async)
        parse_process(description)       -> ParsedProcess
        generate_clarifying_questions(p) -> List[str]
        validate_n8n_workflow(wf)        -> (bool, [errors])
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = {
            "generation_threshold": 0.6,
            "template_exact_threshold": 0.78,
            "template_modify_threshold": 0.55,
            **(config or {}),
        }
        self.catalog = N8nNodeCatalog()
        self._templates = list_templates()
        logger.info(f"WorkflowGenerator initialized with {len(self._templates)} templates")

    # ---- Parsing ------------------------------------------------------------

    def parse_process(self, description: str) -> ParsedProcess:
        description = description.strip()
        trigger, body = _extract_trigger(description)
        clauses = _split_into_clauses(body)
        steps = _parse_steps(clauses)
        confidence, missing = _score_confidence(trigger, steps, description)
        return ParsedProcess(
            trigger=trigger,
            steps=steps,
            confidence=confidence,
            missing=missing,
            raw_description=description,
        )

    # ---- Clarifying questions ----------------------------------------------

    def generate_clarifying_questions(self, parsed: ParsedProcess) -> List[str]:
        questions: List[str] = []

        if "trigger" in parsed.missing or (parsed.trigger and parsed.trigger.kind == "manual" and len(parsed.steps) >= 2):
            questions.append("When should this run — on a schedule (daily, weekly?) or when something specific happens?")

        if "steps" in parsed.missing:
            questions.append("Can you walk me through the steps one at a time? What happens first, then what?")

        # Ask about specific steps missing tools — targeted, not generic.
        for gap in parsed.missing:
            if gap.startswith("tool for"):
                step_desc = gap[len("tool for '"):-1]
                questions.append(f"What service or tool do you use to {step_desc.lower()}?")

        if "tools" in parsed.missing and not any(q.startswith("What service") for q in questions):
            questions.append("Which tools are involved here — where does the data come from and where does it go?")

        # If the description is dominated by vague verbs, ask for concreteness.
        if _VAGUE_VERBS.search(parsed.raw_description) and len(parsed.steps) < 2:
            questions.append("What specifically do you do today — manually — that you'd like automated?")

        return questions

    # ---- Template matching --------------------------------------------------

    def _resolve_strategy(self, parsed: ParsedProcess) -> Tuple[GenerationStrategy, Optional[Dict], float]:
        tpl, score = _match_against_templates(parsed, self._templates)
        if not tpl or score < self.config["template_modify_threshold"]:
            return GenerationStrategy.GENERATE_FRESH, None, score

        # Even a high-similarity match is a variation — not an exact fit — if
        # the customer's process includes actions or tools the template doesn't
        # cover. That's the "close but has variations" case from the spec.
        tpl_actions = set(_template_actions(tpl))
        parsed_actions = {s.action for s in parsed.steps}
        parsed_tools = {s.tool for s in parsed.steps if s.tool}
        tpl_tools = {s.tool for s in _template_to_steps(tpl) if s.tool}
        has_extras = bool(parsed_actions - tpl_actions) or bool(parsed_tools - tpl_tools)

        if score >= self.config["template_exact_threshold"] and not has_extras:
            return GenerationStrategy.TEMPLATE_EXACT, tpl, score
        return GenerationStrategy.TEMPLATE_MODIFIED, tpl, score

    def _merge_with_template(self, template: Dict, parsed: ParsedProcess) -> Tuple[TriggerSpec, List[StepSpec]]:
        """Start from the template's steps, then append parsed steps whose
        actions aren't already covered. Keeps the template as the backbone
        and adds the customer's variations at the end of the chain.
        """
        tpl_trigger = _template_to_trigger(template)
        tpl_steps = _template_to_steps(template)
        tpl_actions = {s.action for s in tpl_steps}

        # Prefer the parsed trigger when it's more specific than the template's.
        trigger = parsed.trigger if parsed.trigger and parsed.trigger.kind != "manual" else tpl_trigger

        # Parsed steps not already covered by the template.
        extras: List[StepSpec] = []
        for s in parsed.steps:
            covered = s.action in tpl_actions and (not s.tool or any(ts.tool == s.tool for ts in tpl_steps))
            if not covered:
                extras.append(s)

        # Re-index the extras' depends_on so they chain off the template tail.
        merged = list(tpl_steps)
        for extra in extras:
            merged.append(StepSpec(
                action=extra.action,
                description=extra.description,
                tool=extra.tool,
                depends_on=[len(merged) - 1] if merged else [],
                condition=extra.condition,
            ))

        return trigger, merged

    # ---- Compile & validate -------------------------------------------------

    def validate_n8n_workflow(self, workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
        return _validate_n8n(workflow)

    # ---- Main entry point ---------------------------------------------------

    async def generate(self, description: str) -> GenerationResult:
        parsed = self.parse_process(description)

        # Confidence gate: below threshold, return targeted questions.
        if parsed.confidence < self.config["generation_threshold"]:
            return GenerationResult(
                workflow=None,
                explanation=[],
                clarifying_questions=self.generate_clarifying_questions(parsed),
                strategy=None,
                confidence=parsed.confidence,
                parsed=parsed,
            )

        # Decide strategy.
        strategy, template, _ = self._resolve_strategy(parsed)

        if strategy == GenerationStrategy.TEMPLATE_EXACT:
            trigger = parsed.trigger if parsed.trigger and parsed.trigger.kind != "manual" else _template_to_trigger(template)
            steps = _template_to_steps(template)
            name = template["name"]
            source = template["name"]
        elif strategy == GenerationStrategy.TEMPLATE_MODIFIED:
            trigger, steps = self._merge_with_template(template, parsed)
            name = f"{template['name']} (customized)"
            source = template["name"]
        else:
            trigger = parsed.trigger
            steps = parsed.steps
            name = self._derive_name(parsed)
            source = None

        workflow = _compile_to_n8n(name, trigger, steps, self.catalog)

        valid, errors = _validate_n8n(workflow)
        if not valid:
            logger.error(f"Generated workflow failed validation: {errors}")
            # Don't ship a broken workflow — fall back to questions so the
            # customer isn't handed something that won't import.
            return GenerationResult(
                workflow=None,
                explanation=[],
                clarifying_questions=[
                    "I built a workflow but it didn't pass structural checks. "
                    "Can you clarify the order of steps so I can try again?"
                ],
                strategy=strategy,
                confidence=parsed.confidence,
                source_template=source,
                parsed=parsed,
            )

        explanation = [_explain_trigger(trigger)] + _explain_steps(steps)

        return GenerationResult(
            workflow=workflow,
            explanation=explanation,
            clarifying_questions=[],
            strategy=strategy,
            confidence=parsed.confidence,
            source_template=source,
            parsed=parsed,
        )

    @staticmethod
    def _derive_name(parsed: ParsedProcess) -> str:
        """Pick a short human name for the workflow from its content."""
        tools = [s.tool.title() for s in parsed.steps if s.tool]
        if tools:
            return f"{' + '.join(dict.fromkeys(tools[:2]))} Automation"
        if parsed.steps:
            return parsed.steps[0].description[:40].strip().title()
        return "Generated Workflow"
