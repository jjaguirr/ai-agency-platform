"""
Unit tests for the Alembic-backed schema check.

Covers two pieces:

  src.database.migrations.head_revision()
      Reads the on-disk migration scripts and returns the head
      revision id. Pure filesystem — no DB.

  ConversationRepository.check_schema()
      Compares the live DB's alembic_version against head_revision().
      Raises SchemaNotReadyError when they diverge, with an actionable
      `alembic upgrade head` hint. The old behaviour (table-existence
      probe) is gone — these tests pin the new contract.

The DB side is exercised with a fake asyncpg pool: check_schema() only
issues one fetchval against alembic_version, so a MagicMock is enough.
Real-Postgres coverage lives in tests/integration/test_alembic_migrations.py.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.conversation_repository import (
    ConversationRepository,
    SchemaNotReadyError,
)


# ───────────────────────── head_revision ────────────────────────────────


def test_head_revision_returns_string():
    """head_revision() resolves the script directory at repo root and
    returns the single head as a non-empty string. If this fails the
    alembic/ directory is missing or has multiple heads."""
    from src.database.migrations import head_revision

    rev = head_revision()
    assert isinstance(rev, str)
    assert rev  # non-empty


def test_migration_chain_is_linear():
    """The chain is base → … → head with no branches or gaps. Pins
    the structural invariant head_revision() relies on (single head)
    without hard-coding a revision count — adding a migration must
    not require touching this test."""
    from src.database.migrations import alembic_config, head_revision
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config())
    # walk_revisions yields head→base; reverse for base→head.
    revs = list(reversed(list(script.walk_revisions())))
    ids = [r.revision for r in revs]

    assert len(revs) >= 2, f"expected at least the bootstrap pair, got {ids}"
    assert revs[0].down_revision is None, (
        f"first revision {ids[0]} is not rooted at base"
    )
    # Each revision's down_revision must be the previous revision —
    # i.e. a straight line, no merges, no orphans.
    for prev, cur in zip(revs, revs[1:]):
        assert cur.down_revision == prev.revision, (
            f"chain broken: {cur.revision}.down_revision="
            f"{cur.down_revision!r}, expected {prev.revision!r}"
        )
    assert revs[-1].revision == head_revision()


def test_naming_convention_present_on_metadata():
    """env.py must attach a constraint naming convention so future
    autogenerate emits stable, droppable constraint names."""
    from src.database.migrations import target_metadata

    conv = target_metadata.naming_convention
    # the keys alembic actually consults
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in conv, f"naming_convention missing {key!r}"


# ───────────────────── check_schema (mocked pool) ───────────────────────


def _fake_pool(fetchval_result=None, fetchval_exc=None):
    """Minimal asyncpg.Pool stand-in: pool.acquire() is an async
    context manager yielding a conn whose .fetchval is controllable."""
    conn = MagicMock()
    if fetchval_exc is not None:
        conn.fetchval = AsyncMock(side_effect=fetchval_exc)
    else:
        conn.fetchval = AsyncMock(return_value=fetchval_result)

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = _acquire
    return pool, conn


async def test_check_schema_passes_at_head():
    """When alembic_version holds the head revision, check_schema()
    returns without raising."""
    from src.database.migrations import head_revision

    pool, conn = _fake_pool(fetchval_result=head_revision())
    repo = ConversationRepository(pool)
    await repo.check_schema()  # no raise

    # It must have queried alembic_version, not information_schema.
    sql = conn.fetchval.await_args.args[0].lower()
    assert "alembic_version" in sql


async def test_check_schema_raises_when_no_version_table():
    """Fresh DB with no alembic_version table → SchemaNotReadyError
    that tells the operator exactly what to run."""
    import asyncpg

    pool, _ = _fake_pool(fetchval_exc=asyncpg.UndefinedTableError("nope"))
    repo = ConversationRepository(pool)

    with pytest.raises(SchemaNotReadyError) as exc:
        await repo.check_schema()
    msg = str(exc.value)
    assert "alembic upgrade head" in msg
    assert "not been initialised" in msg or "no alembic" in msg.lower()


async def test_check_schema_raises_when_behind():
    """alembic_version exists but holds a stale revision → error names
    both current and expected, plus the upgrade command."""
    pool, _ = _fake_pool(fetchval_result="deadbeef0000")
    repo = ConversationRepository(pool)

    with pytest.raises(SchemaNotReadyError) as exc:
        await repo.check_schema()
    msg = str(exc.value)
    assert "deadbeef0000" in msg
    assert "alembic upgrade head" in msg


async def test_check_schema_raises_when_version_null():
    """An empty alembic_version table (stamped to base, or never
    upgraded) returns NULL from fetchval — treat as not-ready."""
    pool, _ = _fake_pool(fetchval_result=None)
    repo = ConversationRepository(pool)

    with pytest.raises(SchemaNotReadyError):
        await repo.check_schema()
