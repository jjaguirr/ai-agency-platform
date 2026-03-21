-- Migration 002: Conversation intelligence layer.
--
-- Two pieces:
--
--   1. Columns on `conversations` for post-hoc derived metadata:
--      summary (LLM-generated one-liner), topics (from delegation
--      domains), quality_flags (heuristic signals). All nullable /
--      empty-default — a conversation gets these only after the
--      background sweep has processed it.
--
--   2. A `delegations` table. One row per completed delegation
--      (where "completed" means the specialist reached a terminal
--      state — COMPLETED, FAILED, or cancelled by the customer
--      declining confirmation). Mid-flight clarification turns
--      don't write a row; only the terminal turn does, carrying
--      the accumulated turn count.
--
--      customer_id is denormalised onto the row even though it's
--      reachable via conversation_id → conversations.customer_id.
--      Analytics queries filter and group by customer_id; the
--      join is cheap but the denorm makes the tenant-isolation
--      predicate local to one table, which matches how every
--      other query in the codebase works.
--
-- Idempotent like 001.

BEGIN;

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS summary       TEXT,
    ADD COLUMN IF NOT EXISTS topics        TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS quality_flags TEXT[] NOT NULL DEFAULT '{}';

-- The sweep query: WHERE summary IS NULL AND updated_at < cutoff.
-- Partial index so processed conversations fall out of it.
CREATE INDEX IF NOT EXISTS idx_conversations_unsummarized
    ON conversations (updated_at)
    WHERE summary IS NULL;

-- Topic filter on the list endpoint: WHERE customer_id = $1 AND $2 = ANY(topics)
CREATE INDEX IF NOT EXISTS idx_conversations_topics
    ON conversations USING GIN (topics);

CREATE TABLE IF NOT EXISTS delegations (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id        TEXT        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    customer_id            TEXT        NOT NULL,
    domain                 TEXT        NOT NULL,
    status                 TEXT        NOT NULL CHECK (status IN ('completed', 'failed', 'cancelled')),
    turns                  INTEGER     NOT NULL CHECK (turns >= 1),
    confirmation_requested BOOLEAN     NOT NULL DEFAULT FALSE,
    -- NULL when confirmation_requested is FALSE. 'confirmed' | 'declined' otherwise.
    confirmation_outcome   TEXT        CHECK (confirmation_outcome IN ('confirmed', 'declined')),
    started_at             TIMESTAMPTZ NOT NULL,
    ended_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Analytics: WHERE customer_id = $1 AND ended_at BETWEEN $2 AND $3 GROUP BY domain
CREATE INDEX IF NOT EXISTS idx_delegations_customer_ended
    ON delegations (customer_id, ended_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('002', 'conversation intelligence: summary/topics/quality columns + delegations table')
ON CONFLICT (version) DO NOTHING;

COMMIT;
