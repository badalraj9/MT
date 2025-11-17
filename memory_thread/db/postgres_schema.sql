-- memories table
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT CHECK(memory_type IN (
        'identity', 'preference', 'event', 'summary', 'timeline'
    )),
    extracted JSONB,
    importance FLOAT CHECK(importance >= 0 AND importance <= 1),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_accessed TIMESTAMP
);

-- memory_edges table
CREATE TABLE IF NOT EXISTS memory_edges (
    id UUID PRIMARY KEY,
    from_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    to_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    relation TEXT,
    weight FLOAT,
    last_activated TIMESTAMP
);
