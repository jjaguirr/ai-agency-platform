"""Heartbeat daemon — background asyncio task for proactive intelligence.

Runs inside the FastAPI process. Iterates active customers on each tick,
collects triggers from behaviors and specialists, passes them through the
noise gate, and dispatches approved triggers via the outbound dispatcher.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional, Protocol, runtime_checkable

from .behaviors import (
    BehaviorConfig,
    FollowUpTrackerBehavior,
    IdleNudgeBehavior,
    MorningBriefingBehavior,
)
from .gate import GateDecision, NoiseConfig, NoiseGate
from .settings_loader import CustomerSettingsLoader
from .state import ProactiveStateStore
from .triggers import ProactiveTrigger

logger = logging.getLogger(__name__)


@runtime_checkable
class OutboundDispatcher(Protocol):
    async def dispatch(self, customer_id: str, trigger: ProactiveTrigger) -> None: ...


class HeartbeatDaemon:
    def __init__(
        self,
        ea_registry,
        state_store: ProactiveStateStore,
        noise_gate: NoiseGate,
        dispatcher: OutboundDispatcher,
        *,
        tick_interval: float = 300.0,
        customer_timeout: float = 30.0,
        clock: Optional[Callable[[], datetime]] = None,
        settings_loader: Optional[CustomerSettingsLoader] = None,
    ) -> None:
        self._registry = ea_registry
        self._state = state_store
        self._gate = noise_gate
        self._dispatcher = dispatcher
        self._tick_interval = tick_interval
        self._customer_timeout = customer_timeout
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._settings = settings_loader
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="heartbeat-daemon")
        logger.info("Heartbeat daemon started (interval=%.0fs)", self._tick_interval)

    async def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Heartbeat daemon stopped")

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Heartbeat tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._tick_interval,
                )
                break  # stop_event was set
            except asyncio.TimeoutError:
                pass  # normal — time for next tick

    async def _tick(self) -> None:
        customer_ids = self._registry.active_customer_ids()
        if not customer_ids:
            return

        # Load per-customer config once, up front. The loader caches with
        # a short TTL, so even a large customer set is at most one Redis
        # read per customer per tick. Loading outside the timeout-wrapped
        # check means a slow Redis response doesn't burn the customer's
        # 30-second check budget.
        noise_configs: dict[str, NoiseConfig] = {}
        behavior_configs: dict[str, BehaviorConfig] = {}
        for cid in customer_ids:
            noise_configs[cid], behavior_configs[cid] = await self._load_configs(cid)

        async def _safe_check(cid: str) -> list[ProactiveTrigger]:
            try:
                return await asyncio.wait_for(
                    self._check_customer(cid, behavior_configs[cid]),
                    timeout=self._customer_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Proactive check timed out for customer=%s", cid)
                return []
            except Exception:
                logger.exception("Proactive check failed for customer=%s", cid)
                return []

        results = await asyncio.gather(*[_safe_check(cid) for cid in customer_ids])

        for cid, triggers in zip(customer_ids, results):
            config = noise_configs[cid]
            for trigger in triggers:
                decision = await self._gate.evaluate(cid, trigger, config, now=self._clock())
                if decision.allowed:
                    try:
                        await self._dispatcher.dispatch(cid, trigger)
                        # Record cooldown after successful dispatch
                        if trigger.cooldown_key:
                            await self._state.record_cooldown(
                                cid, trigger.cooldown_key, config.cooldown_window,
                            )
                        await self._state.increment_daily_count(cid)
                        # Record briefing time so it doesn't fire twice same day
                        if trigger.trigger_type == "morning_briefing":
                            await self._state.set_last_briefing_time(
                                cid, self._clock(),
                            )
                    except Exception:
                        logger.exception(
                            "Failed to dispatch trigger %s for customer=%s",
                            trigger.title, cid,
                        )
                else:
                    logger.debug(
                        "Trigger suppressed for customer=%s: %s (%s)",
                        cid, trigger.title, decision.reason,
                    )

    async def _load_configs(
        self, customer_id: str,
    ) -> tuple[NoiseConfig, BehaviorConfig]:
        if self._settings is None:
            return NoiseConfig(), BehaviorConfig()
        try:
            return (
                await self._settings.noise_config_for(customer_id),
                await self._settings.behavior_config_for(customer_id),
            )
        except Exception:
            logger.exception(
                "Failed to load settings for customer=%s; using defaults",
                customer_id,
            )
            return NoiseConfig(), BehaviorConfig()

    async def _check_customer(
        self, customer_id: str, cfg: Optional[BehaviorConfig] = None,
    ) -> list[ProactiveTrigger]:
        cfg = cfg or BehaviorConfig()
        triggers: list[ProactiveTrigger] = []

        # Built-in behaviors. Some take (customer_id), some take
        # (customer_id, config) — try the config signature first so
        # behaviors that care about per-customer settings see them.
        for behavior in self._get_behaviors():
            try:
                result = await behavior.check(customer_id, cfg)
            except TypeError:
                try:
                    result = await behavior.check(customer_id)
                except Exception:
                    logger.exception(
                        "Behavior %s failed for customer=%s",
                        type(behavior).__name__, customer_id,
                    )
                    continue
            except Exception:
                logger.exception(
                    "Behavior %s failed for customer=%s",
                    type(behavior).__name__, customer_id,
                )
                continue
            if result is None:
                continue
            if isinstance(result, list):
                triggers.extend(result)
            else:
                triggers.append(result)

        # Specialist proactive checks
        specialist_triggers = await self._get_specialist_triggers(customer_id)
        triggers.extend(specialist_triggers)

        return triggers

    def _get_behaviors(self) -> list:
        clock = self._clock
        return [
            MorningBriefingBehavior(self._state, clock=clock),
            FollowUpTrackerBehavior(self._state, clock=clock),
            IdleNudgeBehavior(self._state, clock=clock),
        ]

    async def _get_specialist_triggers(
        self, customer_id: str,
    ) -> list[ProactiveTrigger]:
        triggers: list[ProactiveTrigger] = []
        # Access delegation registry if EA has one
        try:
            ea = self._registry._instances.get(customer_id)
            if ea is None:
                return triggers
            registry = getattr(ea, "delegation_registry", None)
            if registry is None:
                return triggers
            specialists = getattr(registry, "_specialists", None)
            if not isinstance(specialists, dict):
                return triggers
            from src.agents.executive_assistant import BusinessContext
            ctx = BusinessContext()  # Minimal context for proactive checks

            for specialist in specialists.values():
                try:
                    result = await specialist.proactive_check(customer_id, ctx)
                    if result is not None:
                        triggers.append(result)
                except Exception:
                    logger.exception(
                        "Specialist %s proactive_check failed for customer=%s",
                        specialist.domain, customer_id,
                    )
        except Exception:
            logger.exception("Failed to get specialist triggers for customer=%s", customer_id)

        return triggers


class DefaultOutboundDispatcher:
    """Dispatch proactive triggers via WhatsApp (if available) and store for API pull."""

    def __init__(self, whatsapp_manager, state_store: ProactiveStateStore) -> None:
        self._wa = whatsapp_manager
        self._state = state_store

    async def dispatch(self, customer_id: str, trigger: ProactiveTrigger) -> None:
        notification = {
            "id": f"notif_{id(trigger)}",
            "domain": trigger.domain,
            "trigger_type": trigger.trigger_type,
            "priority": trigger.priority.name,
            "title": trigger.title,
            "message": trigger.suggested_message,
            "created_at": trigger.created_at.isoformat(),
        }

        # Try WhatsApp delivery
        try:
            channel = self._wa.get_channel(customer_id)
            if channel is not None:
                await channel.send_message(customer_id, trigger.suggested_message)
        except Exception:
            logger.warning(
                "WhatsApp dispatch failed for customer=%s trigger=%s",
                customer_id, trigger.title,
            )

        # Always store for API pull
        await self._state.add_pending_notification(customer_id, notification)
