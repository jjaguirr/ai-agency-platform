"""
ProactiveEngine — the composition root that turns a heartbeat tick into
customer-visible messages.

Two entry points:

  check_customer(cust, context, specialists, prefs)
      Called by the heartbeat daemon once per customer per tick. Gathers
      candidate triggers (specialist checks + built-in behaviors + due
      followups), runs each through the noise gate, delivers the
      survivors. Every stage swallows exceptions — one broken specialist
      must not take down the whole tick.

  capture_interaction(cust, text)
      Called from the inbound message path. Records last_interaction and
      extracts any commitment language into tracked followups. Cheap;
      intended to sit directly inside handle_customer_interaction.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable, List, Optional, TYPE_CHECKING

from .behaviors import check_idle_nudge, check_morning_briefing
from .followups import commitment_to_trigger, extract_commitments
from .gate import NoiseGate, ProactivePrefs
from .outbound import OutboundRouter
from .state import ProactiveStateStore
from .triggers import ProactiveTrigger

if TYPE_CHECKING:
    from src.agents.base.specialist import SpecialistAgent
    from src.agents.executive_assistant import BusinessContext

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class ProactiveEngine:
    def __init__(
        self,
        *,
        state_store: ProactiveStateStore,
        gate: NoiseGate,
        router: OutboundRouter,
        clock: Clock,
    ):
        self._store = state_store
        self._gate = gate
        self._router = router
        self._clock = clock

    # --- Heartbeat side ----------------------------------------------------

    async def check_customer(
        self,
        customer_id: str,
        context: "BusinessContext",
        *,
        specialists: Iterable["SpecialistAgent"],
        prefs: ProactivePrefs,
    ) -> None:
        now = self._clock()
        candidates: List[ProactiveTrigger] = []

        # --- Specialist hooks ---
        # Each specialist may expose an optional async proactive_check.
        # We tolerate absence AND failure — a misbehaving finance
        # specialist shouldn't block the scheduling one, and neither
        # should block the built-in briefing.
        for spec in specialists:
            check = getattr(spec, "proactive_check", None)
            if check is None:
                continue
            try:
                t = await check(customer_id, context)
            except Exception as e:
                logger.warning("proactive_check crashed for domain=%s cust=%s: %s",
                               getattr(spec, "domain", "?"), customer_id, e)
                continue
            if t is not None:
                candidates.append(t)

        # --- Built-in behaviors ---
        for fn in (check_morning_briefing, check_idle_nudge):
            try:
                t = await fn(customer_id, context, self._store, clock=self._clock)
            except Exception as e:
                logger.warning("builtin behavior %s crashed for cust=%s: %s",
                               fn.__name__, customer_id, e)
                continue
            if t is not None:
                candidates.append(t)

        # --- Due followups ---
        # These are commitments the customer explicitly asked us to track,
        # so they always get a shot at the gate.
        for c in await self._store.list_followups(customer_id):
            t = commitment_to_trigger(c, now=now)
            if t is not None:
                candidates.append(t)

        # --- Gate + deliver ---
        for trigger in candidates:
            try:
                decision = await self._gate.evaluate(customer_id, trigger, prefs)
            except Exception as e:
                logger.warning("gate evaluate failed for cust=%s: %s",
                               customer_id, e)
                continue
            if not decision.allow:
                logger.debug("suppressed proactive trigger cust=%s key=%s reason=%s",
                             customer_id, trigger.cooldown_key, decision.reason)
                continue
            try:
                await self._router.deliver(customer_id, trigger)
                await self._gate.record_sent(customer_id, trigger, prefs)
            except Exception as e:
                # Router is designed not to raise, but belt + braces —
                # don't let a delivery hiccup stop us recording the
                # cooldown for the next trigger in the batch.
                logger.warning("delivery failed for cust=%s: %s",
                               customer_id, e)

    # --- Inbound side ------------------------------------------------------

    async def capture_interaction(self, customer_id: str, text: str) -> None:
        """Record the interaction and harvest any commitment language.

        Called on every inbound message. Must stay cheap — no LLM, no
        network beyond Redis. The followup extractor is regex-only
        precisely so this call is effectively free.
        """
        now = self._clock()
        await self._store.set_last_interaction(customer_id, now)
        for c in extract_commitments(text, ref=now):
            await self._store.add_followup(customer_id, c)
