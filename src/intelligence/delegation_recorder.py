"""Writes delegation lifecycle events to Postgres.

Each specialist delegation produces one row in delegation_records:
created on start, updated on completion/failure/cancellation. This data
feeds topic tagging, specialist performance metrics, and the analytics
endpoint.
"""
from __future__ import annotations

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


class DelegationRecorder:

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def record_start(
        self,
        *,
        conversation_id: str,
        customer_id: str,
        specialist_domain: str,
    ) -> str:
        """Insert a delegation_records row with status='started'. Returns the record id."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "INSERT INTO delegation_records "
                "(conversation_id, customer_id, specialist_domain, status) "
                "VALUES ($1, $2, $3, 'started') "
                "RETURNING id::text",
                conversation_id, customer_id, specialist_domain,
            )

    async def record_end(
        self,
        *,
        record_id: str,
        status: str,
        turns: int,
        confirmation_requested: bool,
        confirmation_outcome: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update a delegation_records row with final status and completed_at."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE delegation_records "
                "SET status = $1, turns = $2, confirmation_requested = $3, "
                "    confirmation_outcome = $4, completed_at = now(), "
                "    error_message = $5 "
                "WHERE id = $6::uuid",
                status, turns, confirmation_requested,
                confirmation_outcome, error_message, record_id,
            )

    async def update_tags_from_delegations(
        self,
        *,
        customer_id: str,
        conversation_id: str,
    ) -> None:
        """Derive conversation tags from delegation_records.

        If no delegations exist, tags the conversation as 'general'.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT specialist_domain FROM delegation_records "
                "WHERE conversation_id = $1 AND customer_id = $2",
                conversation_id, customer_id,
            )
            tags = [r["specialist_domain"] for r in rows] or ["general"]
            await conn.execute(
                "UPDATE conversations SET tags = $1 "
                "WHERE id = $2 AND customer_id = $3",
                tags, conversation_id, customer_id,
            )

    async def delete_customer_data(self, *, customer_id: str) -> int:
        """GDPR: delete all delegation_records for a customer."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM delegation_records WHERE customer_id = $1",
                customer_id,
            )
        return int(result.split()[-1])
