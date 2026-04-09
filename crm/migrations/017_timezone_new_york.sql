-- Migration 017: Revert timezone from America/Grenada back to America/New_York
-- Timezone set to Eastern Time for all schedules.

ALTER TABLE agent_schedules ALTER COLUMN timezone SET DEFAULT 'America/New_York';
UPDATE agent_schedules SET timezone = 'America/New_York' WHERE timezone = 'America/Grenada';
