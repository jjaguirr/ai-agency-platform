"""
ConversationRepository integration tests — real Postgres, no mocks.

These are the only tests that exercise the SQL. API-level tests mock the
repository; if the repository itself is wrong, this is where we find out.

Connection target resolution (first match wins):
  1. $CONVERSATION_REPO_TEST_DSN — explicit override
  2. $POSTGRES_* env vars (CI sets testuser/testpass/testdb)
  3. localhost mcphub defaults (docker-compose.yml)

Skips the whole module if Postgres is unreachable. CI runs unit/ only,
so these are opt-in locally or via a dedicated integration job.

Each test uses a unique customer_id prefix so parallel runs don't collide.
Teardown nukes that prefix.
"""
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

asyncpg = pytest.importorskip("asyncpg")

REPO_ROOT = Path(__file__).parents[2]
MIGRATION = REPO_ROOT / "src" / "database" / "migrations" / "001_conversations.sql"


def _dsn() -> str:
    if explicit := os.getenv("CONVERSATION_REPO_TEST_DSN"):
        return explicit
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "mcphub")
    user = os.getenv("POSTGRES_USER", "mcphub")
    pw = os.getenv("POSTGRES_PASSWORD", "mcphub_password")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


# Migration is idempotent so re-applying per-test is harmless; cheaper
# than fighting pytest-asyncio's event-loop-scope rules for a handful
# of integration tests.
_MIGRATION_SQL = MIGRATION.read_text()


@pytest_asyncio.fixture
async def pool():
    dsn = _dsn()
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, timeout=5)
    except (OSError, asyncpg.PostgresError) as e:
        pytest.skip(f"Postgres unavailable at {dsn!r}: {e}")

    # Apply migration. schema_migrations may not exist in a bare test DB,
    # so ensure it's present first (idempotent CREATE).
    async with p.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  version VARCHAR(50) PRIMARY KEY,"
            "  description TEXT,"
            "  applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)"
        )
        await conn.execute(_MIGRATION_SQL)

    yield p
    await p.close()


@pytest_asyncio.fixture
async def repo(pool):
    from src.database.conversation_repository import ConversationRepository
    return ConversationRepository(pool)


@pytest_asyncio.fixture
async def cust(pool):
    """Fresh customer_id per test, with post-test cleanup."""
    cid = f"test_conv_{uuid.uuid4().hex[:12]}"
    yield cid
    async with pool.acquire() as conn:
        # Cascade handles messages.
        await conn.execute(
            "DELETE FROM conversations WHERE customer_id = $1", cid)


pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────────────────
# Conversation lifecycle
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateAndFetch:
    async def test_create_then_get_messages_empty(self, repo, cust):
        conv_id = await repo.create_conversation(
            customer_id=cust, conversation_id="conv_empty", channel="chat")

        msgs = await repo.get_messages(customer_id=cust, conversation_id=conv_id)
        assert msgs == []

    async def test_get_messages_unknown_conversation(self, repo, cust):
        msgs = await repo.get_messages(
            customer_id=cust, conversation_id="never_created")
        assert msgs is None

    async def test_create_is_idempotent_same_customer(self, repo, cust):
        """Creating the same conversation twice is a no-op, not an error.

        Lets the POST route call create_conversation unconditionally
        without a SELECT-before-INSERT race."""
        a = await repo.create_conversation(
            customer_id=cust, conversation_id="conv_dup", channel="chat")
        b = await repo.create_conversation(
            customer_id=cust, conversation_id="conv_dup", channel="whatsapp")
        assert a == b == "conv_dup"

        # channel stays as the first write — upsert should not overwrite
        conv = await repo.get_conversation(
            customer_id=cust, conversation_id="conv_dup")
        assert conv["channel"] == "chat"

    async def test_create_generates_id_when_none(self, repo, cust):
        conv_id = await repo.create_conversation(
            customer_id=cust, conversation_id=None, channel="email")
        assert conv_id
        # Generated IDs are UUIDs
        uuid.UUID(conv_id)  # raises if not


class TestAppendMessage:
    async def test_append_preserves_order(self, repo, cust):
        await repo.create_conversation(
            customer_id=cust, conversation_id="conv_ord", channel="chat")
        for i in range(5):
            await repo.append_message(
                customer_id=cust,
                conversation_id="conv_ord",
                role="user" if i % 2 == 0 else "assistant",
                content=f"m{i}",
            )

        msgs = await repo.get_messages(
            customer_id=cust, conversation_id="conv_ord")
        assert [m["content"] for m in msgs] == ["m0", "m1", "m2", "m3", "m4"]
        assert [m["role"] for m in msgs] == [
            "user", "assistant", "user", "assistant", "user"]
        # Timestamps monotone
        ts = [m["timestamp"] for m in msgs]
        assert ts == sorted(ts)

    async def test_append_to_unknown_conversation_fails(self, repo, cust):
        """FK should reject a message for a conversation that doesn't exist."""
        with pytest.raises(Exception):  # asyncpg.ForeignKeyViolationError
            await repo.append_message(
                customer_id=cust,
                conversation_id="ghost",
                role="user",
                content="hello",
            )

    async def test_append_rejects_invalid_role(self, repo, cust):
        await repo.create_conversation(
            customer_id=cust, conversation_id="conv_role", channel="chat")
        with pytest.raises(Exception):  # CheckViolationError
            await repo.append_message(
                customer_id=cust,
                conversation_id="conv_role",
                role="human",  # LangChain convention — must be rejected
                content="hello",
            )

    async def test_append_bumps_conversation_updated_at(self, repo, cust):
        await repo.create_conversation(
            customer_id=cust, conversation_id="conv_bump", channel="chat")
        before = await repo.get_conversation(
            customer_id=cust, conversation_id="conv_bump")

        await repo.append_message(
            customer_id=cust, conversation_id="conv_bump",
            role="user", content="hi")

        after = await repo.get_conversation(
            customer_id=cust, conversation_id="conv_bump")
        assert after["updated_at"] >= before["updated_at"]


# ─────────────────────────────────────────────────────────────────────────────
# Tenant isolation — the whole point of taking customer_id on every call
# ─────────────────────────────────────────────────────────────────────────────

class TestTenantIsolation:
    async def test_wrong_customer_sees_none(self, repo, pool, cust):
        other = f"test_conv_other_{uuid.uuid4().hex[:12]}"
        try:
            await repo.create_conversation(
                customer_id=cust, conversation_id="conv_mine", channel="chat")
            await repo.append_message(
                customer_id=cust, conversation_id="conv_mine",
                role="user", content="secret")

            # `other` asks for `conv_mine` — must see nothing.
            msgs = await repo.get_messages(
                customer_id=other, conversation_id="conv_mine")
            assert msgs is None

            conv = await repo.get_conversation(
                customer_id=other, conversation_id="conv_mine")
            assert conv is None
        finally:
            async with pool.acquire() as c:
                await c.execute(
                    "DELETE FROM conversations WHERE customer_id = $1", other)

    async def test_wrong_customer_cannot_append(self, repo, cust):
        other = f"test_conv_other_{uuid.uuid4().hex[:12]}"
        await repo.create_conversation(
            customer_id=cust, conversation_id="conv_guard", channel="chat")

        # Appending with the wrong customer_id must not land in cust's conv.
        # Implementation choice: silent no-op or raise — either is fine as
        # long as the message does NOT appear in cust's history.
        try:
            await repo.append_message(
                customer_id=other, conversation_id="conv_guard",
                role="user", content="intrusion")
        except Exception:
            pass

        msgs = await repo.get_messages(
            customer_id=cust, conversation_id="conv_guard")
        contents = [m["content"] for m in msgs]
        assert "intrusion" not in contents

    async def test_same_conversation_id_different_customers_cannot_collide(
            self, repo, pool, cust):
        """
        conversation_id is the PK — two customers cannot both own "conv_x".

        This is a deliberate trade-off: UUIDs as default IDs make
        collision vanishingly rare, and the tenant filter on every
        read means customer B seeing customer A's conversation is
        impossible even if they *did* collide on an ID. We just
        assert the repo doesn't silently merge them.
        """
        other = f"test_conv_other_{uuid.uuid4().hex[:12]}"
        try:
            await repo.create_conversation(
                customer_id=cust, conversation_id="conv_shared", channel="chat")

            # Second create with a different customer_id must not
            # overwrite ownership.
            await repo.create_conversation(
                customer_id=other, conversation_id="conv_shared",
                channel="whatsapp")

            conv = await repo.get_conversation(
                customer_id=cust, conversation_id="conv_shared")
            assert conv is not None
            assert conv["customer_id"] == cust

            # Other still cannot see it.
            conv_other = await repo.get_conversation(
                customer_id=other, conversation_id="conv_shared")
            assert conv_other is None
        finally:
            async with pool.acquire() as c:
                await c.execute(
                    "DELETE FROM conversations WHERE customer_id = $1", other)


# ─────────────────────────────────────────────────────────────────────────────
# Listing + pagination
# ─────────────────────────────────────────────────────────────────────────────

class TestListConversations:
    async def test_list_returns_customers_conversations_only(
            self, repo, pool, cust):
        other = f"test_conv_other_{uuid.uuid4().hex[:12]}"
        try:
            await repo.create_conversation(
                customer_id=cust, conversation_id="conv_a", channel="chat")
            await repo.create_conversation(
                customer_id=cust, conversation_id="conv_b", channel="email")
            await repo.create_conversation(
                customer_id=other, conversation_id="conv_x", channel="chat")

            convs = await repo.list_conversations(customer_id=cust)
            ids = {c["id"] for c in convs}
            assert ids == {"conv_a", "conv_b"}
        finally:
            async with pool.acquire() as c:
                await c.execute(
                    "DELETE FROM conversations WHERE customer_id = $1", other)

    async def test_list_ordered_by_updated_at_desc(self, repo, cust):
        # Create in order a, b, c — then bump b so it sorts first.
        for conv_id in ("conv_a", "conv_b", "conv_c"):
            await repo.create_conversation(
                customer_id=cust, conversation_id=conv_id, channel="chat")
        await repo.append_message(
            customer_id=cust, conversation_id="conv_b",
            role="user", content="bump")

        convs = await repo.list_conversations(customer_id=cust)
        assert convs[0]["id"] == "conv_b"

    async def test_list_pagination(self, repo, cust):
        for i in range(7):
            await repo.create_conversation(
                customer_id=cust, conversation_id=f"conv_{i}", channel="chat")

        page1 = await repo.list_conversations(
            customer_id=cust, limit=3, offset=0)
        page2 = await repo.list_conversations(
            customer_id=cust, limit=3, offset=3)
        page3 = await repo.list_conversations(
            customer_id=cust, limit=3, offset=6)

        assert len(page1) == 3
        assert len(page2) == 3
        assert len(page3) == 1

        all_ids = [c["id"] for c in page1 + page2 + page3]
        assert len(all_ids) == len(set(all_ids))  # no duplicates across pages


# ─────────────────────────────────────────────────────────────────────────────
# Durability — the whole reason this repository exists
# ─────────────────────────────────────────────────────────────────────────────

class TestSurvivesReconnect:
    async def test_history_survives_pool_cycle(self, pool, cust):
        """
        Simulate process restart: build a repo, write, drop it, build a
        fresh repo on the same pool, read. Data must survive.

        (Closing and recreating the *pool* would be the full fidelity
        test, but pool creation is expensive and module-scoped. A fresh
        repo instance on the shared pool proves the data isn't hiding
        in repo-local state.)
        """
        from src.database.conversation_repository import ConversationRepository

        repo1 = ConversationRepository(pool)
        await repo1.create_conversation(
            customer_id=cust, conversation_id="conv_persist", channel="chat")
        await repo1.append_message(
            customer_id=cust, conversation_id="conv_persist",
            role="user", content="before restart")
        del repo1

        repo2 = ConversationRepository(pool)
        msgs = await repo2.get_messages(
            customer_id=cust, conversation_id="conv_persist")
        assert msgs is not None
        assert msgs[0]["content"] == "before restart"


# ─────────────────────────────────────────────────────────────────────────────
# GDPR deletion
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteCustomerData:
    async def test_delete_removes_conversations_and_messages(
            self, repo, pool, cust):
        await repo.create_conversation(
            customer_id=cust, conversation_id="conv_del", channel="chat")
        await repo.append_message(
            customer_id=cust, conversation_id="conv_del",
            role="user", content="to be forgotten")

        deleted = await repo.delete_customer_data(customer_id=cust)
        assert deleted >= 1  # at least the conversation row

        msgs = await repo.get_messages(
            customer_id=cust, conversation_id="conv_del")
        assert msgs is None

        # Verify cascade actually cleared messages, not just the header.
        async with pool.acquire() as conn:
            orphans = await conn.fetchval(
                "SELECT count(*) FROM messages WHERE conversation_id = $1",
                "conv_del")
        assert orphans == 0

    async def test_delete_is_idempotent(self, repo, cust):
        n1 = await repo.delete_customer_data(customer_id=cust)
        n2 = await repo.delete_customer_data(customer_id=cust)
        assert n1 == 0
        assert n2 == 0

    async def test_delete_does_not_touch_other_customers(
            self, repo, pool, cust):
        other = f"test_conv_other_{uuid.uuid4().hex[:12]}"
        try:
            await repo.create_conversation(
                customer_id=other, conversation_id="conv_survivor",
                channel="chat")

            await repo.delete_customer_data(customer_id=cust)

            survivor = await repo.get_conversation(
                customer_id=other, conversation_id="conv_survivor")
            assert survivor is not None
        finally:
            async with pool.acquire() as c:
                await c.execute(
                    "DELETE FROM conversations WHERE customer_id = $1", other)


# ─────────────────────────────────────────────────────────────────────────────
# Schema existence check (for startup assertion)
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaCheck:
    async def test_check_schema_passes_after_migration(self, repo):
        # Migration applied in pool fixture — should pass.
        await repo.check_schema()

    async def test_check_schema_raises_clearly_when_table_missing(self, pool):
        """
        Rename the table out of the way, assert check_schema raises a
        descriptive error (not a bare asyncpg error), then rename back.
        """
        from src.database.conversation_repository import (
            ConversationRepository, SchemaNotReadyError,
        )
        repo = ConversationRepository(pool)

        async with pool.acquire() as conn:
            await conn.execute(
                "ALTER TABLE conversations RENAME TO conversations_hidden")
        try:
            with pytest.raises(SchemaNotReadyError) as exc_info:
                await repo.check_schema()
            assert "conversations" in str(exc_info.value)
            assert "migration" in str(exc_info.value).lower()
        finally:
            async with pool.acquire() as conn:
                await conn.execute(
                    "ALTER TABLE conversations_hidden RENAME TO conversations")
