"""conversation intelligence layer

Reproduces both 002_*.sql files as a single revision — they share the
'002' version slot in the legacy schema_migrations table and were always
applied together.  Splitting them here would mean a database that ran
the raw SQL would be at neither revision; folding them keeps stamp head
honest.

Adds:
  conversations.summary, .tags (TEXT[]), .quality_signals (JSONB)
  + GIN tag index, partial needs-summary index
  messages.specialist_domain
  delegation_records table + three indexes

Revision ID: b2d4f8e1a6c5
Revises: a1c0e7f9b3d2
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "b2d4f8e1a6c5"
down_revision = "a1c0e7f9b3d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── conversations: intelligence columns ─────────────────────────────
    op.add_column("conversations",
                  sa.Column("summary", sa.Text, nullable=True))
    op.add_column("conversations",
                  sa.Column("tags", ARRAY(sa.Text),
                            server_default=sa.text("'{}'"), nullable=True))
    op.add_column("conversations",
                  sa.Column("quality_signals", JSONB,
                            server_default=sa.text("'{}'"), nullable=True))

    # GIN for tags @> / && operators.
    op.create_index(
        "idx_conversations_tags",
        "conversations",
        ["tags"],
        postgresql_using="gin",
    )
    # Partial: summarization sweep finds work via summary IS NULL.
    op.create_index(
        "idx_conversations_needs_summary",
        "conversations",
        ["customer_id", "updated_at"],
        postgresql_where=sa.text("summary IS NULL"),
    )

    # ─── messages: specialist tag ────────────────────────────────────────
    # No index — see 002_message_metadata.sql for the rationale.
    op.add_column("messages",
                  sa.Column("specialist_domain", sa.Text, nullable=True))

    # ─── delegation_records ──────────────────────────────────────────────
    op.create_table(
        "delegation_records",
        sa.Column("id", UUID(as_uuid=False), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", sa.Text, nullable=False),
        sa.Column("customer_id", sa.Text, nullable=False),
        sa.Column("specialist_domain", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("turns", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("confirmation_requested", sa.Boolean, nullable=False,
                  server_default=sa.text("FALSE")),
        sa.Column("confirmation_outcome", sa.Text, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_delegation_records"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"],
            name="fk_delegation_records_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'cancelled')",
            name="ck_delegation_records_status",
        ),
        sa.CheckConstraint(
            "confirmation_outcome IN ('confirmed', 'declined') "
            "OR confirmation_outcome IS NULL",
            name="ck_delegation_records_confirmation_outcome",
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
    op.drop_index("idx_delegation_records_domain_status",
                  table_name="delegation_records")
    op.drop_index("idx_delegation_records_customer_time",
                  table_name="delegation_records")
    op.drop_index("idx_delegation_records_conversation",
                  table_name="delegation_records")
    op.drop_table("delegation_records")

    op.drop_column("messages", "specialist_domain")

    op.drop_index("idx_conversations_needs_summary",
                  table_name="conversations")
    op.drop_index("idx_conversations_tags", table_name="conversations")
    op.drop_column("conversations", "quality_signals")
    op.drop_column("conversations", "tags")
    op.drop_column("conversations", "summary")
