"""
SQLAlchemy MetaData with a constraint naming convention.

We don't use the SQLAlchemy ORM — Postgres access is raw asyncpg
(see ConversationRepository).  This module exists solely so Alembic
autogenerate has a deterministic naming scheme the day someone adds a
declarative model.  Until then, hand-written migrations name their
constraints explicitly using the same templates so a future
autogenerate diff comes up empty rather than wanting to rename
everything.

The convention follows the pattern Alembic's docs recommend, with one
deviation: index names are *not* templated.  The existing raw-SQL
indexes have hand-picked names (idx_conversations_customer_updated,
etc.) and those names appear in code comments and in people's heads.
Renaming them to satisfy a template buys nothing.  Migrations supply
index names explicitly.
"""
from sqlalchemy import MetaData

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
