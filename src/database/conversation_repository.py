"""
Persistent conversation storage backed by PostgreSQL (asyncpg).

All queries enforce tenant isolation: every method that takes a
conversation_id also requires customer_id and filters on both.
A valid conversation_id with the wrong customer_id returns empty
results (not an error) — same 404-not-403 pattern as the API layer.
"""
import logging
import uuid
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


class ConversationRepository:
    """Encapsulates all conversation/message database operations."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def ensure_conversation(
        self, conversation_id: str, customer_id: str, channel: str
    ) -> str:
        """Create a conversation if it doesn't exist (upsert). Returns conversation_id."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (id, customer_id, channel)
                VALUES ($1, $2, $3)
                ON CONFLICT (id) DO NOTHING
                """,
                uuid.UUID(conversation_id),
                customer_id,
                channel,
            )
        return conversation_id

    async def append_message(
        self,
        conversation_id: str,
        customer_id: str,
        role: str,
        content: str,
    ) -> Optional[str]:
        """Append a message to a conversation.

        Returns the message UUID, or None if the conversation doesn't
        belong to customer_id (tenant isolation).
        """
        conv_uuid = uuid.UUID(conversation_id)

        async with self._pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT customer_id FROM conversations WHERE id = $1",
                conv_uuid,
            )
            if owner is None or owner != customer_id:
                return None

            # Update conversation timestamp
            await conn.execute(
                "UPDATE conversations SET updated_at = now() WHERE id = $1",
                conv_uuid,
            )

            msg_id = await conn.fetchval(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                conv_uuid,
                role,
                content,
            )
            return str(msg_id)

    async def get_messages(
        self, conversation_id: str, customer_id: str
    ) -> Optional[list[dict]]:
        """Get messages for a conversation in chronological order.

        Returns None if the conversation doesn't exist for this customer
        (triggers 404 in the API layer).
        Returns [] if the conversation exists but has no messages.
        """
        conv_uuid = uuid.UUID(conversation_id)

        async with self._pool.acquire() as conn:
            # Check conversation exists for this customer
            exists = await conn.fetchval(
                "SELECT 1 FROM conversations WHERE id = $1 AND customer_id = $2",
                conv_uuid,
                customer_id,
            )
            if exists is None:
                return None

            rows = await conn.fetch(
                """
                SELECT role, content, "timestamp"
                FROM messages
                WHERE conversation_id = $1
                ORDER BY "timestamp" ASC
                """,
                conv_uuid,
            )
            return [
                {
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"].isoformat(),
                }
                for row in rows
            ]

    async def list_conversations(
        self, customer_id: str, limit: int = 20, offset: int = 0
    ) -> list[dict]:
        """List conversations for a customer, most recent first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, channel, created_at, updated_at
                FROM conversations
                WHERE customer_id = $1
                ORDER BY updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                customer_id,
                limit,
                offset,
            )
            return [
                {
                    "conversation_id": str(row["id"]),
                    "channel": row["channel"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                }
                for row in rows
            ]

    async def delete_customer_data(self, customer_id: str) -> int:
        """Delete all conversations and messages for a customer.

        Messages cascade via FK ON DELETE CASCADE.
        Returns the number of deleted conversations.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM conversations WHERE customer_id = $1",
                customer_id,
            )
            return int(result.split()[-1])
