"""
Alembic migration chain — schema parity and round-trip tests.

The whole point of moving off raw SQL is version tracking.  But the
move is only safe if the Alembic chain produces the *same* schema the
raw SQL produced.  These tests pin that invariant: introspect Postgres
after `upgrade head`, assert every column/constraint/index the raw
SQL would have created is present, then prove `downgrade base` cleanly
unwinds.  When they pass, an existing production database can be
`alembic stamp head`'d without re-running anything.

Each test gets a throwaway schema (Postgres namespace, not "schema" in
the migration sense).  That's how we get hermetic isolation without a
fresh database per test — `CREATE SCHEMA test_xyz`, set search_path,
run migrations, drop the schema.  Alembic's version table lands in the
throwaway namespace too because it's unqualified.

DSN resolution mirrors test_conversation_repository so the same env
drives both.  Skips on connect failure — these are integration tests.
"""
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

asyncpg = pytest.importorskip("asyncpg")

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
LEGACY_MIGRATIONS = REPO_ROOT / "src" / "database" / "migrations"

# Resolved once at import.  Tests assert against this instead of
# pinning the literal hex — adding migration 003 shouldn't break the
# stamp test.
_SCRIPT = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
HEAD_REVISION = _SCRIPT.get_heads()[0]

pytestmark = pytest.mark.integration


def _dsn() -> str:
    if explicit := os.getenv("CONVERSATION_REPO_TEST_DSN"):
        return explicit
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "mcphub")
    user = os.getenv("POSTGRES_USER", "mcphub")
    pw = os.getenv("POSTGRES_PASSWORD", "mcphub_password")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def _alembic_cfg(schema: str | None) -> Config:
    """Pure config builder — no env mutation.  Fixtures handle
    DATABASE_URL via monkeypatch so a test failure doesn't leak the
    var into the rest of the suite."""
    cfg = Config(str(ALEMBIC_INI))
    # Schema namespace via cfg.attributes — env.py picks it up and
    # sets search_path on the connection.  Can't smuggle it through
    # the URL: SQLAlchemy's asyncpg dialect translates query params
    # to connect kwargs and asyncpg doesn't take libpq-style options=.
    if schema is not None:
        cfg.attributes["schema"] = schema
    return cfg


@pytest_asyncio.fixture
async def conn():
    """Bare asyncpg connection, no pool — introspection only."""
    dsn = _dsn()
    try:
        c = await asyncpg.connect(dsn, timeout=5)
    except (OSError, asyncpg.PostgresError) as e:
        pytest.skip(f"Postgres unavailable at {dsn!r}: {e}")
    yield c
    await c.close()


@pytest_asyncio.fixture
async def fresh_schema(conn, monkeypatch):
    """Throwaway Postgres schema namespace.  Yields the schema name;
    teardown drops it CASCADE so half-finished migrations don't leak.

    Pins DATABASE_URL for env.py.  monkeypatch restores whatever the
    dev shell had exported (or nothing) even if the test body raises."""
    monkeypatch.setenv("DATABASE_URL", _dsn())
    name = f"alembic_test_{uuid.uuid4().hex[:12]}"
    await conn.execute(f'CREATE SCHEMA "{name}"')
    try:
        yield name
    finally:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


# ─── introspection helpers ───────────────────────────────────────────────────

async def _columns(conn, schema: str, table: str) -> dict[str, dict]:
    rows = await conn.fetch(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = $1 AND table_name = $2",
        schema, table,
    )
    return {
        r["column_name"]: {
            "type": r["data_type"],
            "nullable": r["is_nullable"] == "YES",
            "default": r["column_default"],
        }
        for r in rows
    }


async def _indexes(conn, schema: str, table: str) -> set[str]:
    rows = await conn.fetch(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = $1 AND tablename = $2",
        schema, table,
    )
    return {r["indexname"] for r in rows}


async def _index_def(conn, schema: str, name: str) -> str:
    """Lower-cased CREATE INDEX statement — pg_indexes formats it
    deterministically so we can assert column order, DESC, USING."""
    text = await conn.fetchval(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = $1 AND indexname = $2",
        schema, name,
    )
    return (text or "").lower()


async def _check_constraints(conn, schema: str, table: str) -> dict[str, str]:
    """name → check clause text.  pg_get_constraintdef gives the
    canonical form (Postgres normalises the SQL we wrote)."""
    rows = await conn.fetch(
        "SELECT con.conname, pg_get_constraintdef(con.oid) AS def "
        "FROM pg_constraint con "
        "JOIN pg_class rel ON rel.oid = con.conrelid "
        "JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace "
        "WHERE nsp.nspname = $1 AND rel.relname = $2 AND con.contype = 'c'",
        schema, table,
    )
    return {r["conname"]: r["def"] for r in rows}


async def _foreign_keys(conn, schema: str, table: str) -> dict[str, str]:
    rows = await conn.fetch(
        "SELECT con.conname, pg_get_constraintdef(con.oid) AS def "
        "FROM pg_constraint con "
        "JOIN pg_class rel ON rel.oid = con.conrelid "
        "JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace "
        "WHERE nsp.nspname = $1 AND rel.relname = $2 AND con.contype = 'f'",
        schema, table,
    )
    return {r["conname"]: r["def"] for r in rows}


async def _tables(conn, schema: str) -> set[str]:
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = $1 AND table_type = 'BASE TABLE'",
        schema,
    )
    return {r["table_name"] for r in rows}


# ─── tests ───────────────────────────────────────────────────────────────────

class TestUpgradeHead:
    """Schema at head must match what the raw SQL would have produced.
    These assertions are derived directly from
    src/database/migrations/00*.sql — if they drift, one side is wrong."""

    async def test_creates_all_three_tables(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        present = await _tables(conn, fresh_schema)
        # alembic_version is the tracking table — it lands here too
        # because it's unqualified and search_path points at us.
        assert present >= {"conversations", "messages", "delegation_records",
                           "alembic_version"}

    async def test_conversations_columns(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        cols = await _columns(conn, fresh_schema, "conversations")

        # 001: base columns
        assert cols["id"]["type"] == "text"
        assert cols["id"]["nullable"] is False
        assert cols["customer_id"]["type"] == "text"
        assert cols["customer_id"]["nullable"] is False
        assert cols["channel"]["type"] == "text"
        assert cols["channel"]["nullable"] is False
        assert cols["created_at"]["type"] == "timestamp with time zone"
        assert cols["created_at"]["nullable"] is False
        assert "now()" in (cols["created_at"]["default"] or "")
        assert cols["updated_at"]["type"] == "timestamp with time zone"
        assert cols["updated_at"]["nullable"] is False
        assert "now()" in (cols["updated_at"]["default"] or "")

        # 002: intelligence columns
        assert cols["summary"]["type"] == "text"
        assert cols["summary"]["nullable"] is True
        assert cols["tags"]["type"] == "ARRAY"
        # Postgres normalises '{}' → ARRAY[]::text[] in column_default,
        # but both contain the empty-array signal.  Be loose.
        assert cols["tags"]["default"] is not None
        assert cols["quality_signals"]["type"] == "jsonb"
        assert "'{}'" in (cols["quality_signals"]["default"] or "")

    async def test_conversations_check_constraint(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        checks = await _check_constraints(conn, fresh_schema, "conversations")
        # One CHECK on channel.  Postgres rewrites the IN list as
        # channel = ANY (ARRAY['phone'::text, ...]) — the literals are
        # always single-quoted.  Match the quoted form so 'phone'
        # doesn't accidentally match in 'telephone'.
        assert len(checks) == 1
        ((name, clause),) = checks.items()
        assert "channel" in clause
        for v in ("phone", "whatsapp", "email", "chat"):
            assert f"'{v}'" in clause
        # Naming convention: ck_<table>_<name>
        assert name.startswith("ck_conversations_")

    async def test_conversations_indexes(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        idx = await _indexes(conn, fresh_schema, "conversations")
        # Hand-picked names from the raw SQL — preserved verbatim.
        assert "idx_conversations_customer_updated" in idx
        assert "idx_conversations_tags" in idx
        assert "idx_conversations_needs_summary" in idx

        # Column order and DESC direction matter for the planner.
        # pg_indexes formats this as the parenthesised column list.
        listing = await _index_def(conn, fresh_schema,
                                   "idx_conversations_customer_updated")
        assert "(customer_id, updated_at desc)" in listing

        # Partial index: WHERE clause survives.
        partial = await _index_def(conn, fresh_schema,
                                   "idx_conversations_needs_summary")
        assert "(customer_id, updated_at)" in partial
        assert "where (summary is null)" in partial

        # GIN method on the tags index.
        gin = await _index_def(conn, fresh_schema, "idx_conversations_tags")
        assert "using gin (tags)" in gin

    async def test_messages_columns(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        cols = await _columns(conn, fresh_schema, "messages")

        assert cols["id"]["type"] == "uuid"
        assert "gen_random_uuid()" in (cols["id"]["default"] or "")
        assert cols["conversation_id"]["type"] == "text"
        assert cols["conversation_id"]["nullable"] is False
        assert cols["role"]["type"] == "text"
        assert cols["role"]["nullable"] is False
        assert cols["content"]["type"] == "text"
        assert cols["content"]["nullable"] is False
        assert cols["timestamp"]["type"] == "timestamp with time zone"
        assert cols["timestamp"]["nullable"] is False
        assert "now()" in (cols["timestamp"]["default"] or "")
        # 002b: specialist_domain — nullable, no default.
        assert cols["specialist_domain"]["type"] == "text"
        assert cols["specialist_domain"]["nullable"] is True

    async def test_messages_role_check(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        checks = await _check_constraints(conn, fresh_schema, "messages")
        assert len(checks) == 1
        ((_, clause),) = checks.items()
        assert "role" in clause
        for v in ("user", "assistant", "system"):
            assert f"'{v}'" in clause

    async def test_messages_fk_cascade(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        fks = await _foreign_keys(conn, fresh_schema, "messages")
        assert len(fks) == 1
        ((_, clause),) = fks.items()
        assert "REFERENCES" in clause and "conversations(id)" in clause
        assert "ON DELETE CASCADE" in clause

    async def test_messages_index(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        idx = await _indexes(conn, fresh_schema, "messages")
        assert "idx_messages_conversation_timestamp" in idx
        # Order matters: conversation_id leads, timestamp trails.
        d = await _index_def(conn, fresh_schema,
                             "idx_messages_conversation_timestamp")
        assert "(conversation_id, \"timestamp\")" in d \
            or "(conversation_id, timestamp)" in d

    async def test_delegation_records_columns(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        cols = await _columns(conn, fresh_schema, "delegation_records")

        assert cols["id"]["type"] == "uuid"
        assert "gen_random_uuid()" in (cols["id"]["default"] or "")
        assert cols["conversation_id"]["type"] == "text"
        assert cols["conversation_id"]["nullable"] is False
        assert cols["customer_id"]["type"] == "text"
        assert cols["customer_id"]["nullable"] is False
        assert cols["specialist_domain"]["type"] == "text"
        assert cols["specialist_domain"]["nullable"] is False
        assert cols["status"]["type"] == "text"
        assert cols["status"]["nullable"] is False
        assert cols["turns"]["type"] == "integer"
        assert cols["turns"]["default"] == "1"
        assert cols["confirmation_requested"]["type"] == "boolean"
        assert cols["confirmation_requested"]["default"] == "false"
        assert cols["confirmation_outcome"]["type"] == "text"
        assert cols["confirmation_outcome"]["nullable"] is True
        assert cols["started_at"]["type"] == "timestamp with time zone"
        assert "now()" in (cols["started_at"]["default"] or "")
        assert cols["completed_at"]["type"] == "timestamp with time zone"
        assert cols["completed_at"]["nullable"] is True
        assert cols["error_message"]["type"] == "text"
        assert cols["error_message"]["nullable"] is True

    async def test_delegation_records_checks(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        checks = await _check_constraints(conn, fresh_schema, "delegation_records")
        # Two CHECKs: status and confirmation_outcome.  Pull them apart
        # by which column they reference — joining the clauses and
        # blind-grepping would let one constraint's literals satisfy
        # the other's assertion.
        assert len(checks) == 2
        by_col = {}
        for clause in checks.values():
            if "status" in clause:
                by_col["status"] = clause
            elif "confirmation_outcome" in clause:
                by_col["confirmation_outcome"] = clause
        assert set(by_col) == {"status", "confirmation_outcome"}
        for v in ("started", "completed", "failed", "cancelled"):
            assert f"'{v}'" in by_col["status"]
        for v in ("confirmed", "declined"):
            assert f"'{v}'" in by_col["confirmation_outcome"]
        # The outcome check allows NULL — the IN list alone doesn't.
        assert "is null" in by_col["confirmation_outcome"].lower()

    async def test_delegation_records_fk_cascade(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        fks = await _foreign_keys(conn, fresh_schema, "delegation_records")
        assert len(fks) == 1
        ((_, clause),) = fks.items()
        assert "conversations(id)" in clause
        assert "ON DELETE CASCADE" in clause

    async def test_delegation_records_indexes(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        idx = await _indexes(conn, fresh_schema, "delegation_records")
        assert "idx_delegation_records_conversation" in idx
        assert "idx_delegation_records_customer_time" in idx
        assert "idx_delegation_records_domain_status" in idx

        d = await _index_def(conn, fresh_schema,
                             "idx_delegation_records_customer_time")
        assert "(customer_id, started_at desc)" in d

        d = await _index_def(conn, fresh_schema,
                             "idx_delegation_records_domain_status")
        assert "(specialist_domain, status, started_at)" in d


class TestDowngrade:
    """downgrade base must cleanly drop everything the chain created.
    No leftover tables, no leftover indexes — only alembic_version
    survives (Alembic owns that, not our migrations)."""

    async def test_full_round_trip(self, conn, fresh_schema):
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        present = await _tables(conn, fresh_schema)
        # alembic_version stays — it's the version-tracking table,
        # not part of any migration's upgrade/downgrade.
        assert present == {"alembic_version"}

    async def test_partial_downgrade_to_001(self, conn, fresh_schema):
        """Downgrade one step: 002's columns/table gone, 001's intact.
        Proves the chain is actually steppable, not just head-or-base."""
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")

        # Find revision 001's id by its position — it's the only one
        # whose down_revision is None.
        base_rev = next(
            r.revision for r in _SCRIPT.walk_revisions()
            if r.down_revision is None
        )
        command.downgrade(cfg, base_rev)

        present = await _tables(conn, fresh_schema)
        assert "conversations" in present
        assert "messages" in present
        assert "delegation_records" not in present

        conv_cols = await _columns(conn, fresh_schema, "conversations")
        assert "summary" not in conv_cols
        assert "tags" not in conv_cols
        assert "quality_signals" not in conv_cols

        msg_cols = await _columns(conn, fresh_schema, "messages")
        assert "specialist_domain" not in msg_cols

    async def test_upgrade_after_full_downgrade(self, conn, fresh_schema):
        """Up, down, up again — second upgrade must not collide with
        leftovers from the first.  Catches DROP statements that miss
        an index or constraint."""
        cfg = _alembic_cfg(fresh_schema)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")  # would raise if downgrade was incomplete

        present = await _tables(conn, fresh_schema)
        assert {"conversations", "messages", "delegation_records"} <= present


class TestStampOnLegacyDB:
    """A database that ran the raw SQL files should be stampable to
    head with no DDL.  This is the production migration path: existing
    deployments don't re-run anything, they just get an alembic_version
    row pointing at head.

    Runs against `public`, not a throwaway namespace.  The legacy SQL's
    idempotence DO blocks query information_schema.columns without a
    table_schema filter — they were written for a single-schema world
    (public) and break in subtle ways if a same-named table exists
    elsewhere.  Rather than fight that, we exercise the production
    scenario directly: legacy SQL in public, stamp in public.

    The legacy SQL also writes to `schema_migrations` (legacy version
    tracking).  We create that table empty so the INSERTs land
    harmlessly — it's irrelevant to the parity check."""

    @pytest_asyncio.fixture
    async def public_clean(self, conn, monkeypatch):
        """Drop the conversation-storage tables from public before and
        after.  Other tests use throwaway namespaces; only this one
        owns public, so ordering is irrelevant."""
        monkeypatch.setenv("DATABASE_URL", _dsn())
        drop = (
            "DROP TABLE IF EXISTS "
            "public.delegation_records, public.messages, "
            "public.conversations, public.alembic_version, "
            "public.schema_migrations CASCADE"
        )
        await conn.execute(drop)
        yield
        await conn.execute(drop)

    @pytest_asyncio.fixture
    async def legacy_built(self, conn, public_clean):
        """public schema populated by running the raw SQL files,
        exactly as a pre-Alembic deployment would have done."""
        await conn.execute(
            "CREATE TABLE public.schema_migrations ("
            "  version VARCHAR(50) PRIMARY KEY,"
            "  description TEXT,"
            "  applied_at TIMESTAMPTZ DEFAULT now())"
        )
        for path in sorted(LEGACY_MIGRATIONS.glob("*.sql")):
            await conn.execute(path.read_text())
        yield

    async def test_stamp_head_after_raw_sql(self, conn, legacy_built):
        # Insert a row before stamp — proves stamp doesn't truncate
        # (if someone wired stamp to upgrade by mistake, the upgrade's
        # CREATE TABLE would fail anyway, but belt and suspenders).
        await conn.execute(
            "INSERT INTO public.conversations (id, customer_id, channel) "
            "VALUES ('stamp_probe', 'cust_probe', 'chat')"
        )

        # Now stamp.  No schema attribute → public.
        command.stamp(_alembic_cfg(None), "head")

        version = await conn.fetchval(
            "SELECT version_num FROM public.alembic_version"
        )
        assert version == HEAD_REVISION

        # Data survived.
        survivor = await conn.fetchval(
            "SELECT id FROM public.conversations WHERE id = 'stamp_probe'"
        )
        assert survivor == "stamp_probe"

        # All three tables still present and shaped right.
        present = await _tables(conn, "public")
        assert {"conversations", "messages", "delegation_records"} <= present

        # Re-stamp is idempotent — doesn't error, doesn't add a row.
        command.stamp(_alembic_cfg(None), "head")
        n = await conn.fetchval(
            "SELECT count(*) FROM public.alembic_version"
        )
        assert n == 1

    async def test_constraint_names_diverge_after_stamp(
        self, conn, legacy_built, fresh_schema,
    ):
        """A stamped legacy DB and a fresh `upgrade head` DB are
        structurally identical but catalog-distinct.

        Raw SQL: `channel TEXT CHECK (...)` with no constraint name.
        Postgres autogenerates `conversations_channel_check`.

        Alembic: explicit name `ck_conversations_channel` from the
        naming convention in src/database/metadata.py.

        `stamp` does not touch DDL — it only writes the version row.
        So a stamped legacy DB keeps the autogenerated names.  This is
        deliberate: the alternative is rewriting constraint names on a
        live production table, which is a non-zero-risk DDL operation
        for zero functional gain.

        Consequence: `alembic check` (autogenerate diff) on a stamped
        DB will report constraint-name drift.  That's noise, not a
        real problem — but pin both names here so the divergence is
        explicit and nobody "fixes" one side by accident."""
        # Legacy side: stamp the raw-SQL-built public schema.
        command.stamp(_alembic_cfg(None), "head")
        legacy_checks = await _check_constraints(conn, "public", "conversations")

        # Fresh side: upgrade an empty namespace to head.
        command.upgrade(_alembic_cfg(fresh_schema), "head")
        fresh_checks = await _check_constraints(conn, fresh_schema, "conversations")

        # Same number of constraints, same semantics, different names.
        assert len(legacy_checks) == len(fresh_checks) == 1
        (legacy_name,) = legacy_checks
        (fresh_name,) = fresh_checks
        assert legacy_name == "conversations_channel_check"   # PG autogen
        assert fresh_name == "ck_conversations_channel"       # convention
        # The clauses themselves are identical — Postgres normalises
        # both to the same canonical form.
        assert legacy_checks[legacy_name] == fresh_checks[fresh_name]
