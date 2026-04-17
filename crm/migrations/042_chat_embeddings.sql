-- Migration 042: Verbatim chat embedding + TTL
--
-- Embed each chat_messages row so raw conversation turns are retrievable,
-- not just LLM-distilled facts. Turns > 90 days old with pinned=FALSE and
-- no associated fact reference are pruned in nightly lifecycle. Distilled
-- facts always survive.

BEGIN;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS embedding vector(1024),
    ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_chat_messages_embedding
    ON chat_messages USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

CREATE INDEX IF NOT EXISTS idx_chat_messages_pinned
    ON chat_messages(pinned)
    WHERE pinned = TRUE;

CREATE INDEX IF NOT EXISTS idx_chat_messages_embedded_at
    ON chat_messages(embedded_at);

COMMIT;
