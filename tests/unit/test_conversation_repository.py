"""
Unit tests for ConversationRepository.

Mock the asyncpg pool to verify correct SQL and parameter passing.
Integration tests use real Postgres.
"""
import uuid
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.database.conversation_repository import ConversationRepository


class _FakePoolCM:
    """Mimics asyncpg pool.acquire() returning an async context manager."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value = _FakePoolCM(conn)
    return pool, conn


class TestEnsureConversation:
    async def test_executes_upsert_with_correct_params(self, mock_pool):
        pool, conn = mock_pool
        repo = ConversationRepository(pool)
        conv_id = str(uuid.uuid4())

        result = await repo.ensure_conversation(conv_id, "cust_1", "chat")
        assert result == conv_id

        conn.execute.assert_called_once()
        call_args = conn.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO conversations" in sql
        assert "ON CONFLICT" in sql


class TestAppendMessage:
    async def test_verifies_ownership_before_insert(self, mock_pool):
        pool, conn = mock_pool
        # Simulate conversation not found for this customer
        conn.fetchval.return_value = None

        repo = ConversationRepository(pool)
        result = await repo.append_message(
            str(uuid.uuid4()), "wrong_customer", "user", "hello"
        )
        assert result is None

    async def test_inserts_message_when_owned(self, mock_pool):
        pool, conn = mock_pool
        conv_id = str(uuid.uuid4())
        msg_id = uuid.uuid4()
        # First fetchval: ownership check returns customer_id
        # Second fetchval: INSERT RETURNING id
        conn.fetchval.side_effect = ["cust_1", msg_id]

        repo = ConversationRepository(pool)
        result = await repo.append_message(conv_id, "cust_1", "user", "hello")
        assert result is not None


class TestGetMessages:
    async def test_returns_none_for_nonexistent_conversation(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval.return_value = None  # conversation not found

        repo = ConversationRepository(pool)
        result = await repo.get_messages(str(uuid.uuid4()), "cust_1")
        assert result is None

    async def test_returns_list_for_existing_conversation(self, mock_pool):
        pool, conn = mock_pool
        conv_uuid = uuid.uuid4()
        conn.fetchval.return_value = 1  # conversation exists
        conn.fetch.return_value = [
            {"role": "user", "content": "hi", "timestamp": MagicMock(isoformat=lambda: "2026-03-19T10:00:00+00:00")},
        ]

        repo = ConversationRepository(pool)
        result = await repo.get_messages(str(conv_uuid), "cust_1")
        assert result is not None
        assert len(result) == 1


class TestDeleteCustomerData:
    async def test_returns_count(self, mock_pool):
        pool, conn = mock_pool
        conn.execute.return_value = "DELETE 3"

        repo = ConversationRepository(pool)
        count = await repo.delete_customer_data("cust_1")
        assert count == 3

    async def test_returns_zero_when_no_data(self, mock_pool):
        pool, conn = mock_pool
        conn.execute.return_value = "DELETE 0"

        repo = ConversationRepository(pool)
        count = await repo.delete_customer_data("cust_ghost")
        assert count == 0
