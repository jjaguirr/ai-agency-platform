"""
Alembic glue used by both env.py and the API's startup check.

Lives under src/ (not in the alembic/ tree) because the running app
needs head_revision() at startup and src/ is the only package that's
guaranteed to be on sys.path / installed in the wheel. env.py imports
back into here so there's a single source of truth for the metadata
and config location.

This package *also* still contains the legacy raw .sql files. Those
are superseded — see the header in each file — but kept so existing
integration-test fixtures and any prod DB that hasn't been stamped yet
have a reference for what "the schema before alembic" looked like.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import asyncpg
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData

# Repo root = three parents up from this file
#   (src/database/migrations/__init__.py → src/database → src → root)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"

# Naming convention for future autogenerate. The hand-written 001/002
# migrations name constraints explicitly to match what the raw SQL
# produced (Postgres defaults), so existing DBs and fresh alembic DBs
# are bit-for-bit identical and `stamp head` is safe. New migrations
# should let SQLAlchemy derive names from this convention instead.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: Empty for now — the repo uses raw asyncpg, not ORM models. env.py
#: still passes this to context.configure() so autogenerate has a
#: convention to work with the day declarative models appear.
target_metadata = MetaData(naming_convention=NAMING_CONVENTION)


def alembic_config() -> Config:
    """A Config pointed at the repo-root alembic.ini. Callers that need
    a different database override sqlalchemy.url on the returned object
    (or set $DATABASE_URL) before handing it to alembic.command.*."""
    return Config(str(_ALEMBIC_INI))


def head_revision() -> str:
    """The single head of the migration chain. Raises if the chain has
    diverged into multiple heads — that's a bug in the versions/ dir,
    not something the API should try to recover from."""
    script = ScriptDirectory.from_config(alembic_config())
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f"alembic versions/ has {len(heads)} heads ({heads}); "
            f"expected exactly one. Merge or delete the stray revision."
        )
    return heads[0]


async def current_revision(conn: asyncpg.Connection) -> Optional[str]:
    """Read the live revision from alembic_version. Returns None if the
    table doesn't exist (never migrated/stamped) or is empty (stamped
    to base)."""
    try:
        return await conn.fetchval("SELECT version_num FROM alembic_version")
    except asyncpg.UndefinedTableError:
        return None


__all__ = [
    "NAMING_CONVENTION",
    "alembic_config",
    "current_revision",
    "head_revision",
    "target_metadata",
]
