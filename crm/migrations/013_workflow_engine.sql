-- 013_workflow_engine.sql
-- Declarative workflow engine tables: workflow runs + per-step audit trail.

-- Workflow execution runs
CREATE TABLE IF NOT EXISTS workflow_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'robothor-primary',
    workflow_id     TEXT NOT NULL,
    trigger_type    TEXT NOT NULL DEFAULT 'manual',
    trigger_detail  TEXT,
    correlation_id  TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'timeout', 'cancelled')),
    steps_total     INTEGER NOT NULL DEFAULT 0,
    steps_completed INTEGER NOT NULL DEFAULT 0,
    steps_failed    INTEGER NOT NULL DEFAULT 0,
    steps_skipped   INTEGER NOT NULL DEFAULT 0,
    context         JSONB DEFAULT '{}',
    error_message   TEXT,
    duration_ms     INTEGER,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Per-step audit trail
CREATE TABLE IF NOT EXISTS workflow_run_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    step_id         TEXT NOT NULL,
    step_type       TEXT NOT NULL CHECK (step_type IN ('agent', 'tool', 'condition', 'transform', 'noop')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    agent_id        TEXT,
    agent_run_id    UUID,
    tool_name       TEXT,
    tool_input      JSONB,
    tool_output     JSONB,
    condition_branch TEXT,
    output_text     TEXT,
    error_message   TEXT,
    duration_ms     INTEGER,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_status ON workflow_runs(workflow_id, status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_tenant ON workflow_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created ON workflow_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_correlation ON workflow_runs(correlation_id) WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_run ON workflow_run_steps(run_id);
