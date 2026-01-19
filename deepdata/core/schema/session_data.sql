-- Per-Session Data Schema
-- File: sessions/{cwd_name}_{session_id}/session.db
-- Purpose: Conversation, plots, and interactions for a single session

-- Table 1: Conversation Blocks (JSON with generated columns)
CREATE TABLE IF NOT EXISTS conversation_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_number INTEGER NOT NULL,
    block_index INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' or 'assistant'

    -- Full JSON from Claude SDK
    block_data TEXT NOT NULL,

    -- Generated columns (auto-extracted from JSON for fast queries)
    block_type TEXT GENERATED ALWAYS AS (block_data ->> '$.type') STORED,
    tool_name TEXT GENERATED ALWAYS AS (block_data ->> '$.name') STORED,
    text_content TEXT GENERATED ALWAYS AS (block_data ->> '$.text') STORED,
    tool_use_id TEXT GENERATED ALWAYS AS (block_data ->> '$.id') STORED,

    -- Constraints
    CHECK (block_type IN ('text', 'tool_use', 'tool_result')),
    CHECK (role IN ('user', 'assistant'))
);

-- Indexes on conversation_blocks
CREATE INDEX IF NOT EXISTS idx_conversation_turn
    ON conversation_blocks(turn_number, block_index);
CREATE INDEX IF NOT EXISTS idx_block_type
    ON conversation_blocks(block_type);
CREATE INDEX IF NOT EXISTS idx_tool_name
    ON conversation_blocks(tool_name)
    WHERE tool_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tool_use_id
    ON conversation_blocks(tool_use_id)
    WHERE tool_use_id IS NOT NULL;

-- Optional: Full-text search on conversation
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts USING fts5(
    text_content,
    content='conversation_blocks',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS conversation_ai AFTER INSERT ON conversation_blocks BEGIN
    INSERT INTO conversation_fts(rowid, text_content)
    VALUES (new.id, new.text_content);
END;

CREATE TRIGGER IF NOT EXISTS conversation_ad AFTER DELETE ON conversation_blocks BEGIN
    DELETE FROM conversation_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS conversation_au AFTER UPDATE ON conversation_blocks BEGIN
    DELETE FROM conversation_fts WHERE rowid = old.id;
    INSERT INTO conversation_fts(rowid, text_content)
    VALUES (new.id, new.text_content);
END;

-- Table 2: Plots
-- Note: fig_json is stored in plots/{plot_id}.json files for fast recovery
CREATE TABLE IF NOT EXISTS plots (
    plot_id INTEGER PRIMARY KEY,
    plotly_code TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: Interactions
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id INTEGER NOT NULL,
    interaction_id INTEGER NOT NULL,  -- Per-plot sequence (1, 2, 3... for each plot)
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    screenshot_path TEXT,
    screenshot_size_kb INTEGER,

    -- Cumulative state at this interaction point (for state restoration)
    -- JSON: {"xaxis.range": [...], "yaxis.range": [...], "trace_visibility": [...]}
    view_state TEXT,

    -- Foreign key with cascade delete
    FOREIGN KEY (plot_id) REFERENCES plots(plot_id) ON DELETE CASCADE,

    -- Constraint on event types
    CHECK (event_type IN (
        'init',
        'relayout',
        'click',
        'doubleclick',
        'hover',
        'selected',
        'legendclick',
        'restyle',
        'page_load',
        'page_close'
    )),

    -- Unique constraint: each plot has unique interaction numbers
    UNIQUE (plot_id, interaction_id)
);

-- Indexes on interactions
CREATE INDEX IF NOT EXISTS idx_interactions_plot
    ON interactions(plot_id);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp
    ON interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_event_type
    ON interactions(event_type);
CREATE INDEX IF NOT EXISTS idx_interactions_screenshot
    ON interactions(screenshot_path)
    WHERE screenshot_path IS NOT NULL;
