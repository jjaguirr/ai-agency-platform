"""
Alembic revision check for API startup.

Replaces the old table-existence check, which couldn't tell "schema
exists but is one migration behind" from "schema is current".  Now we
ask Alembic: is the database at head?  If not, log the exact command
to fix it and refuse to start — same fail-fast contract, better
diagnostics.

Two halves:
  get_head_revision() — reads alembic/versions/ from disk.  No DB.
                        Property of the *code*, not the database.
  check_alembic_head() — reads alembic_version from the DB and
                         compares.  Raises SchemaNotReadyError on any
                         mismatch.

The check is deliberately strict: behind, ahead, unknown revision,
missing table, empty table — all refuse.  Auto-migrating in the
startup path would mean a rollback-and-redeploy could silently
downgrade the schema.  An operator runs `alembic upgrade head` once,
deliberately, with their eyes open.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import asyncpg
from alembic.config import Config
from alembic.script import ScriptDirectory

from .conversation_repository import SchemaNotReadyError

# alembic.ini lives at the repo root, two parents up from this file.
# Resolved once; ScriptDirectory reads it lazily.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


@lru_cache(maxsize=1)
def _script_directory() -> ScriptDirectory:
    cfg = Config(str(_ALEMBIC_INI))
    return ScriptDirectory.from_config(cfg)


def get_head_revision() -> str:
    """The single head revision id from alembic/versions/.  Raises if
    the chain has multiple heads (a merge commit went wrong) — that's
    a code bug, not a runtime concern, so we don't try to handle it."""
    heads = _script_directory().get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f"Expected exactly one Alembic head, found {len(heads)}: {heads!r}. "
            f"Run `alembic merge heads` to resolve."
        )
    return heads[0]


def _known_revisions() -> set[str]:
    return {r.revision for r in _script_directory().walk_revisions()}


async def check_alembic_head(pool: asyncpg.Pool) -> None:
    """Assert the database is at the head revision.  Raises
    SchemaNotReadyError otherwise — the lifespan hook in src/api/app.py
    catches that and aborts startup."""
    head = get_head_revision()

    try:
        async with pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT version_num FROM alembic_version"
            )
    except asyncpg.UndefinedTableError:
        raise SchemaNotReadyError(
            "Database has no alembic_version table — migrations have "
            "never been applied. Run `alembic upgrade head` before "
            "starting the API."
        )

    if current is None:
        raise SchemaNotReadyError(
            "alembic_version table is empty. "
            "Run `alembic upgrade head` before starting the API."
        )

    if current == head:
        return

    if current not in _known_revisions():
        # Database is on a revision this codebase doesn't know about —
        # either the code was downgraded or two branches diverged.
        # Don't suggest `upgrade head`; that would lie.
        raise SchemaNotReadyError(
            f"Database is at revision {current!r}, which is not found "
            f"in this codebase's migration chain (head: {head!r}). "
            f"The deployed code may be older than the database schema."
        )

    # Known revision, but not head — straightforward "you're behind".
    raise SchemaNotReadyError(
        f"Database is at revision {current!r}; head is {head!r}. "
        f"Run `alembic upgrade head` before starting the API."
    )
