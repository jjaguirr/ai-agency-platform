"""
Built-in proactive behaviors — things the EA initiates regardless of
which specialists are registered.

These live at the EA level (not in a specialist) because they're
cross-domain: the morning briefing pulls from followups + calendar +
whatever else accumulates overnight; the idle nudge depends on
last-interaction, which no specialist owns.

Idempotency is enforced HERE via last_briefing / last_nudge timestamps,
not by leaning on the noise gate's cooldown. The gate is a safety net;
these functions should already be correct without it. That way the gate
never has to know what "once per day in customer's timezone" means.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

from .state import ProactiveStateStore
from .triggers import Priority, ProactiveTrigger

if TYPE_CHECKING:
    from src.agents.executive_assistant import BusinessContext


Clock = Callable[[], datetime]


def _local(dt: datetime, tz_name: str) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


# --- Morning briefing -------------------------------------------------------

async def check_morning_briefing(
    customer_id: str,
    context: "BusinessContext",
    state_store: ProactiveStateStore,
    *,
    briefing_hour: int = 8,
    clock: Clock,
) -> Optional[ProactiveTrigger]:
    """Fire the daily briefing if it's past `briefing_hour` in the customer's
    timezone and we haven't already sent one today.

    Returns None if:
      • It's too early (local hour < briefing_hour)
      • We already sent today's briefing
      • There's nothing to say (no followups, no calendar items, …)

    The last check matters — "good morning, you have nothing today" is
    technically true and utterly useless. Silence is better.
    """
    now = clock()
    tz = getattr(context, "timezone", None) or "UTC"
    local_now = _local(now, tz)

    if local_now.hour < briefing_hour:
        return None

    last = await state_store.get_last_briefing(customer_id)
    if last is not None and _local(last, tz).date() == local_now.date():
        return None  # already briefed today

    # --- Gather content ---
    # Today this is followups only; hooking in the scheduling specialist's
    # calendar view is a one-line add once SchedulingSpecialist exposes
    # a day-summary method. The briefing structure already accommodates it.
    followups = await state_store.list_followups(customer_id)
    due_today = [
        f for f in followups
        if _local(f.due, tz).date() <= local_now.date()
    ]

    n_items = len(due_today)
    if n_items == 0:
        return None

    # --- Compose ---
    if n_items == 1:
        body = f"Good morning — one thing on your plate today: {due_today[0].text}."
    else:
        lines = "\n".join(f"  • {f.text}" for f in due_today[:5])
        more = f"\n  …and {n_items - 5} more" if n_items > 5 else ""
        body = f"Good morning — {n_items} items today:\n{lines}{more}"

    return ProactiveTrigger(
        domain="ea",
        trigger_type="briefing",
        priority=Priority.MEDIUM,
        title="Morning briefing",
        payload={"n_items": n_items},
        suggested_message=body,
        cooldown_key="morning_briefing",
        created_at=now,
    )


# --- Idle nudge -------------------------------------------------------------

async def check_idle_nudge(
    customer_id: str,
    context: "BusinessContext",
    state_store: ProactiveStateStore,
    *,
    idle_days: int = 7,
    clock: Clock,
) -> Optional[ProactiveTrigger]:
    """Gentle re-engagement if the customer has gone quiet AND there's a
    reason to reach out.

    Guards, in order (cheapest first):
      • Never interacted → don't nudge (they haven't onboarded)
      • Interacted recently (within idle_days) → don't nudge
      • Already nudged since their last interaction → don't nudge again
      • Nothing pending → don't nudge (no hook to pull them back with)

    Priority LOW because this is a re-engagement convenience, not an
    actionable alert. Customers on the default MEDIUM floor won't see it
    unless they've opted into low-priority chatter — which is the right
    default. A customer who's gone quiet hasn't asked to be chased.
    """
    now = clock()
    last_interaction = await state_store.get_last_interaction(customer_id)

    if last_interaction is None:
        return None
    if now - last_interaction < timedelta(days=idle_days):
        return None

    # One nudge per idle period — if we already nudged after they went
    # quiet and they didn't respond, nagging harder won't help.
    last_nudge = await state_store.get_last_nudge(customer_id)
    if last_nudge is not None and last_nudge > last_interaction:
        return None

    pending = await state_store.list_followups(customer_id)
    if not pending:
        return None

    sample = pending[0].text
    n = len(pending)
    if n == 1:
        msg = f"Haven't heard from you in a bit — still want me to follow up on: {sample}?"
    else:
        msg = (f"Haven't heard from you in a bit — you've got {n} open items "
               f"(including: {sample}). Want to pick anything up?")

    return ProactiveTrigger(
        domain="ea",
        trigger_type="suggestion",
        priority=Priority.LOW,
        title="Check-in",
        payload={"idle_days": (now - last_interaction).days, "pending": n},
        suggested_message=msg,
        cooldown_key="idle_nudge",
        created_at=now,
    )
