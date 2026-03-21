"""
Postgres access for the conversation intelligence layer.

Separate from ConversationRepository on purpose: that one is on the hot
path (every message POST writes to it); this one is background-sweep and
dashboard-read. Different failure modes, different caller sets. Both sit
on the same pool.

Every customer-scoped query carries the customer_id predicate at the SQL
level — same tenant-isolation discipline as ConversationRepository.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DelegationRecord:
    """One terminal delegation, as the EA hands it to the route for persistence."""
    conversation_id: str
    customer_id: str
    domain: str
    status: str                          # 'completed' | 'failed' | 'cancelled'
    turns: int
    confirmation_requested: bool
    confirmation_outcome: Optional[str]  # 'confirmed' | 'declined' | None
    started_at: datetime
    ended_at: datetime


class IntelligenceRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ─── sweep ───────────────────────────────────────────────────────────

    async def find_idle_unsummarized(
        self, *, idle_minutes: int, limit: int,
    ) -> list[tuple[str, str]]:
        """Conversations that stopped moving and haven't been summarized.

        Returns (conversation_id, customer_id) pairs. The daemon fetches
        messages separately via ConversationRepository (it already owns
        that query) — keeping this method to a single-table scan.

        The partial index on (updated_at) WHERE summary IS NULL means
        already-processed conversations don't cost anything here.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - idle_minutes * 60
        cutoff_ts = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, customer_id FROM conversations "
                "WHERE summary IS NULL AND updated_at < $1 "
                "ORDER BY updated_at LIMIT $2",
                cutoff_ts, limit,
            )
        return [(r["id"], r["customer_id"]) for r in rows]

    async def set_intelligence(
        self,
        *,
        customer_id: str,
        conversation_id: str,
        summary: Optional[str],
        topics: list[str],
        quality_flags: list[str],
    ) -> bool:
        """Write derived metadata. Tenant-guarded; returns False if the
        conversation doesn't exist or belongs to someone else."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE conversations "
                "SET summary = $1, topics = $2, quality_flags = $3 "
                "WHERE id = $4 AND customer_id = $5",
                summary, topics, quality_flags, conversation_id, customer_id,
            )
        return result == "UPDATE 1"

    # ─── delegations ─────────────────────────────────────────────────────

    async def record_delegation(self, rec: DelegationRecord) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO delegations "
                "(conversation_id, customer_id, domain, status, turns, "
                " confirmation_requested, confirmation_outcome, "
                " started_at, ended_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                rec.conversation_id, rec.customer_id, rec.domain,
                rec.status, rec.turns, rec.confirmation_requested,
                rec.confirmation_outcome, rec.started_at, rec.ended_at,
            )

    async def get_delegation_statuses(
        self, *, customer_id: str, conversation_id: str,
    ) -> list[tuple[str, str]]:
        """(domain, status) for each delegation in this conversation.

        Feeds quality.detect_unresolved and tagging.tags_from_delegations
        during the sweep — both only need domain and terminal status.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT domain, status FROM delegations "
                "WHERE customer_id = $1 AND conversation_id = $2 "
                "ORDER BY ended_at",
                customer_id, conversation_id,
            )
        return [(r["domain"], r["status"]) for r in rows]

    # ─── analytics ───────────────────────────────────────────────────────

    async def topic_breakdown(
        self, *, customer_id: str, since: datetime, until: datetime,
    ) -> list[dict]:
        """Conversation count per topic tag, as {label, value} for charts.

        Uses conversations.created_at (not updated_at) as the time anchor
        — a conversation "belongs" to the period it started in.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT unnest(topics) AS topic, count(*) AS count "
                "FROM conversations "
                "WHERE customer_id = $1 AND created_at >= $2 AND created_at < $3 "
                "GROUP BY topic ORDER BY count DESC",
                customer_id, since, until,
            )
        return [{"label": r["topic"], "value": r["count"]} for r in rows]

    async def specialist_metrics(
        self, *, customer_id: str, since: datetime, until: datetime,
    ) -> list[dict]:
        """Per-domain aggregate: count, success rate, avg turns, confirm rate.

        Rates computed here rather than in SQL so division-by-zero
        becomes None (no confirmations requested) instead of a CASE
        expression nobody wants to read.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT domain, "
                "  count(*)                                                   AS delegation_count, "
                "  count(*) FILTER (WHERE status = 'completed')               AS success_count, "
                "  avg(turns)                                                 AS avg_turns, "
                "  count(*) FILTER (WHERE confirmation_requested)             AS confirm_requested, "
                "  count(*) FILTER (WHERE confirmation_outcome = 'confirmed') AS confirm_accepted "
                "FROM delegations "
                "WHERE customer_id = $1 AND ended_at >= $2 AND ended_at < $3 "
                "GROUP BY domain ORDER BY delegation_count DESC",
                customer_id, since, until,
            )
        out = []
        for r in rows:
            total = r["delegation_count"]
            req = r["confirm_requested"]
            out.append({
                "domain": r["domain"],
                "delegation_count": total,
                "success_rate": r["success_count"] / total if total else None,
                "avg_turns": float(r["avg_turns"]) if r["avg_turns"] is not None else None,
                "confirmation_rate": r["confirm_accepted"] / req if req else None,
            })
        return out

    async def quality_counts(
        self, *, customer_id: str, since: datetime, until: datetime,
    ) -> dict[str, int]:
        """Count of conversations per quality flag in the window."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT unnest(quality_flags) AS flag, count(*) AS count "
                "FROM conversations "
                "WHERE customer_id = $1 AND created_at >= $2 AND created_at < $3 "
                "GROUP BY flag",
                customer_id, since, until,
            )
        return {r["flag"]: r["count"] for r in rows}

    async def conversation_count(
        self, *, customer_id: str, since: datetime, until: datetime,
    ) -> int:
        """Total conversations in the window — the trend denominator."""
        async with self._pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT count(*) FROM conversations "
                "WHERE customer_id = $1 AND created_at >= $2 AND created_at < $3",
                customer_id, since, until,
            )
        return int(n or 0)
