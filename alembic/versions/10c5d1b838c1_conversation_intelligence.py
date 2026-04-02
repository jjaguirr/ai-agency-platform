"""002 — conversation intelligence

Reproduces the union of:
  src/database/migrations/002_conversation_intelligence.sql
  src/database/migrations/002_message_metadata.sql

Both raw files share the '002' label and were always applied together;
they're a single logical revision here.

Adds:
  conversations.summary / .tags / .quality_signals
  messages.specialist_domain
  delegation_records (table)
  GIN + partial indexes for the summarisation sweep and tag filter

Revision ID: 10c5d1b838c1
Revises: 156127bc0bf1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "10c5d1b838c1"
down_revision = "156127bc0bf1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── conversations: intelligence columns ────────────────────────────
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "quality_signals",
            postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=True,
        ),
    )

    # GIN for tags @> / && filtering
    op.create_index(
        "idx_conversations_tags",
        "conversations",
        ["tags"],
        postgresql_using="gin",
    )
    # Partial index for the summarisation sweep — only rows the sweep
    # will ever scan are indexed, so it stays tiny even as the table
    # grows.
    op.create_index(
        "idx_conversations_needs_summary",
        "conversations",
        ["customer_id", "updated_at"],
        postgresql_where=sa.text("summary IS NULL"),
    )

    # ── messages: specialist_domain ─────────────────────────────────────
    op.add_column(
        "messages",
        sa.Column("specialist_domain", sa.Text(), nullable=True),
    )

    # ── delegation_records ──────────────────────────────────────────────
    op.create_table(
        "delegation_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("specialist_domain", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "turns",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "confirmation_requested",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column("confirmation_outcome", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="delegation_records_pkey"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="delegation_records_conversation_id_fkey",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'cancelled')",
            name=op.f("delegation_records_status_check"),
        ),
        sa.CheckConstraint(
            "confirmation_outcome IN ('confirmed', 'declined') "
            "OR confirmation_outcome IS NULL",
            name=op.f("delegation_records_confirmation_outcome_check"),
        ),
    )
    op.create_index(
        "idx_delegation_records_conversation",
        "delegation_records",
        ["conversation_id"],
    )
    op.create_index(
        "idx_delegation_records_customer_time",
        "delegation_records",
        ["customer_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "idx_delegation_records_domain_status",
        "delegation_records",
        ["specialist_domain", "status", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("delegation_records")

    op.drop_column("messages", "specialist_domain")

    op.drop_index("idx_conversations_needs_summary", table_name="conversations")
    op.drop_index("idx_conversations_tags", table_name="conversations")
    op.drop_column("conversations", "quality_signals")
    op.drop_column("conversations", "tags")
    op.drop_column("conversations", "summary")
