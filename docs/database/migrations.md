# Database migrations

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/).
The API will **refuse to start** if the database is not at the current
head revision — `ConversationRepository.check_schema()` compares
`alembic_version.version_num` against the on-disk head during the
FastAPI lifespan hook and raises with the exact command to run if they
differ. Migrations are never applied automatically; running them is an
operator decision.

## Where things live

| Path | Purpose |
|---|---|
| `alembic.ini` | CLI config. `script_location` and logging only — no DB URL baked in. |
| `alembic/env.py` | Async (asyncpg) runner. Resolves the target URL at runtime (see below). |
| `alembic/versions/` | Revision scripts. One file per schema change. |
| `src/database/migrations/__init__.py` | `head_revision()`, `current_revision()`, `alembic_config()`, `target_metadata` — shared by `env.py` and the startup check. |
| `src/database/migrations/*.sql` | **Superseded.** Legacy raw SQL kept for reference and integration-test fixtures. Do not extend. |

## URL resolution

`env.py` picks the database URL in this order (first wins):

1. `sqlalchemy.url` set on the `Config` object — used by tests and
   programmatic callers.
2. `$DATABASE_URL`
3. `DatabaseConfig.from_env()` — the `POSTGRES_HOST` / `POSTGRES_PORT` /
   `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` variables the
   API itself uses.

A plain `postgresql://` URL is automatically rewritten to
`postgresql+asyncpg://` for the async engine.

## Fresh deploy

```bash
alembic upgrade head
```

Run from the repo root. Creates every table, index and constraint, and
records the head revision in `alembic_version`. Idempotent — re-running
on an up-to-date DB is a no-op.

## Adopting an existing database

Databases built from the legacy raw SQL files have the full schema but
no `alembic_version` table, so the API rejects them. Adopt without
re-running DDL:

```bash
alembic stamp head
```

This only writes the version row. The bootstrap revisions
(`156127bc0bf1`, `10c5d1b838c1`) reproduce the raw SQL **including
Postgres' default constraint names**, so a stamped DB and a
freshly-upgraded DB are interchangeable — verified by
`tests/integration/test_alembic_migrations.py::test_schema_parity_with_raw_sql`.

## Upgrading after a pull

```bash
alembic current          # what the DB is at
alembic history          # what revisions exist
alembic upgrade head     # apply anything pending
```

## Rolling back

```bash
alembic downgrade -1     # one step
alembic downgrade <rev>  # to a specific revision
alembic downgrade base   # everything (drops all domain tables)
```

Every revision **must** have a working `downgrade()`. The round-trip
integration test (`test_upgrade_downgrade_upgrade_round_trip`) enforces
this.

## Adding a migration

```bash
alembic revision -m "short imperative description"
```

This writes a stub to `alembic/versions/<rev>_<slug>.py`. Fill in
`upgrade()` and `downgrade()` by hand — the project uses raw asyncpg,
not the SQLAlchemy ORM, so there are no declarative models for
`--autogenerate` to diff against yet.

Guidelines:

- **Let the naming convention name your constraints.** Don't pass
  `name=` to `PrimaryKeyConstraint` / `ForeignKeyConstraint` /
  `CheckConstraint`; `target_metadata.naming_convention` (in
  `src/database/migrations/__init__.py`) produces stable, droppable
  names. The two bootstrap revisions are the *only* exception — they
  use `op.f()` to match the PG-default names the legacy SQL produced.
- **`downgrade()` must fully reverse `upgrade()`.** Drop in reverse
  creation order.
- **One concern per revision.** Don't bundle an index with an unrelated
  column add.
- **Preview before applying:** `alembic upgrade head --sql` prints the
  DDL without touching a database.

## Running the migration tests

Integration tests create and drop throwaway databases, so they need a
Postgres with `CREATEDB` privilege:

```bash
docker run -d --rm --name alembic-test-pg \
  -e POSTGRES_USER=mcphub -e POSTGRES_PASSWORD=mcphub_password \
  -e POSTGRES_DB=mcphub -p 55432:5432 postgres:16-alpine

POSTGRES_PORT=55432 uv run pytest tests/integration/test_alembic_migrations.py -v
```

Unit tests need no database:

```bash
uv run pytest tests/unit/database/test_alembic_check.py -q
```

## Troubleshooting

**`SchemaNotReadyError: Database has not been initialised with Alembic`**
No `alembic_version` table. Fresh DB → `alembic upgrade head`. Legacy
raw-SQL DB → `alembic stamp head`.

**`SchemaNotReadyError: Database is at revision 'X' but the code expects 'Y'`**
Pending migrations after a deploy. Run `alembic upgrade head`.

**`RuntimeError: alembic versions/ has N heads`**
Two revision files share a `down_revision` (usually a merge artefact).
`alembic heads` shows them; either `alembic merge` or fix the
`down_revision` of one to chain after the other.
