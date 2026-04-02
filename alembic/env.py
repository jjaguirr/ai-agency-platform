"""
Alembic environment — async (asyncpg) edition.

DSN resolution mirrors the integration tests' `_dsn()` so the same env
vars drive both: `DATABASE_URL` wins; otherwise the POSTGRES_* family
that DatabaseConfig.from_env() reads.  We coerce whatever we get into
the asyncpg dialect because the API runs on asyncpg and we want
migrations exercising the same driver path.

target_metadata stays None — migrations are hand-written op.* calls,
not autogenerate-from-models.  The naming convention defined in
src.database.metadata is still load-bearing for the day someone adds a
declarative model and runs autogenerate; the constraints in our
migrations name themselves explicitly to match it.
"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No declarative models — migrations are explicit.  Autogenerate is
# inert until somebody points this at a real MetaData.
target_metadata = None


def _resolve_url() -> str:
    """DATABASE_URL wins; fall back to the POSTGRES_* family the rest
    of the codebase uses (DatabaseConfig.from_env, integration _dsn)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "mcphub")
        user = os.getenv("POSTGRES_USER", "mcphub")
        pw = os.getenv("POSTGRES_PASSWORD", "mcphub_password")
        url = f"postgresql://{user}:{pw}@{host}:{port}/{db}"
    # Force asyncpg.  postgres:// → postgresql+asyncpg://, and a bare
    # postgresql:// (psycopg2 default) likewise.  If someone hands us
    # an explicit +psycopg dialect we leave it — they presumably know.
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


config.set_main_option("sqlalchemy.url", _resolve_url())


def run_migrations_offline() -> None:
    """--sql mode — emit DDL without a live connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    # Tests pass a throwaway-schema name via cfg.attributes['schema']
    # so each test gets a hermetic namespace without a fresh database.
    # Production omits it and migrations land in `public`.
    # version_table_schema places alembic_version in the same namespace.
    schema = config.attributes.get("schema")
    if schema is not None:
        connection.exec_driver_sql(f'SET search_path TO "{schema}"')
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=schema,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # SQLAlchemy 2.0 autobegins on first execute and rolls back on
    # close unless told otherwise.  Alembic's context.begin_transaction
    # nests inside that — its commit is a savepoint release, not a
    # real commit.  begin() makes the outer commit-on-exit instead.
    async with connectable.begin() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    # alembic.command.* are synchronous entrypoints.  When invoked
    # from an async test (pytest-asyncio), there's already a loop and
    # asyncio.run() refuses to nest.  Detect that and run the
    # migration in a fresh thread with its own loop.  CLI use takes
    # the cheap path.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_async_migrations())
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(asyncio.run, run_async_migrations()).result()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
