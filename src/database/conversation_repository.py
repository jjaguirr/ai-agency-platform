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
    """Raised at startup when the database isn't at the Alembic head
    revision. Distinct from a generic asyncpg error so the lifespan
    hook can catch it and log an actionable message instead of a bare
    traceback."""


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
        Assert the database is at the Alembic head revision. Call once
        at startup.

        Compares ``alembic_version.version_num`` against the head of
        the on-disk migration chain. Anything other than an exact
        match raises SchemaNotReadyError with the literal command the
        operator should run.

        We deliberately do *not* auto-migrate. Production schema
        changes are an operator decision (backups, maintenance window,
        read replicas to consider). The API's job is to refuse to
        start with a clear instruction, not to guess.

        A database that predates Alembic — built from the raw SQL in
        ``src/database/migrations/*.sql`` — has no ``alembic_version``
        table. The error message covers that case explicitly: stamp
        first, then upgrade.
        """
        # Local import: pulls in alembic + reads alembic.ini from disk.
        # check_schema() runs once at startup so the cost is fine, and
        # keeping it out of module scope means importing this file in
        # tests doesn't require alembic to be installed.
        from src.database.migrations import current_revision, head_revision

        head = head_revision()
        async with self._pool.acquire() as conn:
            current = await current_revision(conn)

        if current == head:
            return

        if current is None:
            raise SchemaNotReadyError(
                "Database has not been initialised with Alembic "
                "(no alembic_version table, or it is empty). "
                "Run: `alembic upgrade head`. "
                "If this database was built from the legacy raw SQL "
                "files, run `alembic stamp head` first to adopt it."
            )

        raise SchemaNotReadyError(
            f"Database is at Alembic revision {current!r} but the code "
            f"expects {head!r}. Run: `alembic upgrade head`."
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
        tags: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Newest-first by updated_at. Covered by
        idx_conversations_customer_updated."""
        if tags:
            sql = (
                "SELECT id, channel, created_at, updated_at, "
                "       summary, tags, quality_signals "
                "FROM conversations WHERE customer_id = $1 "
                "AND tags @> $4::text[] "
                "ORDER BY updated_at DESC, id LIMIT $2 OFFSET $3"
            )
            args = [customer_id, limit, offset, tags]
        else:
            sql = (
                "SELECT id, channel, created_at, updated_at, "
                "       summary, tags, quality_signals "
                "FROM conversations WHERE customer_id = $1 "
                "ORDER BY updated_at DESC, id LIMIT $2 OFFSET $3"
            )
            args = [customer_id, limit, offset]

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [
            {
                "id": r["id"],
                "channel": r["channel"],
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
                "summary": r["summary"],
                "tags": list(r["tags"]) if r["tags"] else [],
                "quality_signals": dict(r["quality_signals"]) if r["quality_signals"] else {},
            }
            for r in rows
        ]

    async def list_conversations_enriched(
        self,
        *,
        customer_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Same ordering and paging as list_conversations, plus two
        per-conversation aggregates for the dashboard: message_count and
        the distinct set of specialist domains that touched it.

        One query, LATERAL subselect per conversation. For a 50-row
        dashboard page that's 50 small aggregations over
        idx_messages_conversation — fine. If a customer ever accrues
        tens of thousands of messages per conversation and this shows up
        in profiles, denormalise a counter onto the conversations row.

        COALESCE on both aggregates because a conversation with zero
        messages yields (NULL, NULL) from the lateral — the dashboard
        wants (0, []). FILTER on the array_agg drops NULL domains
        (user messages, general-assistance replies) so the dashboard
        never sees [None] as a "specialist".
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT c.id, c.channel, c.created_at, c.updated_at, "
                "       COALESCE(m.cnt, 0) AS message_count, "
                "       COALESCE(m.domains, '{}') AS specialist_domains "
                "FROM conversations c "
                "LEFT JOIN LATERAL ("
                "  SELECT COUNT(*) AS cnt, "
                "         array_agg(DISTINCT specialist_domain) "
                "           FILTER (WHERE specialist_domain IS NOT NULL) "
                "           AS domains "
                "  FROM messages WHERE conversation_id = c.id"
                ") m ON true "
                "WHERE c.customer_id = $1 "
                "ORDER BY c.updated_at DESC, c.id LIMIT $2 OFFSET $3",
                customer_id, limit, offset,
            )
        return [
            {
                "id": r["id"],
                "channel": r["channel"],
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
                "message_count": r["message_count"],
                # asyncpg returns text[] as a Python list already.
                "specialist_domains": list(r["specialist_domains"]),
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
        specialist_domain: Optional[str] = None,
    ) -> None:
        """
        Append one message and bump the conversation's updated_at.

        Tenant-guarded: the INSERT only accepts conversation_ids that
        belong to `customer_id`. If the conversation exists but belongs
        to someone else, the NOT EXISTS subquery makes the INSERT a
        no-op and the FK constraint catches the case where it doesn't
        exist at all.

        `specialist_domain` tags which specialist produced this reply
        (finance, scheduling, ...). None for user messages and for
        assistant turns the EA handled itself. Only the conversations
        route sets it, from ea.last_specialist_domain post-interaction.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Guarded insert: only if conversation belongs to this
                # customer. A bare INSERT would let customer B append
                # to customer A's conversation if B guessed the ID.
                result = await conn.execute(
                    "INSERT INTO messages "
                    "  (conversation_id, role, content, specialist_domain) "
                    "SELECT $1, $2, $3, $4 "
                    "WHERE EXISTS ("
                    "  SELECT 1 FROM conversations "
                    "  WHERE id = $1 AND customer_id = $5"
                    ")",
                    conversation_id, role, content, specialist_domain,
                    customer_id,
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

    # ─── intelligence ─────────────────────────────────────────────────────

    async def get_conversations_needing_summary(
        self,
        *,
        idle_threshold_minutes: int = 30,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Conversations idle longer than threshold with no summary.

        Cross-tenant: used by the background sweep, not tenant-scoped API.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, customer_id, updated_at "
                "FROM conversations "
                "WHERE summary IS NULL "
                "  AND updated_at < now() - make_interval(mins => $1) "
                "ORDER BY updated_at ASC "
                "LIMIT $2",
                idle_threshold_minutes, limit,
            )
        return [
            {
                "id": r["id"],
                "customer_id": r["customer_id"],
                "updated_at": _iso(r["updated_at"]),
            }
            for r in rows
        ]

    async def set_summary(
        self,
        *,
        conversation_id: str,
        summary: str,
    ) -> None:
        """Write the LLM-generated summary to the conversation."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET summary = $1 WHERE id = $2",
                summary, conversation_id,
            )

    async def set_quality_signals(
        self,
        *,
        conversation_id: str,
        signals: dict,
    ) -> None:
        """Write quality signal flags to the conversation."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET quality_signals = $1::jsonb WHERE id = $2",
                signals, conversation_id,
            )

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
