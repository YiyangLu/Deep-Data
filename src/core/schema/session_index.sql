-- Global Session Index Schema
-- File: session_index.db
-- Purpose: Cross-session queries and metadata

CREATE TABLE IF NOT EXISTS sessions (
    -- Identity
    session_id TEXT PRIMARY KEY,
    folder_path TEXT NOT NULL,

    -- Temporal
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Properties
    agent_id TEXT NOT NULL,
    cwd TEXT NOT NULL,

    -- Files
    transcript_file TEXT NOT NULL DEFAULT 'transcript.txt',

    -- Context
    latest_query TEXT,

    -- Cost tracking
    total_cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,

    -- User metadata
    notes TEXT,
    tags TEXT,
    session_name TEXT DEFAULT 'Agent',  -- User-friendly session name

    -- Parent activity (for sessions created by deep_plot/mle)
    parent_activity_type TEXT,  -- 'mle' | 'deep_plot' | null for standalone
    parent_activity_id TEXT     -- run_id | analysis_id | null
);

-- Activities table (tracks high-level user activities)
CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,              -- 'agent' | 'deep_plot' | 'mle'
    name TEXT,                       -- user-friendly name
    status TEXT DEFAULT 'running',   -- 'running' | 'paused' | 'completed' | 'failed'
    config TEXT,                     -- JSON: activity-specific configuration
    result TEXT,                     -- JSON: activity-specific results
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions(cwd);
CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(parent_activity_type, parent_activity_id);
CREATE INDEX IF NOT EXISTS idx_activities_updated ON activities(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(type);
