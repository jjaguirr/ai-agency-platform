"""
Shared interaction context — assembled once per interaction, passed read-only
to the specialist that handles the delegation.

The ContextAssembler aggregates lightweight snapshots from each domain
(calendar, finance, workflows, notifications) with per-source timeouts
so a slow or broken domain never blocks the customer's response.

Lazy loading: if the EA knows the message is about scheduling, it tells
the assembler ``relevant_domains={"scheduling"}`` and the finance/workflow
sources are skipped entirely. If the message is ambiguous, all domains
produce summaries.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from src.proactive.state import ProactiveStateStore

logger = logging.getLogger(__name__)


# --- Read-only snapshot types -----------------------------------------------

@dataclass(frozen=True)
class CalendarSnapshot:
    events_next_24h: List[Dict[str, Any]]
    has_conflicts: bool = False


@dataclass(frozen=True)
class FinanceSnapshot:
    transaction_baseline: Optional[float] = None
    recent_expense_total: Optional[float] = None
    top_category: Optional[str] = None
    budget_status: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowSnapshot:
    active_count: int = 0
    workflow_names: List[str] = field(default_factory=list)
    recent_failures: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CustomerPreferences:
    tone: str = "professional"
    working_hours: Optional[Dict[str, str]] = None
    business_type: str = ""
    language: str = "en"


@dataclass
class DelegationRecord:
    domain: str = ""
    status: str = ""
    timestamp: str = ""


@dataclass
class InteractionContext:
    """Read-only context assembled once per interaction."""
    recent_conversation_summary: Optional[str] = None
    calendar_snapshot: Optional[CalendarSnapshot] = None
    finance_snapshot: Optional[FinanceSnapshot] = None
    workflow_snapshot: Optional[WorkflowSnapshot] = None
    pending_notifications: List[Dict[str, Any]] = field(default_factory=list)
    customer_preferences: CustomerPreferences = field(default_factory=CustomerPreferences)
    delegation_history: List[DelegationRecord] = field(default_factory=list)


# --- Domain relevance -------------------------------------------------------

_DOMAIN_MAP: Dict[str, Set[str]] = {
    "scheduling": {"scheduling"},
    "finance": {"finance"},
    "workflows": {"workflows"},
    "social_media": {"social_media"},
}


# --- Assembler --------------------------------------------------------------

class ContextAssembler:
    """Assembles InteractionContext from domain sources with timeouts."""

    def __init__(
        self,
        *,
        proactive_store: "ProactiveStateStore",
        settings_redis,
        source_timeout: float = 2.0,
    ):
        self._proactive = proactive_store
        self._settings_redis = settings_redis
        self._source_timeout = source_timeout

    async def assemble(
        self,
        customer_id: str,
        *,
        relevant_domains: Set[str],
        calendar_client=None,
        workflow_store=None,
        conversation_summary: Optional[str] = None,
        delegation_history: Optional[List[DelegationRecord]] = None,
    ) -> InteractionContext:
        """Build context. Each domain source respects timeout independently."""
        fetch_all = len(relevant_domains) == 0

        # Launch all relevant fetches concurrently.
        cal_task = None
        fin_task = None
        wf_task = None

        if (fetch_all or "scheduling" in relevant_domains) and calendar_client is not None:
            cal_task = asyncio.ensure_future(
                self._fetch_calendar(customer_id, calendar_client)
            )

        if fetch_all or "finance" in relevant_domains:
            fin_task = asyncio.ensure_future(
                self._fetch_finance(customer_id)
            )

        if (fetch_all or "workflows" in relevant_domains) and workflow_store is not None:
            wf_task = asyncio.ensure_future(
                self._fetch_workflows(customer_id, workflow_store)
            )

        notif_task = asyncio.ensure_future(self._fetch_notifications(customer_id))
        prefs_task = asyncio.ensure_future(self._fetch_preferences(customer_id))

        # Await with timeouts — each source independent.
        calendar_snapshot = await self._guarded(cal_task, "calendar")
        finance_snapshot = await self._guarded(fin_task, "finance")
        workflow_snapshot = await self._guarded(wf_task, "workflows")
        notifications = await self._guarded(notif_task, "notifications") or []
        preferences = await self._guarded(prefs_task, "preferences") or CustomerPreferences()

        return InteractionContext(
            recent_conversation_summary=conversation_summary,
            calendar_snapshot=calendar_snapshot,
            finance_snapshot=finance_snapshot,
            workflow_snapshot=workflow_snapshot,
            pending_notifications=notifications,
            customer_preferences=preferences,
            delegation_history=delegation_history or [],
        )

    async def _guarded(self, task, label: str):
        """Await a task with timeout + error guard. Returns None on failure."""
        if task is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=self._source_timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Context source '{label}' timed out after {self._source_timeout}s")
            task.cancel()
            return None
        except Exception as e:
            logger.warning(f"Context source '{label}' failed: {e}")
            return None

    # --- Per-domain fetch methods -------------------------------------------

    async def _fetch_calendar(self, customer_id: str, calendar_client) -> CalendarSnapshot:
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=24)
        events = await calendar_client.list_events(now, end)

        event_dicts = []
        for e in events:
            event_dicts.append({
                "id": getattr(e, "id", ""),
                "title": getattr(e, "title", ""),
                "start": e.start.isoformat() if hasattr(e.start, "isoformat") else str(e.start),
                "end": e.end.isoformat() if hasattr(e.end, "isoformat") else str(e.end),
            })

        # Simple conflict check: any overlapping events in the next 24h
        has_conflicts = False
        sorted_events = sorted(events, key=lambda ev: ev.start)
        for i in range(len(sorted_events) - 1):
            if sorted_events[i].end > sorted_events[i + 1].start:
                has_conflicts = True
                break

        return CalendarSnapshot(
            events_next_24h=event_dicts,
            has_conflicts=has_conflicts,
        )

    async def _fetch_finance(self, customer_id: str) -> FinanceSnapshot:
        baseline = await self._proactive.get_transaction_baseline(customer_id)
        return FinanceSnapshot(
            transaction_baseline=baseline,
        )

    async def _fetch_workflows(self, customer_id: str, workflow_store) -> WorkflowSnapshot:
        workflows = await workflow_store.list_workflows(customer_id)
        active = [w for w in workflows if w.get("status") == "active"]
        return WorkflowSnapshot(
            active_count=len(active),
            workflow_names=[w["name"] for w in active],
            recent_failures=[w for w in workflows if w.get("status") == "error"],
        )

    async def _fetch_notifications(self, customer_id: str) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        return await self._proactive.list_pending_notifications(customer_id, now=now)

    async def _fetch_preferences(self, customer_id: str) -> CustomerPreferences:
        prefs = CustomerPreferences()
        try:
            raw = await self._settings_redis.get(f"settings:{customer_id}")
            if not raw:
                return prefs
            data = json.loads(raw if isinstance(raw, str) else raw.decode())
            personality = data.get("personality") or {}
            prefs.tone = personality.get("tone", prefs.tone)
            prefs.language = personality.get("language", prefs.language)
            wh = data.get("working_hours")
            if wh:
                prefs.working_hours = wh
        except Exception as e:
            logger.warning(f"Preferences fetch failed, using defaults: {e}")
        return prefs
