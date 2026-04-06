-- 031_run_status_skipped.sql
-- Add 'skipped' to the status CHECK constraint for agent_runs and workflow_runs.
-- Needed for dedup logic that marks duplicate/concurrent runs as skipped
-- rather than completed or failed.

BEGIN;

ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check
    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'timeout', 'cancelled', 'skipped'));

ALTER TABLE workflow_runs DROP CONSTRAINT IF EXISTS workflow_runs_status_check;
ALTER TABLE workflow_runs ADD CONSTRAINT workflow_runs_status_check
    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'timeout', 'cancelled', 'skipped'));

COMMIT;
