-- Memory v4 schema consolidation
-- Drops legacy short/long-term tables (frozen since Feb 3, 2026),
-- adds tsv column for BM25, switches to HNSW index, drops dead function.
-- Idempotent — safe to run on both fresh and existing databases.
BEGIN;

-- Drop legacy tier tables (data was frozen, never queried)
DROP TABLE IF EXISTS short_term_memory CASCADE;
DROP TABLE IF EXISTS long_term_memory CASCADE;

-- Add tsvector column for BM25 keyword search
ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('english', fact_text)) STORED;
CREATE INDEX IF NOT EXISTS idx_facts_tsv ON memory_facts USING GIN(tsv);

-- Replace IVFFlat with HNSW (better recall, no training data needed)
DROP INDEX IF EXISTS idx_facts_embedding;
CREATE INDEX IF NOT EXISTS idx_facts_embedding ON memory_facts
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=200);

-- Drop legacy unified search function (referenced dropped tables)
DROP FUNCTION IF EXISTS search_memories(vector, integer, boolean, boolean);

COMMIT;
