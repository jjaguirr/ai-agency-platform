-- Add JSONB metadata column to messages for specialist domain tagging.
-- Nullable, no default — existing rows unaffected.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS metadata JSONB;
