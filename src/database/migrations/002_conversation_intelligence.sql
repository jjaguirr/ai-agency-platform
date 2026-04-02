-- ════════════════════════════════════════════════════════════════════════════
-- SUPERSEDED by alembic/versions/20260402_b2d4f8e1a6c5_conversation_intelligence.py
--
-- Kept for reference and for the stamp-parity test in
-- tests/integration/test_alembic_migrations.py::TestStampOnLegacyDB.
-- Do not apply manually.  Run `alembic upgrade head` instead.
-- Existing databases that ran this file: run `alembic stamp head` once.
-- ════════════════════════════════════════════════════════════════════════════
--
-- Migration 002: Conversation intelligence layer.
--
-- Extends conversations with summary, topic tags, and quality signals.
-- Adds delegation_records for specialist performance tracking.
--
-- Idempotent: IF NOT EXISTS / ADD COLUMN IF NOT EXISTS everywhere.

BEGIN;

-- ─── Extend conversations ────────────────────────────────────────────────
-- summary: LLM-generated, NULL until the background sweep processes it.
-- tags: specialist domains touched (finance, scheduling, etc.), or 'general'.
-- quality_signals: {escalation, unresolved, long} — heuristic flags.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conversations' AND column_name = 'summary'
    ) THEN
        ALTER TABLE conversations ADD COLUMN summary TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conversations' AND column_name = 'tags'
    ) THEN
        ALTER TABLE conversations ADD COLUMN tags TEXT[] DEFAULT '{}';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conversations' AND column_name = 'quality_signals'
    ) THEN
        ALTER TABLE conversations ADD COLUMN quality_signals JSONB DEFAULT '{}';
    END IF;
END $$;

-- GIN index for tag-based filtering (supports @> and && operators).
CREATE INDEX IF NOT EXISTS idx_conversations_tags
    ON conversations USING GIN (tags);

-- Partial index for the summarization sweep: find conversations needing a summary.
CREATE INDEX IF NOT EXISTS idx_conversations_needs_summary
    ON conversations (customer_id, updated_at)
    WHERE summary IS NULL;

-- ─── Delegation records ──────────────────────────────────────────────────
-- One row per delegation lifecycle. Created on delegation start,
-- updated on completion/failure/cancellation.

CREATE TABLE IF NOT EXISTS delegation_records (
    id                     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id        TEXT         NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    customer_id            TEXT         NOT NULL,
    specialist_domain      TEXT         NOT NULL,
    status                 TEXT         NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'cancelled')),
    turns                  INT          NOT NULL DEFAULT 1,
    confirmation_requested BOOLEAN      NOT NULL DEFAULT FALSE,
    confirmation_outcome   TEXT         CHECK (confirmation_outcome IN ('confirmed', 'declined') OR confirmation_outcome IS NULL),
    started_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at           TIMESTAMPTZ,
    error_message          TEXT
);

CREATE INDEX IF NOT EXISTS idx_delegation_records_conversation
    ON delegation_records (conversation_id);

CREATE INDEX IF NOT EXISTS idx_delegation_records_customer_time
    ON delegation_records (customer_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_delegation_records_domain_status
    ON delegation_records (specialist_domain, status, started_at);

INSERT INTO schema_migrations (version, description)
VALUES ('002', 'conversation intelligence: summary, tags, quality signals, delegation records')
ON CONFLICT (version) DO NOTHING;

COMMIT;
