-- Migration tracking table + backfill of existing migrations.
-- This enables `robothor.db.migrate` to know which migrations have been applied.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT  -- SHA-256 of file contents at apply time
);

-- Backfill all 17 existing migrations as already applied.
INSERT INTO schema_migrations (version, filename, applied_at) VALUES
    ('001',  '001_crm_tables.sql',            NOW()),
    ('004',  '004_telemetry_table.sql',        NOW()),
    ('005',  '005_task_coordination.sql',      NOW()),
    ('006',  '006_task_state_machine.sql',     NOW()),
    ('007',  '007_routines.sql',               NOW()),
    ('008',  '008_multi_tenancy.sql',          NOW()),
    ('009',  '009_agent_notifications.sql',    NOW()),
    ('010',  '010_health_tables.sql',          NOW()),
    ('011',  '011_agent_engine.sql',           NOW()),
    ('012',  '012_webchat_trigger_type.sql',   NOW()),
    ('013',  '013_workflow_engine.sql',        NOW()),
    ('014',  '014_engine_enhancements.sql',    NOW()),
    ('015',  '015_chat_history.sql',           NOW()),
    ('015b', '015b_supervisor_to_main.sql',    NOW()),
    ('016',  '016_sub_agents.sql',             NOW()),
    ('017',  '017_timezone_new_york.sql',      NOW()),
    ('018',  '018_migration_tracking.sql',     NOW())
ON CONFLICT (version) DO NOTHING;

COMMIT;
