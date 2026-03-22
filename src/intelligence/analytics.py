"""Aggregation queries for conversation intelligence analytics.

All queries filter by customer_id (tenant isolation). The response
shape is structured for chart consumption — arrays of data points
with labels and values.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)


def compute_time_range(
    period: str,
    *,
    now: Optional[datetime] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> tuple[datetime, datetime]:
    """Convert a period string to (start, end) datetimes."""
    now = now or datetime.now(timezone.utc)

    if period == "custom":
        if not start or not end:
            raise ValueError("start and end required for custom period")
        return (
            datetime.fromisoformat(start),
            datetime.fromisoformat(end),
        )

    deltas = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    delta = deltas.get(period)
    if delta is None:
        raise ValueError(f"Unknown period: {period}")
    return now - delta, now


class AnalyticsService:

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_analytics(
        self,
        *,
        customer_id: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            overview = await self._overview(conn, customer_id, start, end)
            topics = await self._topic_breakdown(conn, customer_id, start, end)
            specialists = await self._specialist_performance(conn, customer_id, start, end)
            conv_trend = await self._conversation_trend(conn, customer_id, start, end)
            deleg_trend = await self._delegation_trend(conn, customer_id, start, end)

        total = overview["total_conversations"] or 0
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "overview": {
                "total_conversations": total,
                "total_delegations": overview["total_delegations"] or 0,
                "avg_messages_per_conversation": float(overview["avg_messages"] or 0),
                "escalation_rate": (
                    (overview["escalation_count"] or 0) / total if total else 0.0
                ),
                "unresolved_rate": (
                    (overview["unresolved_count"] or 0) / total if total else 0.0
                ),
            },
            "topics": {"breakdown": topics},
            "specialist_performance": specialists,
            "trends": {
                "conversations_by_day": conv_trend,
                "delegations_by_day": deleg_trend,
            },
        }

    async def _overview(
        self, conn, customer_id: str, start: datetime, end: datetime,
    ) -> dict:
        return await conn.fetchrow(
            "SELECT "
            "  (SELECT count(*) FROM conversations "
            "   WHERE customer_id = $1 AND created_at BETWEEN $2 AND $3) AS total_conversations, "
            "  (SELECT count(*) FROM delegation_records "
            "   WHERE customer_id = $1 AND started_at BETWEEN $2 AND $3) AS total_delegations, "
            "  (SELECT avg(msg_count) FROM ("
            "    SELECT count(*) AS msg_count FROM messages m "
            "    JOIN conversations c ON m.conversation_id = c.id "
            "    WHERE c.customer_id = $1 AND c.created_at BETWEEN $2 AND $3 "
            "    GROUP BY c.id"
            "  ) sub) AS avg_messages, "
            "  (SELECT count(*) FROM conversations "
            "   WHERE customer_id = $1 AND created_at BETWEEN $2 AND $3 "
            "   AND quality_signals->>'escalation' = 'true') AS escalation_count, "
            "  (SELECT count(*) FROM conversations "
            "   WHERE customer_id = $1 AND created_at BETWEEN $2 AND $3 "
            "   AND quality_signals->>'unresolved' = 'true') AS unresolved_count",
            customer_id, start, end,
        )

    async def _topic_breakdown(
        self, conn, customer_id: str, start: datetime, end: datetime,
    ) -> list[dict]:
        rows = await conn.fetch(
            "SELECT unnest(tags) AS domain, count(*) AS cnt "
            "FROM conversations "
            "WHERE customer_id = $1 AND created_at BETWEEN $2 AND $3 "
            "  AND array_length(tags, 1) > 0 "
            "GROUP BY domain ORDER BY cnt DESC",
            customer_id, start, end,
        )
        total = sum(r["cnt"] for r in rows) or 1
        return [
            {
                "domain": r["domain"],
                "count": r["cnt"],
                "percentage": round(r["cnt"] / total * 100, 1),
            }
            for r in rows
        ]

    async def _specialist_performance(
        self, conn, customer_id: str, start: datetime, end: datetime,
    ) -> list[dict]:
        rows = await conn.fetch(
            "SELECT "
            "  specialist_domain, "
            "  count(*) AS delegation_count, "
            "  count(*) FILTER (WHERE status = 'completed') AS completed, "
            "  avg(turns) AS avg_turns, "
            "  count(*) FILTER (WHERE confirmation_requested) AS conf_requested, "
            "  avg(EXTRACT(EPOCH FROM (completed_at - started_at))) "
            "    FILTER (WHERE completed_at IS NOT NULL) AS avg_resolution_seconds "
            "FROM delegation_records "
            "WHERE customer_id = $1 AND started_at BETWEEN $2 AND $3 "
            "  AND status != 'started' "
            "GROUP BY specialist_domain "
            "ORDER BY delegation_count DESC",
            customer_id, start, end,
        )
        return [
            {
                "domain": r["specialist_domain"],
                "delegation_count": r["delegation_count"],
                "success_rate": round(
                    r["completed"] / r["delegation_count"] * 100, 1,
                ) if r["delegation_count"] else 0.0,
                "avg_turns": round(float(r["avg_turns"] or 0), 1),
                "confirmation_rate": round(
                    r["conf_requested"] / r["delegation_count"] * 100, 1,
                ) if r["delegation_count"] else 0.0,
                "avg_resolution_seconds": (
                    round(float(r["avg_resolution_seconds"]), 1)
                    if r["avg_resolution_seconds"] is not None else None
                ),
            }
            for r in rows
        ]

    async def _conversation_trend(
        self, conn, customer_id: str, start: datetime, end: datetime,
    ) -> list[dict]:
        rows = await conn.fetch(
            "SELECT date_trunc('day', created_at)::date AS day, count(*) AS cnt "
            "FROM conversations "
            "WHERE customer_id = $1 AND created_at BETWEEN $2 AND $3 "
            "GROUP BY day ORDER BY day",
            customer_id, start, end,
        )
        return [{"date": str(r["day"]), "count": r["cnt"]} for r in rows]

    async def _delegation_trend(
        self, conn, customer_id: str, start: datetime, end: datetime,
    ) -> list[dict]:
        rows = await conn.fetch(
            "SELECT date_trunc('day', started_at)::date AS day, count(*) AS cnt "
            "FROM delegation_records "
            "WHERE customer_id = $1 AND started_at BETWEEN $2 AND $3 "
            "GROUP BY day ORDER BY day",
            customer_id, start, end,
        )
        return [{"date": str(r["day"]), "count": r["cnt"]} for r in rows]
