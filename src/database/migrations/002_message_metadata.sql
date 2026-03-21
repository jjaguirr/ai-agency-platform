-- Migration 002: specialist_domain on messages
--
-- Tags assistant messages with which specialist handled the turn, so the
-- dashboard can show "this conversation touched finance + scheduling"
-- without replaying the whole message history.
--
-- NULL for user messages and general-assistance replies — most rows.
-- No index: low cardinality, always read via the per-conversation
-- LATERAL join in list_conversations_enriched which already filters on
-- conversation_id (covered by idx_messages_conversation). If the
-- aggregation ever profiles hot, add a partial index on
-- (conversation_id) WHERE specialist_domain IS NOT NULL.

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS specialist_domain TEXT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('002', 'specialist_domain on messages')
ON CONFLICT (version) DO NOTHING;
