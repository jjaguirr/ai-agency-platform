"""001 — initial schema: conversations + messages

Reproduces src/database/migrations/001_conversations.sql exactly so an
existing database built from that file can be `alembic stamp`ed to this
revision without drift.

Constraint names match Postgres' auto-generated defaults from the raw
SQL ({table}_pkey, {table}_{col}_fkey, {table}_{col}_check) rather than
the project's NAMING_CONVENTION. That convention is for *future*
migrations; here we're matching an already-deployed schema.

Revision ID: 156127bc0bf1
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "156127bc0bf1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="conversations_pkey"),
        sa.CheckConstraint(
            "channel IN ('phone', 'whatsapp', 'email', 'chat')",
            # op.f(): name is final — don't re-apply NAMING_CONVENTION.
            # We're matching the PG-default name the raw SQL produced.
            name=op.f("conversations_channel_check"),
        ),
    )
    # (customer_id, updated_at DESC) — DESC matters for the
    # newest-first list query's index-only scan direction.
    op.create_index(
        "idx_conversations_customer_updated",
        "conversations",
        ["customer_id", sa.text("updated_at DESC")],
    )

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "timestamp",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="messages_pkey"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="messages_conversation_id_fkey",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name=op.f("messages_role_check"),
        ),
    )
    op.create_index(
        "idx_messages_conversation_timestamp",
        "messages",
        ["conversation_id", "timestamp"],
    )


def downgrade() -> None:
    # Index drops are implicit in DROP TABLE; FK CASCADE-deletes nothing
    # because we drop child first.
    op.drop_table("messages")
    op.drop_table("conversations")
