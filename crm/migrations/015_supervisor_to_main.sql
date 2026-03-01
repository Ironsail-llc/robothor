-- Migration 015: Redirect supervisor agent references to main
-- Run after deploying the merged supervisor → main agent changes.
--
-- This is a one-time data migration. The supervisor agent no longer exists;
-- all its tasks and notifications are now handled by the main agent.

-- Reassign open tasks from supervisor to main
UPDATE crm_tasks
SET assigned_to_agent = 'main'
WHERE assigned_to_agent = 'supervisor'
  AND status NOT IN ('DONE');

-- Redirect unread notifications
UPDATE crm_agent_notifications
SET to_agent = 'main'
WHERE to_agent = 'supervisor'
  AND read_at IS NULL;
