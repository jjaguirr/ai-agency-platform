"""
Persistent conversation storage backed by Postgres (asyncpg).

Exists because the in-memory history on each ExecutiveAssistant vanishes
when the EA is LRU-evicted from EARegistry or the process restarts.
Customers reasonably expect "what did I say yesterday" to work.

Every conversation-scoped method takes `customer_id` and filters on it
at the SQL level. A wrong customer_id yields an empty result, never a
row belonging to someone else. That's the tenant isolation boundary —
callers (API routes) pull customer_id from the JWT, pass it here, and
the query does the rest.

The repository is stateless — all durability is in Postgres. Two
instances on the same pool see the same data.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)


class SchemaNotReadyError(RuntimeError):
    """Raised at startup when the conversations/messages tables don't
    exist. Distinct from a generic asyncpg error so the lifespan hook
    can catch it and log an actionable message instead of a bare
    UndefinedTableError traceback."""


_REQUIRED_TABLES = ("conversations", "messages")


def _iso(ts: datetime) -> str:
    """Postgres TIMESTAMPTZ → ISO-8601 string for JSON responses."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


class ConversationRepository:
    """
    Thin asyncpg wrapper. No caching, no ORM, no batching — every method
    is one or two round trips. Conversations are low-frequency compared
    to the EA's LLM calls; premature optimisation here buys nothing.
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ─── schema ──────────────────────────────────────────────────────────

    async def check_schema(self) -> None:
        """
        Assert required tables exist. Call once at startup.

        Raises SchemaNotReadyError with a clear hint if a table is
        missing — typically "you forgot to run the migration".
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY($1::text[])",
                list(_REQUIRED_TABLES),
            )
        present = {r["table_name"] for r in rows}
        missing = [t for t in _REQUIRED_TABLES if t not in present]
        if missing:
            raise SchemaNotReadyError(
                f"Missing table(s): {missing}. "
                f"Apply migration src/database/migrations/001_conversations.sql "
                f"before starting the API."
            )

    # ─── conversations ───────────────────────────────────────────────────

    async def create_conversation(
        self,
        *,
        customer_id: str,
        conversation_id: Optional[str],
        channel: str,
    ) -> str:
        """
        Upsert a conversation header. Returns the conversation_id.

        If conversation_id is None, generate a UUID. If a row with that
        id already exists *and belongs to this customer*, do nothing
        (idempotent re-POST). If it belongs to a different customer,
        the INSERT is silently ignored — the caller will see None from
        get_messages and the API returns 404. We never overwrite
        ownership.
        """
        conv_id = conversation_id or str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO conversations (id, customer_id, channel) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (id) DO NOTHING",
                conv_id, customer_id, channel,
            )
        return conv_id

    async def get_conversation(
        self,
        *,
        customer_id: str,
        conversation_id: str,
    ) -> Optional[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, customer_id, channel, created_at, updated_at "
                "FROM conversations WHERE id = $1 AND customer_id = $2",
                conversation_id, customer_id,
            )
        if row is None:
            return None
        return {
            "id": row["id"],
            "customer_id": row["customer_id"],
            "channel": row["channel"],
            "created_at": _iso(row["created_at"]),
            "updated_at": _iso(row["updated_at"]),
        }

    async def list_conversations(
        self,
        *,
        customer_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Newest-first by updated_at. Covered by
        idx_conversations_customer_updated."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, channel, created_at, updated_at "
                "FROM conversations WHERE customer_id = $1 "
                "ORDER BY updated_at DESC, id LIMIT $2 OFFSET $3",
                customer_id, limit, offset,
            )
        return [
            {
                "id": r["id"],
                "channel": r["channel"],
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
            }
            for r in rows
        ]

    # ─── messages ────────────────────────────────────────────────────────

    async def append_message(
        self,
        *,
        customer_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """
        Append one message and bump the conversation's updated_at.

        Tenant-guarded: the INSERT only accepts conversation_ids that
        belong to `customer_id`. If the conversation exists but belongs
        to someone else, the NOT EXISTS subquery makes the INSERT a
        no-op and the FK constraint catches the case where it doesn't
        exist at all.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Guarded insert: only if conversation belongs to this
                # customer. A bare INSERT would let customer B append
                # to customer A's conversation if B guessed the ID.
                result = await conn.execute(
                    "INSERT INTO messages (conversation_id, role, content) "
                    "SELECT $1, $2, $3 "
                    "WHERE EXISTS ("
                    "  SELECT 1 FROM conversations "
                    "  WHERE id = $1 AND customer_id = $4"
                    ")",
                    conversation_id, role, content, customer_id,
                )
                # "INSERT 0 1" on success, "INSERT 0 0" on tenant mismatch.
                # The FK violation (conversation_id nonexistent) surfaces
                # only when the subquery finds nothing — in which case
                # we also get INSERT 0 0, not an FK error. So: raise
                # explicitly on zero rows, matching the test expectation
                # that appending to an unknown conversation fails loudly.
                if result == "INSERT 0 0":
                    raise asyncpg.ForeignKeyViolationError(
                        f"conversation {conversation_id!r} not found "
                        f"for customer {customer_id!r}"
                    )
                await conn.execute(
                    "UPDATE conversations SET updated_at = now() "
                    "WHERE id = $1 AND customer_id = $2",
                    conversation_id, customer_id,
                )

    async def get_messages(
        self,
        *,
        customer_id: str,
        conversation_id: str,
    ) -> Optional[list[dict[str, Any]]]:
        """
        Chronological message list, or None if the conversation doesn't
        exist *for this customer*. Empty list means "exists but no
        messages yet". Callers (history endpoint) map None → 404,
        empty → 200.

        Two queries rather than a JOIN: the existence check against
        conversations is what gives us the None/[] distinction. A
        LEFT JOIN would collapse both into "zero rows".
        """
        async with self._pool.acquire() as conn:
            owner = await conn.fetchval(
                "SELECT 1 FROM conversations "
                "WHERE id = $1 AND customer_id = $2",
                conversation_id, customer_id,
            )
            if owner is None:
                return None
            rows = await conn.fetch(
                "SELECT role, content, timestamp FROM messages "
                "WHERE conversation_id = $1 ORDER BY timestamp, id",
                conversation_id,
            )
        return [
            {"role": r["role"], "content": r["content"],
             "timestamp": _iso(r["timestamp"])}
            for r in rows
        ]

    # ─── GDPR ────────────────────────────────────────────────────────────

    async def delete_customer_data(self, *, customer_id: str) -> int:
        """
        Drop every conversation (and cascaded message) for this customer.
        Returns conversations deleted. Idempotent — second call on an
        already-deleted customer returns 0.

        Called by the customer deletion pipeline. Also reachable directly
        for ad-hoc cleanup.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM conversations WHERE customer_id = $1",
                customer_id,
            )
        # asyncpg returns "DELETE <n>"
        return int(result.split()[-1])
