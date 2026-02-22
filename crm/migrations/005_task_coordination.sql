-- Task Coordination: Agent-to-agent task routing columns
-- Database: robothor_memory
-- Run: psql robothor_memory -f 005_task_coordination.sql
--
-- All columns have defaults — zero downtime, backward-compatible.
-- Agents are TEXT (not UUID) because agents aren't CRM people.

BEGIN;

-- ─── New columns ──────────────────────────────────────────────────────────

ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS created_by_agent TEXT;
ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS assigned_to_agent TEXT;
ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'normal';
ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';
ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS parent_task_id UUID REFERENCES crm_tasks(id);
ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS resolution TEXT;

-- ─── Indexes (partial — only non-deleted rows) ───────────────────────────

CREATE INDEX IF NOT EXISTS idx_crm_tasks_assigned_to_agent
    ON crm_tasks (assigned_to_agent)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_tasks_created_by_agent
    ON crm_tasks (created_by_agent)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_tasks_priority
    ON crm_tasks (priority)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_tasks_parent_task_id
    ON crm_tasks (parent_task_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_tasks_tags
    ON crm_tasks USING GIN (tags)
    WHERE deleted_at IS NULL;

COMMIT;
