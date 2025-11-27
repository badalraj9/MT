-- NODE TABLE ---------------------------------------------------
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT CHECK(memory_type IN (
        'identity', 'preference', 'event', 'fact',
        'task', 'belief', 'other', 'timeline' -- timeline is still needed
    )),
    importance FLOAT CHECK(importance >= 0 AND importance <= 1),

    -- Extracted, top-level fields
    entities TEXT[],
    topics TEXT[],

    -- Timestamps
    created_at TIMESTAMP,
    last_accessed TIMESTAMP,

    -- Graph-related fields
    relations UUID[],

    -- Structured metadata
    metadata JSONB,

    -- Fields for timeline memories (still required by timeline_service)
    domain TEXT,
    current_value TEXT,
    history JSONB
);

-- EDGE TABLE ---------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_edges (
    id UUID PRIMARY KEY,
    from_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    to_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    relation TEXT,
    weight FLOAT,
    last_activated TIMESTAMP
);

-- EXTENSIONS & INDEXES -----------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS memories_content_trgm_idx ON memories USING gin (content gin_trgm_ops);
