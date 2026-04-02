"""
Alembic environment — async (asyncpg) edition.

The repo doesn't use the SQLAlchemy ORM; queries go through raw asyncpg
in ConversationRepository. Alembic is here purely as a migration runner
and version tracker, so target_metadata stays empty (no autogenerate
source yet). The MetaData *does* carry a constraint naming convention
so that the day someone adds declarative models, autogenerate emits
droppable constraint names from the start.

URL resolution order (first wins):
  1. config.get_main_option("sqlalchemy.url") if it's a real URL —
     tests set this via cfg.set_main_option(...)
  2. $DATABASE_URL
  3. DatabaseConfig.from_env() — the same POSTGRES_* fallback the API
     uses, so `alembic upgrade head` against a docker-compose stack
     works with no extra env.
"""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from src.database.migrations import target_metadata

config = context.config

# Wire alembic's [logger_*] sections into Python logging — but only when
# invoked via the CLI (config_file_name set). Programmatic callers may
# build a Config() with no ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    # 1. explicit override on the Config (tests, programmatic callers)
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url and ini_url != "driver://":
        url = ini_url
    # 2. $DATABASE_URL
    elif env_url := os.getenv("DATABASE_URL"):
        url = env_url
    # 3. POSTGRES_* fallback (matches src/api/app.py)
    else:
        from src.utils.config import DatabaseConfig
        url = DatabaseConfig.from_env().url

    # asyncpg driver required for create_async_engine. Accept either
    # plain postgresql:// or an already-qualified URL.
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


def run_migrations_offline() -> None:
    """--sql mode: emit SQL to stdout, no DB connection."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # compare server defaults + types when autogenerate is eventually used
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_async_engine(_resolve_url(), poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
