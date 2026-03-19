-- Persistent conversation storage.
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS conversations (
    id              UUID            PRIMARY KEY,
    customer_id     TEXT            NOT NULL,
    channel         TEXT            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversations_customer_id
    ON conversations (customer_id);

CREATE TABLE IF NOT EXISTS messages (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID            NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT            NOT NULL,
    content         TEXT            NOT NULL,
    "timestamp"     TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp
    ON messages (conversation_id, "timestamp");
