-- Migration 038: Add user_id to audit trail
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log (user_id) WHERE user_id != '';
