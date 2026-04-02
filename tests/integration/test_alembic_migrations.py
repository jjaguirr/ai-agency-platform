"""
Alembic migration integration tests — real Postgres.

Each test gets a *fresh throwaway database* so upgrade/downgrade can be
exercised without trampling the shared mcphub DB the other integration
tests use. We connect to the maintenance `postgres` database to
CREATE/DROP DATABASE around each test.

What's covered:

  • upgrade head from empty → all tables/columns/indexes present
  • downgrade base → everything gone
  • round-trip (up, down, up) is clean
  • schema parity: alembic head ≡ raw SQL files (same columns, types,
    nullability, defaults; same index names)
  • stamp head on a raw-SQL database works and check_schema() passes
  • check_schema() on an empty DB raises SchemaNotReadyError

These are *sync* tests. alembic.command.* calls into env.py which does
its own asyncio.run(); nesting that inside a pytest-asyncio loop would
deadlock. Verification queries use psycopg2 (already a dep) for the
same reason.

Skips the whole module if Postgres is unreachable.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterator

import pytest

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).parents[2]
RAW_SQL_DIR = REPO_ROOT / "src" / "database" / "migrations"


# ───────────────────────── connection plumbing ──────────────────────────


def _base_dsn_parts() -> dict:
    """Same resolution order as test_conversation_repository.py."""
    if explicit := os.getenv("CONVERSATION_REPO_TEST_DSN"):
        # crude parse — only used for host/port/user/pw extraction
        import urllib.parse as up
        u = up.urlparse(explicit)
        return dict(host=u.hostname, port=u.port or 5432,
                    user=u.username, password=u.password)
    return dict(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "mcphub"),
        password=os.getenv("POSTGRES_PASSWORD", "mcphub_password"),
    )


def _dsn(database: str) -> str:
    p = _base_dsn_parts()
    return (
        f"postgresql://{p['user']}:{p['password']}"
        f"@{p['host']}:{p['port']}/{database}"
    )


@pytest.fixture(scope="module")
def maint_conn():
    """Connection to the `postgres` maintenance DB for CREATE/DROP
    DATABASE. Module-scoped: one connection serves every test."""
    p = _base_dsn_parts()
    try:
        conn = psycopg2.connect(dbname="postgres", connect_timeout=3, **p)
    except psycopg2.OperationalError as e:
        pytest.skip(f"Postgres unavailable: {e}")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest.fixture
def fresh_db(maint_conn) -> Iterator[str]:
    """Create a uniquely-named empty database, yield its name, drop it
    afterwards. Each test runs in total isolation."""
    name = f"test_alembic_{uuid.uuid4().hex[:10]}"
    with maint_conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    try:
        yield name
    finally:
        with maint_conn.cursor() as cur:
            # FORCE in case a stray connection lingers (psycopg2 closes
            # eagerly so this is belt-and-braces).
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def alembic_cfg(fresh_db):
    """Alembic Config pointed at the fresh database via
    sqlalchemy.url — env.py checks that *first*, before $DATABASE_URL,
    so no process-global env mutation is needed (and these tests stay
    safe under pytest-xdist)."""
    from src.database.migrations import alembic_config

    cfg = alembic_config()
    cfg.set_main_option(
        "sqlalchemy.url",
        _dsn(fresh_db).replace("postgresql://", "postgresql+asyncpg://"),
    )
    return cfg


# ───────────────────────── introspection helpers ────────────────────────


def _columns(dbname: str, table: str) -> dict[str, dict]:
    """column_name → {data_type, is_nullable, column_default}"""
    with psycopg2.connect(dbname=dbname, **_base_dsn_parts()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s",
                (table,),
            )
            return {
                r[0]: {"type": r[1], "nullable": r[2], "default": r[3]}
                for r in cur.fetchall()
            }


def _indexes(dbname: str, table: str) -> set[str]:
    with psycopg2.connect(dbname=dbname, **_base_dsn_parts()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname='public' AND tablename=%s",
                (table,),
            )
            return {r[0] for r in cur.fetchall()}


def _tables(dbname: str) -> set[str]:
    with psycopg2.connect(dbname=dbname, **_base_dsn_parts()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
            return {r[0] for r in cur.fetchall()}


def _apply_raw_sql(dbname: str) -> None:
    """Replay the legacy raw SQL files (plus the schema_migrations
    bootstrap they assume) — this is what an existing prod DB looks
    like before the alembic switchover."""
    with psycopg2.connect(dbname=dbname, **_base_dsn_parts()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  version VARCHAR(50) PRIMARY KEY,"
                "  description TEXT,"
                "  applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)"
            )
            for f in sorted(RAW_SQL_DIR.glob("*.sql")):
                cur.execute(f.read_text())
        conn.commit()


# ───────────────────────────── tests ─────────────────────────────────────


def test_upgrade_head_creates_full_schema(fresh_db, alembic_cfg):
    from alembic import command

    command.upgrade(alembic_cfg, "head")

    tables = _tables(fresh_db)
    assert {"conversations", "messages", "delegation_records",
            "alembic_version"} <= tables

    # Column checks are *superset* assertions: future migrations may
    # add columns and this test must not need touching. Exact parity
    # against a frozen reference is test_schema_parity_with_raw_sql's
    # job — this test only proves the repo's queries have what they
    # need.
    conv_cols = _columns(fresh_db, "conversations")
    assert set(conv_cols) >= {
        "id", "customer_id", "channel", "created_at", "updated_at",
        "summary", "tags", "quality_signals",
    }
    # spot-check types the repo code depends on
    assert conv_cols["tags"]["type"] == "ARRAY"
    assert conv_cols["quality_signals"]["type"] == "jsonb"
    assert conv_cols["created_at"]["type"] == "timestamp with time zone"

    msg_cols = set(_columns(fresh_db, "messages"))
    assert msg_cols >= {"id", "conversation_id", "role", "content",
                        "timestamp", "specialist_domain"}

    deleg_cols = set(_columns(fresh_db, "delegation_records"))
    assert deleg_cols >= {
        "id", "conversation_id", "customer_id", "specialist_domain",
        "status", "turns", "confirmation_requested",
        "confirmation_outcome", "started_at", "completed_at",
        "error_message",
    }

    # named indexes from the raw SQL must all be present
    assert "idx_conversations_customer_updated" in _indexes(fresh_db, "conversations")
    assert "idx_conversations_tags" in _indexes(fresh_db, "conversations")
    assert "idx_conversations_needs_summary" in _indexes(fresh_db, "conversations")
    assert "idx_messages_conversation_timestamp" in _indexes(fresh_db, "messages")
    di = _indexes(fresh_db, "delegation_records")
    assert {"idx_delegation_records_conversation",
            "idx_delegation_records_customer_time",
            "idx_delegation_records_domain_status"} <= di


def test_downgrade_base_drops_everything(fresh_db, alembic_cfg):
    from alembic import command

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")

    remaining = _tables(fresh_db)
    # alembic_version stays (alembic owns it); domain tables are gone.
    assert "conversations" not in remaining
    assert "messages" not in remaining
    assert "delegation_records" not in remaining


def test_upgrade_downgrade_upgrade_round_trip(fresh_db, alembic_cfg):
    """Down-then-up must land on an identical schema. Catches downgrade
    steps that leave residue (orphan indexes, sequences) which then
    collide on the second upgrade."""
    from alembic import command

    command.upgrade(alembic_cfg, "head")
    snap1 = {t: _columns(fresh_db, t) for t in
             ("conversations", "messages", "delegation_records")}

    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    snap2 = {t: _columns(fresh_db, t) for t in
             ("conversations", "messages", "delegation_records")}

    assert snap1 == snap2


def test_schema_parity_with_raw_sql(maint_conn, alembic_cfg, fresh_db):
    """The alembic-built schema must match the legacy raw-SQL schema on
    every column (name, type, nullability) and every named index. This
    is what makes `alembic stamp head` safe on existing prod DBs."""
    from alembic import command

    # Build the alembic schema in fresh_db.
    command.upgrade(alembic_cfg, "head")

    # Build the raw-SQL schema in a second throwaway DB.
    raw_db = f"test_rawsql_{uuid.uuid4().hex[:10]}"
    with maint_conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{raw_db}"')
    try:
        _apply_raw_sql(raw_db)

        for table in ("conversations", "messages", "delegation_records"):
            a_cols = _columns(fresh_db, table)
            r_cols = _columns(raw_db, table)
            # Defaults can differ textually (e.g. now() vs now()) while
            # being semantically identical — compare presence-of-default
            # rather than the literal expression string.
            def norm(cols):
                return {
                    k: (v["type"], v["nullable"], v["default"] is not None)
                    for k, v in cols.items()
                }
            assert norm(a_cols) == norm(r_cols), (
                f"{table}: column mismatch\n"
                f"  alembic={norm(a_cols)}\n  rawsql={norm(r_cols)}"
            )

            a_idx = _indexes(fresh_db, table)
            r_idx = _indexes(raw_db, table)
            # Every raw-SQL index must exist under the same name in the
            # alembic schema. (Alembic may add alembic_version_pkc etc.
            # on its own table — irrelevant here.)
            assert r_idx <= a_idx, (
                f"{table}: missing indexes {r_idx - a_idx}"
            )
    finally:
        with maint_conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{raw_db}" WITH (FORCE)')


def test_stamp_head_on_raw_sql_database(fresh_db, alembic_cfg):
    """An existing database built from the raw SQL files can be adopted
    by `alembic stamp head` without re-running migrations or losing
    data, and check_schema() then accepts it."""
    import asyncio
    import asyncpg
    from alembic import command
    from src.database.conversation_repository import ConversationRepository

    _apply_raw_sql(fresh_db)

    # Insert a row so we can prove stamp didn't truncate anything.
    with psycopg2.connect(dbname=fresh_db, **_base_dsn_parts()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (id, customer_id, channel) "
                "VALUES ('keep-me', 'cust', 'chat')"
            )
        conn.commit()

    command.stamp(alembic_cfg, "head")

    # Data survived.
    with psycopg2.connect(dbname=fresh_db, **_base_dsn_parts()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_id FROM conversations WHERE id='keep-me'")
            assert cur.fetchone() == ("cust",)

    # check_schema() now passes — drive it through a real asyncpg pool
    # to exercise the production code path end-to-end.
    async def _verify():
        pool = await asyncpg.create_pool(_dsn(fresh_db), min_size=1, max_size=1)
        try:
            await ConversationRepository(pool).check_schema()
        finally:
            await pool.close()

    asyncio.run(_verify())


def test_check_schema_rejects_unmigrated_db(fresh_db):
    """Empty DB, never upgraded → check_schema() raises with the
    `alembic upgrade head` hint. check_schema() reads head_revision()
    from disk and queries the pool we hand it; no alembic Config
    needed."""
    import asyncio
    import asyncpg
    from src.database.conversation_repository import (
        ConversationRepository, SchemaNotReadyError,
    )

    async def _verify():
        pool = await asyncpg.create_pool(_dsn(fresh_db), min_size=1, max_size=1)
        try:
            repo = ConversationRepository(pool)
            with pytest.raises(SchemaNotReadyError) as exc:
                await repo.check_schema()
            assert "alembic upgrade head" in str(exc.value)
        finally:
            await pool.close()

    asyncio.run(_verify())
