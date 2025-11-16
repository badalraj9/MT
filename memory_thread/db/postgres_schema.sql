-- Table: memories
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT CHECK(memory_type IN (
      'identity', 'preference', 'event', 'summary', 'timeline', 'task'
    )),
    extracted JSONB,
    importance FLOAT CHECK(importance >= 0 AND importance <= 1),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    pinned BOOLEAN DEFAULT FALSE,
    domain TEXT,
    current_value TEXT,
    history JSONB,
    embedding VECTOR(1536)
);

-- Table: memory_edges
CREATE TABLE memory_edges (
    id UUID PRIMARY KEY,
    from_id UUID REFERENCES memories(id),
    to_id UUID REFERENCES memories(id),
    relation TEXT,
    weight FLOAT,
    last_activated TIMESTAMP
);
