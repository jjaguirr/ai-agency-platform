-- ════════════════════════════════════════════════════════════════════════════
-- SUPERSEDED by alembic/versions/20260402_b2d4f8e1a6c5_conversation_intelligence.py
--
-- Folded into the same Alembic revision as 002_conversation_intelligence.sql
-- (both shared the '002' version slot in schema_migrations).  Kept for
-- reference and for the stamp-parity test.  Do not apply manually.
-- ════════════════════════════════════════════════════════════════════════════
--
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
