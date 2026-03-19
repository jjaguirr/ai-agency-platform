"""
Integration tests for persistent conversation storage.

Uses a real PostgreSQL instance. Requires either:
  - docker-compose Postgres running on localhost:5432 (mcphub_test db)
  - testcontainers (auto-spins a container)

Tests verify:
  - Migration idempotency
  - Message persistence across connections
  - Chronological ordering
  - Tenant isolation
  - Pagination
  - GDPR deletion
"""
import asyncio
import uuid

import asyncpg
import pytest
import pytest_asyncio

from src.database.conversation_repository import ConversationRepository

POSTGRES_DSN = "postgresql://mcphub:mcphub_password@localhost:5432/mcphub_test"
MIGRATION_PATH = "src/database/migrations/001_conversations.sql"

pytestmark = pytest.mark.integration


async def _create_test_db():
    """Create mcphub_test database if it doesn't exist."""
    sys_conn = await asyncpg.connect(
        "postgresql://mcphub:mcphub_password@localhost:5432/mcphub"
    )
    try:
        exists = await sys_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'mcphub_test'"
        )
        if not exists:
            await sys_conn.execute("CREATE DATABASE mcphub_test")
    finally:
        await sys_conn.close()


async def _run_migration(pool: asyncpg.Pool):
    with open(MIGRATION_PATH) as f:
        sql = f.read()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def _drop_tables(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS messages CASCADE")
        await conn.execute("DROP TABLE IF EXISTS conversations CASCADE")


@pytest_asyncio.fixture
async def pg_pool():
    """Real asyncpg pool against mcphub_test."""
    try:
        await _create_test_db()
    except Exception:
        pytest.skip("PostgreSQL not available on localhost:5432")

    pool = await asyncpg.create_pool(POSTGRES_DSN, min_size=1, max_size=5)
    await _drop_tables(pool)
    await _run_migration(pool)
    yield pool
    await _drop_tables(pool)
    await pool.close()


@pytest_asyncio.fixture
async def repo(pg_pool):
    return ConversationRepository(pg_pool)


class TestMigrationIdempotency:
    async def test_migration_runs_twice_without_error(self, pg_pool):
        """Running the migration a second time should not fail or duplicate."""
        await _run_migration(pg_pool)
        await _run_migration(pg_pool)

        async with pg_pool.acquire() as conn:
            tables = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename IN ('conversations', 'messages')"
            )
            assert len(tables) == 2


class TestAppendAndRetrieve:
    async def test_append_message_persists(self, repo):
        conv_id = str(uuid.uuid4())
        customer = "cust_persist"

        await repo.ensure_conversation(conv_id, customer, "chat")
        msg_id = await repo.append_message(conv_id, customer, "user", "hello")

        assert msg_id is not None
        messages = await repo.get_messages(conv_id, customer)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"

    async def test_messages_survive_new_connection(self, pg_pool):
        """Messages persist across separate pool acquisitions."""
        repo = ConversationRepository(pg_pool)
        conv_id = str(uuid.uuid4())
        customer = "cust_survive"

        await repo.ensure_conversation(conv_id, customer, "api")
        await repo.append_message(conv_id, customer, "user", "ping")

        # Create a second repo instance (simulates restart with same pool)
        repo2 = ConversationRepository(pg_pool)
        messages = await repo2.get_messages(conv_id, customer)
        assert len(messages) == 1
        assert messages[0]["content"] == "ping"

    async def test_get_messages_chronological_order(self, repo):
        conv_id = str(uuid.uuid4())
        customer = "cust_chrono"

        await repo.ensure_conversation(conv_id, customer, "chat")
        await repo.append_message(conv_id, customer, "user", "first")
        await repo.append_message(conv_id, customer, "assistant", "second")
        await repo.append_message(conv_id, customer, "user", "third")

        messages = await repo.get_messages(conv_id, customer)
        assert len(messages) == 3
        contents = [m["content"] for m in messages]
        assert contents == ["first", "second", "third"]
        # Timestamps are ascending
        timestamps = [m["timestamp"] for m in messages]
        assert timestamps == sorted(timestamps)

    async def test_get_messages_nonexistent_conversation(self, repo):
        result = await repo.get_messages(str(uuid.uuid4()), "cust_none")
        assert result is None

    async def test_get_messages_empty_conversation(self, repo):
        conv_id = str(uuid.uuid4())
        customer = "cust_empty"
        await repo.ensure_conversation(conv_id, customer, "chat")

        messages = await repo.get_messages(conv_id, customer)
        assert messages == []


class TestEnsureConversation:
    async def test_idempotent(self, repo):
        conv_id = str(uuid.uuid4())
        customer = "cust_idem"

        id1 = await repo.ensure_conversation(conv_id, customer, "chat")
        id2 = await repo.ensure_conversation(conv_id, customer, "chat")
        assert id1 == id2

    async def test_creates_with_correct_channel(self, repo, pg_pool):
        conv_id = str(uuid.uuid4())
        customer = "cust_channel"

        await repo.ensure_conversation(conv_id, customer, "whatsapp")

        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT channel FROM conversations WHERE id = $1",
                uuid.UUID(conv_id),
            )
            assert row["channel"] == "whatsapp"


class TestTenantIsolation:
    async def test_customer_a_cannot_read_customer_b_messages(self, repo):
        conv_id = str(uuid.uuid4())
        customer_a = "cust_a"
        customer_b = "cust_b"

        await repo.ensure_conversation(conv_id, customer_a, "chat")
        await repo.append_message(conv_id, customer_a, "user", "secret")

        # Customer B tries to read with the same conversation_id
        result = await repo.get_messages(conv_id, customer_b)
        assert result is None  # not found, not empty

    async def test_append_to_wrong_customer_fails(self, repo):
        conv_id = str(uuid.uuid4())
        await repo.ensure_conversation(conv_id, "cust_owner", "chat")

        # Different customer tries to append
        result = await repo.append_message(conv_id, "cust_intruder", "user", "hack")
        assert result is None  # should fail silently


class TestListConversations:
    async def test_list_returns_most_recent_first(self, repo):
        customer = "cust_list"

        conv1 = str(uuid.uuid4())
        conv2 = str(uuid.uuid4())
        conv3 = str(uuid.uuid4())

        await repo.ensure_conversation(conv1, customer, "chat")
        await repo.ensure_conversation(conv2, customer, "api")
        await repo.ensure_conversation(conv3, customer, "whatsapp")

        convs = await repo.list_conversations(customer)
        assert len(convs) == 3
        # Most recent first
        assert convs[0]["conversation_id"] == conv3
        assert convs[1]["conversation_id"] == conv2
        assert convs[2]["conversation_id"] == conv1

    async def test_pagination_limit_offset(self, repo):
        customer = "cust_page"
        ids = []
        for _ in range(5):
            cid = str(uuid.uuid4())
            ids.append(cid)
            await repo.ensure_conversation(cid, customer, "chat")

        # Most recent first, so reversed
        ids.reverse()

        page1 = await repo.list_conversations(customer, limit=2, offset=0)
        assert len(page1) == 2
        assert page1[0]["conversation_id"] == ids[0]
        assert page1[1]["conversation_id"] == ids[1]

        page2 = await repo.list_conversations(customer, limit=2, offset=2)
        assert len(page2) == 2
        assert page2[0]["conversation_id"] == ids[2]
        assert page2[1]["conversation_id"] == ids[3]

    async def test_list_empty(self, repo):
        convs = await repo.list_conversations("cust_no_convos")
        assert convs == []

    async def test_list_isolated_per_customer(self, repo):
        await repo.ensure_conversation(str(uuid.uuid4()), "cust_x", "chat")
        await repo.ensure_conversation(str(uuid.uuid4()), "cust_y", "chat")

        x_convs = await repo.list_conversations("cust_x")
        assert len(x_convs) == 1


class TestDeleteCustomerData:
    async def test_deletes_conversations_and_messages(self, repo, pg_pool):
        customer = "cust_delete"
        conv_id = str(uuid.uuid4())

        await repo.ensure_conversation(conv_id, customer, "chat")
        await repo.append_message(conv_id, customer, "user", "delete me")
        await repo.append_message(conv_id, customer, "assistant", "ok")

        count = await repo.delete_customer_data(customer)
        assert count == 1  # 1 conversation deleted

        # Messages cascaded
        async with pg_pool.acquire() as conn:
            msg_count = await conn.fetchval(
                "SELECT count(*) FROM messages WHERE conversation_id = $1",
                uuid.UUID(conv_id),
            )
            assert msg_count == 0

        # Conversation gone
        assert await repo.get_messages(conv_id, customer) is None

    async def test_delete_returns_zero_for_unknown_customer(self, repo):
        count = await repo.delete_customer_data("cust_ghost")
        assert count == 0

    async def test_delete_does_not_affect_other_customers(self, repo):
        cust_a = "cust_del_a"
        cust_b = "cust_del_b"

        conv_a = str(uuid.uuid4())
        conv_b = str(uuid.uuid4())

        await repo.ensure_conversation(conv_a, cust_a, "chat")
        await repo.append_message(conv_a, cust_a, "user", "a's message")

        await repo.ensure_conversation(conv_b, cust_b, "chat")
        await repo.append_message(conv_b, cust_b, "user", "b's message")

        await repo.delete_customer_data(cust_a)

        # B's data intact
        messages = await repo.get_messages(conv_b, cust_b)
        assert len(messages) == 1
        assert messages[0]["content"] == "b's message"
