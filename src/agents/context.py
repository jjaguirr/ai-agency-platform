"""
Shared interaction context for specialists.

Assembled once per interaction by the EA and passed to whichever
specialist handles the delegation. Gives the finance specialist a
glimpse of tomorrow's calendar, lets the scheduling specialist know a
large expense just went through — without breaking the isolation
boundary (specialists still never touch raw clients).

Design:
- Frozen dataclasses. Specialists read, never mutate.
- Lazy. The builder only calls the domain sources it's asked to —
  a scheduling delegation doesn't pull finance detail.
- Timeout-guarded. One slow source doesn't block the customer's reply.
- Sources are pluggable async callables: ``customer_id -> DomainSnapshot``.
  The EA wires concrete sources (calendar client, proactive state, etc.)
  at construction time; tests inject doubles.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainSnapshot:
    """One domain's lightweight state summary.

    ``summary`` is a short prose string suitable for direct inclusion in
    a response ("2 events today, first at 9:00"). ``data`` carries the
    structured payload for specialists that want to reason over it.
    """
    domain: str
    summary: str
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InteractionContext:
    """Cross-domain snapshot assembled at the start of an interaction.

    Everything is immutable. ``recent_turns`` and ``delegation_history``
    are tuples, not lists, so a specialist can't sneak an append in.
    ``domains`` maps domain name → snapshot; absent key means that
    source wasn't loaded (out of scope for this delegation) or timed
    out — callers treat both cases as "no context available."
    """
    customer_id: str
    recent_turns: Tuple[Dict[str, str], ...]
    personality: Mapping[str, str]
    domains: Mapping[str, DomainSnapshot]
    delegation_history: Tuple[Dict[str, Any], ...]

    # --- Convenience accessors ---------------------------------------------

    @property
    def tone(self) -> str:
        return self.personality.get("tone") or "professional"

    def get_domain(self, name: str) -> Optional[DomainSnapshot]:
        return self.domains.get(name)

    def recent_domains(self) -> List[str]:
        """Ordered list of which specialists handled recent requests."""
        return [d["domain"] for d in self.delegation_history if d.get("domain")]


# A source is any async callable: customer_id -> DomainSnapshot.
DomainSource = Callable[[str], Awaitable[DomainSnapshot]]


class ContextBuilder:
    """Assembles an InteractionContext from registered domain sources.

    Sources run concurrently under a per-source timeout. A slow or
    crashed source is logged and skipped — the customer's response
    must never wait on a flaky dependency.
    """

    def __init__(
        self,
        sources: Dict[str, DomainSource],
        *,
        per_source_timeout: float = 2.0,
    ) -> None:
        self._sources = dict(sources)
        self._timeout = per_source_timeout

    async def build(
        self,
        *,
        customer_id: str,
        primary_domain: Optional[str],
        recent_turns: Iterable[Dict[str, str]],
        personality: Mapping[str, str],
        delegation_history: Iterable[Dict[str, Any]],
        include: Optional[Iterable[str]] = None,
    ) -> InteractionContext:
        to_load = self._select_domains(primary_domain, include)
        snapshots = await self._load_concurrent(customer_id, to_load)

        return InteractionContext(
            customer_id=customer_id,
            recent_turns=tuple(recent_turns),
            personality=dict(personality),
            domains=snapshots,
            delegation_history=tuple(delegation_history),
        )

    def _select_domains(
        self, primary: Optional[str], include: Optional[Iterable[str]],
    ) -> List[str]:
        # Ambiguous message → give the specialist a lightweight view of
        # everything. Otherwise, primary + any explicit extras.
        if primary is None:
            return list(self._sources)
        wanted = {primary, *(include or ())}
        return [d for d in wanted if d in self._sources]

    async def _load_concurrent(
        self, customer_id: str, domains: List[str],
    ) -> Dict[str, DomainSnapshot]:
        if not domains:
            return {}

        async def guarded(name: str) -> tuple[str, Optional[DomainSnapshot]]:
            try:
                snap = await asyncio.wait_for(
                    self._sources[name](customer_id),
                    timeout=self._timeout,
                )
                return name, snap
            except asyncio.TimeoutError:
                logger.warning(
                    "Context source %r timed out after %.1fs for customer=%s",
                    name, self._timeout, customer_id,
                )
            except Exception:
                logger.exception(
                    "Context source %r crashed for customer=%s; skipping",
                    name, customer_id,
                )
            return name, None

        results = await asyncio.gather(*(guarded(d) for d in domains))
        return {name: snap for name, snap in results if snap is not None}
