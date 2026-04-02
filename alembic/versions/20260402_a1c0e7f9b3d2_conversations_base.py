"""conversations + messages base schema

Reproduces src/database/migrations/001_conversations.sql exactly so an
existing database can be `alembic stamp head`'d without re-running DDL.
See that file for the design rationale (TEXT id, no FK to customers,
CASCADE on messages, role naming convention).

Constraint names follow src.database.metadata.NAMING_CONVENTION so a
future autogenerate run produces an empty diff.  Index names are the
hand-picked ones from the raw SQL — they appear in code comments and
shouldn't churn.

Revision ID: a1c0e7f9b3d2
Revises:
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "a1c0e7f9b3d2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.CheckConstraint(
            "channel IN ('phone', 'whatsapp', 'email', 'chat')",
            name="ck_conversations_channel",
        ),
    )
    # WHERE customer_id = $1 ORDER BY updated_at DESC
    op.create_index(
        "idx_conversations_customer_updated",
        "conversations",
        ["customer_id", sa.text("updated_at DESC")],
    )

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=False), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_role",
        ),
    )
    # WHERE conversation_id = $1 ORDER BY timestamp ASC
    op.create_index(
        "idx_messages_conversation_timestamp",
        "messages",
        ["conversation_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("idx_messages_conversation_timestamp", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_conversations_customer_updated",
                  table_name="conversations")
    op.drop_table("conversations")
