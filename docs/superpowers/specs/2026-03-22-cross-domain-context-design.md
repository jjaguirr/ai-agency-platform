# Cross-Domain Context & Specialist Response Quality — Design

**Date:** 2026-03-22
**Scope:** shared context layer, personality-aware synthesis, per-specialist pattern awareness.

## Problem

The four specialists work, but in isolation. Finance doesn't know you have a board meeting tomorrow; scheduling doesn't know you just recorded a $5k expense; workflows can't suggest automations for things you keep asking about. Every specialist answers in the same flat tone regardless of customer preference.

## Shared context layer — `src/agents/context.py`

### `InteractionContext`

Frozen dataclass assembled once per interaction by the EA, passed to whichever specialist handles the delegation. Gives each specialist a read-only glimpse of other domains without breaking the isolation boundary (specialists still never touch raw clients).

```python
@dataclass(frozen=True)
class InteractionContext:
    customer_id: str
    recent_turns: Tuple[Dict[str, str], ...]       # last N conversation turns
    personality: Mapping[str, str]                 # {tone, language, name}
    domains: Mapping[str, DomainSnapshot]          # per-domain state summary
    delegation_history: Tuple[Dict[str, Any], ...] # which specialists fired recently
```

Tuples, not lists — specialists can't sneak an append in. Carried to specialists via a new optional `SpecialistTask.interaction_context` field; older construction paths (offline scripts, direct unit tests) keep working when it's absent.

### `ContextBuilder`

Assembles the context from pluggable async sources (`customer_id -> DomainSnapshot`).

- **Lazy.** `primary_domain="finance"` loads only the finance source. `primary_domain=None` (ambiguous) loads all sources lightweight. Explicit `include=[...]` extends the primary.
- **Concurrent.** Sources run under `asyncio.gather` with per-source `asyncio.wait_for` (default 2s). Four 50ms sources finish in ~50ms, not 200ms.
- **Fail-soft.** A slow or crashed source is logged and its key is absent from `ctx.domains`. The customer's response never waits on a flaky dependency.
- **Tenant-isolated.** Every source receives `customer_id`; the context carries it for downstream verification.

Concrete domain sources (calendar client, proactive state, workflow store) are wired at `create_default_app` time — deferred, see Open items.

## Personality — `src/agents/tone.py`

Tone is applied in the EA's `_synthesize_specialist_result`, not in specialist execution. Specialists do the same work regardless of tone; the EA owns phrasing.

Four tones (`schemas.Tone`): `professional`, `friendly`, `concise`, `detailed`.

Two paths:

| Path | Mechanism | Determinism |
|---|---|---|
| LLM | `guidance(tone)` injected into synthesis prompt | non-deterministic |
| LLM-free | `render(result, tone)` rewrites `summary_for_ea` | deterministic — what tests assert against |

The LLM-free renderers differ meaningfully: `concise` strips filler prefixes, `friendly` adds an opener, `detailed` surfaces payload fields not already in the base summary, `professional` normalises punctuation. `concise` is always shortest, `detailed` always longest.

Unknown tone falls back to `professional`. If `_personality` is unset (callers bypassing `__init__`), synthesis degrades to defaults rather than crashing — same philosophy as `_load_personality`.

## Pattern awareness — `ProactiveStateStore` extensions

All per-customer, Redis-backed under `proactive:{customer_id}:{subkey}`. All optional — a missing store or Redis error leaves base behaviour intact.

### Finance

| Method | Key | Behaviour |
|---|---|---|
| `record_category_transaction(cid, cat, amt)` | `tx_cat:{cat}` | hash `{count, sum}` |
| `get_category_baseline(cid, cat)` | same | mean, `None` until 3 samples |
| `set_budget` / `get_budget` | `budget:{cat}` | float limit |
| `record_period_spend` / `get_period_spend` | `period:{cat}:{YYYY-MM}` | running total |

`FinanceSpecialist` reads category baseline before recording a new transaction; if the new amount > 2× baseline it appends "That's higher than your usual {category} spend" to `summary_for_ea`. Summary queries are enriched with budget progress and month-over-month deltas.

### Scheduling

| Method | Key | Behaviour |
|---|---|---|
| `record_meeting_booked(cid, duration_min, hour)` | `sched_prefs` | bounded list (last 30), JSON entries `{d, h}` |
| `get_scheduling_prefs(cid)` | same | `{durations, preferred_duration (modal), preferred_hour (modal), sample_count}` |

Duration fallback chain: parsed → learned modal (≥3 samples) → hardcoded 60m (create) / 30m (slot-find). Conflicts are checked at create time and named in `summary_for_ea`, not only staged to proactive.

### Workflows

| Method | Key | Behaviour |
|---|---|---|
| `record_suggestion(cid, topic, window_s)` | `suggest:{topic}` | TTL cooldown (default 6h) |
| `suggestion_cooling_down(cid, topic)` | same | exists check |

`WorkflowSpecialist._maybe_suggest` scans `interaction_context.delegation_history` for repeated topic keywords. Threshold 3 hits → check no matching workflow exists → check cooldown → append "You ask about {topic}s a lot — want me to set up an automated {label}?" and record cooldown.

## Open items

- `ContextBuilder` is not yet wired into `_delegate_to_specialist`. Concrete domain sources live in the app factory, not the EA constructor; wiring is a follow-up.

## Validation

- `uv run pytest tests/unit/test_interaction_context.py tests/unit/test_personality_synthesis.py tests/unit/test_finance_patterns.py tests/unit/test_scheduling_preferences.py tests/unit/test_workflow_suggestions.py -q` — 47 tests
- All four tones produce distinct output from the same `SpecialistResult`
- `concise` shortest, `detailed` longest, `detailed` surfaces payload-only fields
- Category baselines and budgets tenant-isolated
- Learned duration overrides hardcoded default after 3 samples
- Conflict named in response text, not just proactive
- Suggestion fires at threshold 3, respects cooldown, suppressed when workflow exists
- `interaction_context=None` degrades gracefully
- Tests committed before implementation (TDD)
