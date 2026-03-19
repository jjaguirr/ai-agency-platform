"""
Unit tests for ConversationRepository.

Mock the asyncpg pool to verify correct SQL, parameter passing, and
return value structure. Integration tests use real Postgres.
"""
import uuid
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, call

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


# ─── ensure_conversation ─────────────────────────────────────────────────────

class TestEnsureConversation:
    async def test_executes_upsert_sql(self, mock_pool):
        pool, conn = mock_pool
        repo = ConversationRepository(pool)
        conv_id = str(uuid.uuid4())

        result = await repo.ensure_conversation(conv_id, "cust_1", "chat")
        assert result == conv_id

        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        assert "INSERT INTO conversations" in sql
        assert "ON CONFLICT" in sql
        # Verify parameters: uuid, customer_id, channel
        assert conn.execute.call_args[0][1] == uuid.UUID(conv_id)
        assert conn.execute.call_args[0][2] == "cust_1"
        assert conn.execute.call_args[0][3] == "chat"


# ─── append_message ──────────────────────────────────────────────────────────

class TestAppendMessage:
    async def test_checks_ownership_with_correct_sql(self, mock_pool):
        pool, conn = mock_pool
        conv_id = str(uuid.uuid4())
        conn.fetchval.return_value = None  # not found

        repo = ConversationRepository(pool)
        result = await repo.append_message(conv_id, "wrong_cust", "user", "hi")
        assert result is None

        # First fetchval: ownership check
        ownership_sql = conn.fetchval.call_args_list[0][0][0]
        assert "SELECT customer_id FROM conversations" in ownership_sql
        assert "WHERE id = $1" in ownership_sql

    async def test_rejects_wrong_customer(self, mock_pool):
        pool, conn = mock_pool
        conv_id = str(uuid.uuid4())
        # Conversation exists but belongs to different customer
        conn.fetchval.return_value = "real_owner"

        repo = ConversationRepository(pool)
        result = await repo.append_message(conv_id, "intruder", "user", "hi")
        assert result is None

    async def test_or_logic_in_ownership_check(self, mock_pool):
        """owner is None OR owner != customer_id -> return None.
        Both conditions must independently reject."""
        pool, conn = mock_pool
        conv_id = str(uuid.uuid4())

        # Case 1: owner is None (conversation doesn't exist)
        conn.fetchval.return_value = None
        repo = ConversationRepository(pool)
        assert await repo.append_message(conv_id, "cust", "user", "hi") is None

        # Case 2: owner exists but doesn't match
        conn.fetchval.reset_mock()
        conn.fetchval.return_value = "other_cust"
        assert await repo.append_message(conv_id, "cust", "user", "hi") is None

    async def test_inserts_message_updates_timestamp_and_returns_id(self, mock_pool):
        pool, conn = mock_pool
        conv_id = str(uuid.uuid4())
        msg_id = uuid.uuid4()
        # fetchval calls: 1) ownership check, 2) INSERT RETURNING id
        conn.fetchval.side_effect = ["cust_1", msg_id]

        repo = ConversationRepository(pool)
        result = await repo.append_message(conv_id, "cust_1", "user", "hello")

        assert result == str(msg_id)

        # Verify UPDATE was called (updated_at)
        execute_calls = conn.execute.call_args_list
        assert len(execute_calls) == 1
        update_sql = execute_calls[0][0][0]
        assert "UPDATE conversations SET updated_at" in update_sql

        # Verify INSERT was the second fetchval
        insert_sql = conn.fetchval.call_args_list[1][0][0]
        assert "INSERT INTO messages" in insert_sql
        assert "RETURNING id" in insert_sql

    async def test_passes_uuid_not_string_to_queries(self, mock_pool):
        """conv_uuid must be a uuid.UUID, not a string."""
        pool, conn = mock_pool
        conv_id = str(uuid.uuid4())
        conn.fetchval.side_effect = ["cust_1", uuid.uuid4()]

        repo = ConversationRepository(pool)
        await repo.append_message(conv_id, "cust_1", "user", "hello")

        # Ownership check passes UUID
        ownership_param = conn.fetchval.call_args_list[0][0][1]
        assert isinstance(ownership_param, uuid.UUID)
        assert str(ownership_param) == conv_id


# ─── get_messages ─────────────────────────────────────────────────────────────

class TestGetMessages:
    async def test_returns_none_for_nonexistent_conversation(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval.return_value = None

        repo = ConversationRepository(pool)
        result = await repo.get_messages(str(uuid.uuid4()), "cust_1")
        assert result is None

        # Verify tenant-isolated SQL
        sql = conn.fetchval.call_args[0][0]
        assert "customer_id = $2" in sql

    async def test_returns_empty_list_for_conversation_with_no_messages(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval.return_value = 1  # conversation exists
        conn.fetch.return_value = []  # no messages

        repo = ConversationRepository(pool)
        result = await repo.get_messages(str(uuid.uuid4()), "cust_1")
        assert result == []

    async def test_returns_correct_dict_keys(self, mock_pool):
        pool, conn = mock_pool
        ts = datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc)
        conn.fetchval.return_value = 1
        conn.fetch.return_value = [
            {"role": "user", "content": "hi", "timestamp": ts},
        ]

        repo = ConversationRepository(pool)
        result = await repo.get_messages(str(uuid.uuid4()), "cust_1")

        assert len(result) == 1
        msg = result[0]
        # Assert exact keys — catches key-name mutations
        assert set(msg.keys()) == {"role", "content", "timestamp"}
        assert msg["role"] == "user"
        assert msg["content"] == "hi"
        assert msg["timestamp"] == ts.isoformat()

    async def test_orders_by_timestamp_asc(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval.return_value = 1
        conn.fetch.return_value = []

        repo = ConversationRepository(pool)
        await repo.get_messages(str(uuid.uuid4()), "cust_1")

        fetch_sql = conn.fetch.call_args[0][0]
        assert 'ORDER BY "timestamp" ASC' in fetch_sql

    async def test_passes_uuid_not_string(self, mock_pool):
        pool, conn = mock_pool
        conv_id = str(uuid.uuid4())
        conn.fetchval.return_value = None

        repo = ConversationRepository(pool)
        await repo.get_messages(conv_id, "cust_1")

        param = conn.fetchval.call_args[0][1]
        assert isinstance(param, uuid.UUID)


# ─── list_conversations ──────────────────────────────────────────────────────

class TestListConversations:
    async def test_returns_correct_dict_keys(self, mock_pool):
        pool, conn = mock_pool
        ts = datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc)
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": uuid.uuid4(),
            "channel": "chat",
            "created_at": ts,
            "updated_at": ts,
        }[key]
        conn.fetch.return_value = [row]

        repo = ConversationRepository(pool)
        result = await repo.list_conversations("cust_1")

        assert len(result) == 1
        conv = result[0]
        assert set(conv.keys()) == {"conversation_id", "channel", "created_at", "updated_at"}
        assert conv["channel"] == "chat"
        assert conv["created_at"] == ts.isoformat()
        assert conv["updated_at"] == ts.isoformat()

    async def test_passes_limit_and_offset_to_query(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch.return_value = []

        repo = ConversationRepository(pool)
        await repo.list_conversations("cust_1", limit=5, offset=10)

        args = conn.fetch.call_args[0]
        sql = args[0]
        assert "LIMIT $2 OFFSET $3" in sql
        assert args[1] == "cust_1"
        assert args[2] == 5
        assert args[3] == 10

    async def test_default_limit_offset(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch.return_value = []

        repo = ConversationRepository(pool)
        await repo.list_conversations("cust_1")

        args = conn.fetch.call_args[0]
        assert args[2] == 20  # default limit
        assert args[3] == 0   # default offset

    async def test_orders_by_updated_at_desc(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch.return_value = []

        repo = ConversationRepository(pool)
        await repo.list_conversations("cust_1")

        sql = conn.fetch.call_args[0][0]
        assert "ORDER BY updated_at DESC" in sql


# ─── delete_customer_data ────────────────────────────────────────────────────

class TestDeleteCustomerData:
    async def test_returns_count_from_delete(self, mock_pool):
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

    async def test_deletes_correct_table_with_customer_filter(self, mock_pool):
        pool, conn = mock_pool
        conn.execute.return_value = "DELETE 0"

        repo = ConversationRepository(pool)
        await repo.delete_customer_data("cust_1")

        sql = conn.execute.call_args[0][0]
        assert "DELETE FROM conversations" in sql
        assert "customer_id = $1" in sql
        assert conn.execute.call_args[0][1] == "cust_1"

    async def test_parses_last_word_of_result(self, mock_pool):
        """Ensures we parse 'DELETE N' correctly — split()[-1] not split()[1]."""
        pool, conn = mock_pool
        conn.execute.return_value = "DELETE 42"

        repo = ConversationRepository(pool)
        assert await repo.delete_customer_data("c") == 42
