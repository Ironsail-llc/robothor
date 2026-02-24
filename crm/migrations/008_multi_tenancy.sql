-- Migration 008: Multi-Tenancy Support
-- Adds crm_tenants table and tenant_id column to all CRM tables.
-- All existing data is backfilled to 'robothor-primary' tenant.
-- Composite indexes for tenant-scoped queries.

BEGIN;

-- ─── Tenants Table ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS crm_tenants (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    parent_tenant_id TEXT REFERENCES crm_tenants(id),
    settings JSONB DEFAULT '{}',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenants_parent ON crm_tenants(parent_tenant_id) WHERE parent_tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tenants_active ON crm_tenants(active) WHERE active = TRUE;

-- Seed the primary tenant
INSERT INTO crm_tenants (id, display_name)
VALUES ('robothor-primary', 'Robothor Primary')
ON CONFLICT (id) DO NOTHING;

-- ─── Add tenant_id to CRM Tables ────────────────────────────────────────

-- People
ALTER TABLE crm_people ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_people SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_people_tenant ON crm_people(tenant_id) WHERE deleted_at IS NULL;

-- Companies
ALTER TABLE crm_companies ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_companies SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_companies_tenant ON crm_companies(tenant_id) WHERE deleted_at IS NULL;

-- Notes
ALTER TABLE crm_notes ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_notes SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_notes_tenant ON crm_notes(tenant_id) WHERE deleted_at IS NULL;

-- Tasks
ALTER TABLE crm_tasks ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_tasks SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON crm_tasks(tenant_id) WHERE deleted_at IS NULL;

-- Task History
ALTER TABLE crm_task_history ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_task_history SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_task_history_tenant ON crm_task_history(tenant_id);

-- Routines
ALTER TABLE crm_routines ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_routines SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_routines_tenant ON crm_routines(tenant_id) WHERE deleted_at IS NULL;

-- Conversations
ALTER TABLE crm_conversations ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_conversations SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_tenant ON crm_conversations(tenant_id);

-- Messages
ALTER TABLE crm_messages ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'robothor-primary' REFERENCES crm_tenants(id);
UPDATE crm_messages SET tenant_id = 'robothor-primary' WHERE tenant_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_messages_tenant ON crm_messages(tenant_id);

COMMIT;
