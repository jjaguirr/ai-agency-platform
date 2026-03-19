"""
Noise control — the thing that stops the proactive system from spamming.

Four filters, applied in order:
  1. Cooldown       — same cooldown_key within window → SUPPRESS
  2. Priority floor — below customer's min_priority → SUPPRESS
  3. Quiet hours    — local time in [quiet_start, quiet_end) → SUPPRESS
  4. Daily cap      — already sent N today → SUPPRESS

URGENT triggers bypass filters 3 and 4 (they're volume/comfort guards,
not correctness guards). URGENT does NOT bypass cooldown — if the same
urgent thing has already been sent, sending it again doesn't make it
more urgent, it makes it noise. URGENT naturally passes the priority
floor by virtue of being maximal.

The gate exposes two operations, kept separate so the caller can decide
whether to count a suppressed message against quotas (it shouldn't):
  evaluate(cust, trigger, prefs)   → GateDecision(allow, reason)  [no side effects]
  record_sent(cust, trigger, prefs)                               [mutates state]

The split also means a speculative "would this pass?" check is free.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, NamedTuple
from zoneinfo import ZoneInfo

from .state import ProactiveStateStore
from .triggers import Priority, ProactiveTrigger


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ProactivePrefs:
    """Per-customer dials on the noise gate.

    Timezone is duplicated here (rather than pulled from BusinessContext)
    so the gate is self-contained — callers don't need to thread the whole
    context object through when only the TZ matters for quiet-hours math.
    """
    timezone: str
    min_priority: Priority
    quiet_start_hour: int  # inclusive, local hour [0,24)
    quiet_end_hour: int    # exclusive, local hour [0,24)
    daily_cap: int
    cooldown_hours: int


class GateDecision(NamedTuple):
    allow: bool
    reason: str  # human-readable — logged on suppress, ignored on allow


class NoiseGate:
    def __init__(self, state_store: ProactiveStateStore, *, clock: Clock):
        self._store = state_store
        self._clock = clock

    # --- Evaluation --------------------------------------------------------

    async def evaluate(
        self,
        customer_id: str,
        trigger: ProactiveTrigger,
        prefs: ProactivePrefs,
    ) -> GateDecision:
        now = self._clock()
        urgent = trigger.priority >= Priority.URGENT

        # 1. Cooldown — applies to everything. If the same semantic event
        #    fired recently, the customer already knows about it. URGENT is
        #    no exception: resending the same urgent alert every five
        #    minutes isn't diligence, it's harassment.
        if trigger.cooldown_key:
            last = await self._store.get_cooldown(customer_id, trigger.cooldown_key)
            if last and (now - last) < timedelta(hours=prefs.cooldown_hours):
                return GateDecision(False, reason="cooldown")

        # 2. Priority floor — customer opted out of low-noise chatter.
        #    URGENT passes by construction (it's the max).
        if trigger.priority < prefs.min_priority:
            return GateDecision(False, reason="priority below threshold")

        # 3. Quiet hours — comfort filter, URGENT punches through.
        if not urgent and self._in_quiet_hours(now, prefs):
            return GateDecision(False, reason="quiet hours")

        # 4. Daily cap — volume filter, URGENT doesn't consume or respect.
        if not urgent:
            date_str = self._local_date_str(now, prefs)
            sent = await self._store.get_daily_count(customer_id, date_str)
            if sent >= prefs.daily_cap:
                return GateDecision(False, reason="daily cap reached")

        return GateDecision(True, reason="ok")

    # --- Recording ---------------------------------------------------------

    async def record_sent(
        self,
        customer_id: str,
        trigger: ProactiveTrigger,
        prefs: ProactivePrefs,
    ) -> None:
        """Apply the side effects of a successful send.

        Called AFTER delivery succeeds — we don't burn a daily slot on a
        message that never left the process.
        """
        now = self._clock()
        if trigger.cooldown_key:
            await self._store.set_cooldown(customer_id, trigger.cooldown_key, now)
        # URGENT doesn't count against the cap — it's reserved for things
        # like double-bookings where the cost of silence dwarfs the cost
        # of an extra ping. Counting it would mean a morning briefing can
        # crowd out a meeting-collision alert.
        if trigger.priority < Priority.URGENT:
            date_str = self._local_date_str(now, prefs)
            await self._store.incr_daily_count(customer_id, date_str)

    # --- Helpers -----------------------------------------------------------

    @staticmethod
    def _to_local(utc: datetime, tz_name: str) -> datetime:
        # Callers always supply aware datetimes via the clock; if somehow
        # naive, treat as UTC so downstream math is still deterministic.
        if utc.tzinfo is None:
            utc = utc.replace(tzinfo=timezone.utc)
        return utc.astimezone(ZoneInfo(tz_name))

    def _local_date_str(self, utc: datetime, prefs: ProactivePrefs) -> str:
        # Daily cap resets at local midnight, not UTC midnight — a
        # customer in Auckland shouldn't find their cap rolling over at
        # noon. Hence the date string is derived from local time.
        return self._to_local(utc, prefs.timezone).strftime("%Y-%m-%d")

    def _in_quiet_hours(self, utc: datetime, prefs: ProactivePrefs) -> bool:
        local = self._to_local(utc, prefs.timezone)
        h = local.hour
        start, end = prefs.quiet_start_hour, prefs.quiet_end_hour
        if start == end:
            return False  # degenerate range means "never quiet"
        if start < end:
            # Normal window, e.g. 12–14 (lunch).
            return start <= h < end
        # Wraps midnight — the common case (e.g. 22–07). Quiet if we're
        # past start OR before end.
        return h >= start or h < end
