-- ════════════════════════════════════════════════════════════════════════════
-- SUPERSEDED by alembic/versions/20260402_a1c0e7f9b3d2_conversations_base.py
--
-- Kept for reference and for the stamp-parity test in
-- tests/integration/test_alembic_migrations.py::TestStampOnLegacyDB.
-- Do not apply manually.  Run `alembic upgrade head` instead.
-- Existing databases that ran this file: run `alembic stamp head` once.
-- ════════════════════════════════════════════════════════════════════════════
--
-- Migration 001: Persistent conversation storage.
--
-- Two tables: conversations (header) and messages (append-only log).
--
-- Design choices worth noting:
--
--   conversation.id is TEXT, not UUID. The API lets callers supply
--   arbitrary conversation_id strings (chat widgets embed session IDs,
--   WhatsApp uses phone numbers). We generate a UUID only when the
--   caller omits one. Forcing UUID here would break every existing
--   client.
--
--   customer_id is TEXT with no FK to customers(id). The customers
--   table keys on UUID; the API layer keys on the JWT claim string
--   (e.g. "cust_abc123"). They are different identifier spaces. This
--   table lives in the API's identifier space. GDPR deletion covers
--   it via PG_VARCHAR_TABLES.
--
--   messages.conversation_id cascades from conversations. Deleting a
--   conversation (via customer deletion) cleans up its messages in
--   one FK-enforced pass — no orphan sweep needed.
--
--   role is constrained to the canonical OpenAI/Anthropic convention
--   ("user"/"assistant"/"system"). The EA's in-memory history uses
--   LangChain's "human"/"ai" — that convention stays in the EA; the
--   persistence layer stores the wire-format names.
--
-- Idempotent: IF NOT EXISTS everywhere so the startup check can
-- re-apply this file safely.

BEGIN;

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT        PRIMARY KEY,
    customer_id TEXT        NOT NULL,
    channel     TEXT        NOT NULL CHECK (channel IN ('phone', 'whatsapp', 'email', 'chat')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- List-conversations query: WHERE customer_id = $1 ORDER BY updated_at DESC
CREATE INDEX IF NOT EXISTS idx_conversations_customer_updated
    ON conversations (customer_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT        NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- History query: WHERE conversation_id = $1 ORDER BY timestamp ASC
CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp
    ON messages (conversation_id, timestamp);

INSERT INTO schema_migrations (version, description)
VALUES ('001', 'conversations + messages persistent storage')
ON CONFLICT (version) DO NOTHING;

COMMIT;
