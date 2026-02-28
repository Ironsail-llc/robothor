BEGIN;

-- Session metadata: tracks active sessions, model overrides, last activity
CREATE TABLE IF NOT EXISTS chat_sessions (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT DEFAULT 'robothor-primary',
    session_key TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'telegram',  -- telegram, webchat
    model_override TEXT,                        -- persists /model selection
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, session_key)
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_active
    ON chat_sessions(last_active_at DESC);

-- Individual messages: one row per message, JSONB payload (LangChain pattern)
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message JSONB NOT NULL,                     -- {"role": "user", "content": "..."}
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages(session_id, created_at ASC);

-- TTL cleanup uses idx_chat_sessions_active (last_active_at DESC) for range scans

COMMIT;
