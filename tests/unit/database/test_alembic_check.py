"""
Alembic head check — startup gate replacing the table-existence check.

The old check_schema() asked "do the tables exist?" — which can't tell
you "tables exist but are one migration behind".  The new check asks
"is the database at the head revision?".  Same SchemaNotReadyError on
failure, but with an `alembic upgrade head` hint instead of a path to
a SQL file.

Mocked at the asyncpg layer.  The Alembic ScriptDirectory side reads
real revision files from disk — that's cheap and means we don't
hardcode the head revision id in tests.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from src.database.conversation_repository import SchemaNotReadyError


pytestmark = pytest.mark.unit

# Walk the real chain once.  Tests use BASE_REVISION as the
# canonical "valid revision that isn't head" — it's guaranteed to
# exist and guaranteed to be behind, regardless of how many
# migrations get added later.
_script = ScriptDirectory.from_config(
    Config(str(Path(__file__).parents[3] / "alembic.ini"))
)
BASE_REVISION = next(
    r.revision for r in _script.walk_revisions() if r.down_revision is None
)


def _mock_pool(version_query_result):
    """asyncpg pool whose acquire().fetchval() returns the supplied
    revision (or raises).  Just enough surface for the head check.

    The conn mock is attached as `pool._conn` so tests can assert on
    the exact query issued — without that, the implementation could
    swap to `SELECT 1` and the at-head test would still pass."""
    conn = MagicMock()
    if isinstance(version_query_result, Exception):
        conn.fetchval = AsyncMock(side_effect=version_query_result)
    else:
        conn.fetchval = AsyncMock(return_value=version_query_result)

    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    pool._conn = conn
    return pool


class TestGetHeadRevision:
    """The head revision must be readable from the alembic/ directory
    without a database connection — it's a property of the codebase,
    not of the database state."""

    def test_returns_current_head(self):
        from src.database.alembic_check import get_head_revision
        head = get_head_revision()
        # Don't pin the literal id (couples the test to migration
        # filenames) — assert it agrees with an independent read of
        # the same directory.  If the implementation cached a stale
        # value or read the wrong path, this catches it.
        assert head == _script.get_heads()[0]
        # And it's not the base — head and base are distinct unless
        # the chain is one revision long, which it isn't.
        assert head != BASE_REVISION


class TestCheckAlembicHead:
    async def test_passes_when_db_at_head(self):
        from src.database.alembic_check import (
            check_alembic_head, get_head_revision,
        )
        pool = _mock_pool(get_head_revision())
        # Should return without raising.
        await check_alembic_head(pool)
        # And it actually queried the version table — not, say,
        # short-circuited on a cached value.
        pool._conn.fetchval.assert_awaited_once_with(
            "SELECT version_num FROM alembic_version"
        )

    async def test_raises_when_db_behind_head(self):
        from src.database.alembic_check import check_alembic_head
        # Some old revision that exists in the chain but isn't head.
        # Use the base revision id — guaranteed to exist and not be head.
        pool = _mock_pool(BASE_REVISION)
        with pytest.raises(SchemaNotReadyError) as exc_info:
            await check_alembic_head(pool)
        msg = str(exc_info.value)
        assert "alembic upgrade head" in msg
        assert BASE_REVISION in msg

    async def test_raises_when_alembic_version_missing(self):
        """Fresh database, never migrated — alembic_version doesn't
        exist.  asyncpg raises UndefinedTableError; the check should
        catch it and translate to SchemaNotReadyError with the same
        upgrade hint."""
        import asyncpg
        from src.database.alembic_check import check_alembic_head
        pool = _mock_pool(
            asyncpg.UndefinedTableError(
                'relation "alembic_version" does not exist'
            )
        )
        with pytest.raises(SchemaNotReadyError) as exc_info:
            await check_alembic_head(pool)
        msg = str(exc_info.value)
        assert "alembic upgrade head" in msg
        # Should mention the table is missing — distinguishes "never
        # migrated" from "migrated but stale" in the log.
        assert "alembic_version" in msg.lower()

    async def test_raises_when_alembic_version_empty(self):
        """alembic_version exists but has no rows — `alembic stamp base`
        or a botched manual cleanup.  fetchval returns None."""
        from src.database.alembic_check import check_alembic_head
        pool = _mock_pool(None)
        with pytest.raises(SchemaNotReadyError) as exc_info:
            await check_alembic_head(pool)
        assert "alembic upgrade head" in str(exc_info.value)

    async def test_raises_on_unknown_revision(self):
        """Database claims a revision that isn't in the local chain —
        somebody downgraded the code, or two branches are fighting.
        Don't auto-migrate; surface it loudly."""
        from src.database.alembic_check import check_alembic_head
        pool = _mock_pool("deadbeef9999")
        with pytest.raises(SchemaNotReadyError) as exc_info:
            await check_alembic_head(pool)
        msg = str(exc_info.value)
        assert "deadbeef9999" in msg
        # The hint here is *not* "upgrade head" — that would lie.  The
        # operator needs to investigate.
        assert "not found" in msg
        assert "alembic upgrade head" not in msg


class TestCheckSchemaDelegates:
    """ConversationRepository.check_schema must call the Alembic head
    check, not the old table-existence loop.  Same exception type so
    the lifespan hook in src/api/app.py keeps working unchanged."""

    async def test_check_schema_passes_when_at_head(self):
        from src.database.alembic_check import get_head_revision
        from src.database.conversation_repository import ConversationRepository
        repo = ConversationRepository(_mock_pool(get_head_revision()))
        await repo.check_schema()

    async def test_check_schema_raises_schemanotreadyerror_when_behind(self):
        from src.database.conversation_repository import ConversationRepository
        repo = ConversationRepository(_mock_pool(BASE_REVISION))
        with pytest.raises(SchemaNotReadyError) as exc_info:
            await repo.check_schema()
        # New hint, not the old SQL-file path.
        assert "alembic upgrade head" in str(exc_info.value)
        assert "001_conversations.sql" not in str(exc_info.value)
