-- Critical Fixes Schema for Memory Thread
-- Addresses: Determinism, Event Ordering, Deduplication, Strict Types

-- 1. Global Sequence for Total Ordering
CREATE SEQUENCE IF NOT EXISTS gateway_seq START 1;

-- 2. New Strict Events Table
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY, -- No default, must be deterministic
    namespace TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL, -- Gateway assigned
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    object_id UUID NOT NULL,
    delta JSONB NOT NULL,
    antecedents JSONB NOT NULL DEFAULT '[]'::jsonb,
    truth_vector JSONB NOT NULL,
    provenance JSONB NOT NULL,

    -- Critical New Columns
    gateway_seq BIGINT NOT NULL,
    dedup_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consolidated_into UUID -- For assimilation
);

-- 3. Indices for Performance & Correctness
CREATE INDEX IF NOT EXISTS idx_events_namespace_ts_seq ON events(namespace, timestamp, gateway_seq);
CREATE INDEX IF NOT EXISTS idx_events_object ON events(object_id);
CREATE INDEX IF NOT EXISTS idx_events_gateway_seq ON events(gateway_seq);

-- 4. Deduplication Index (Unique Constraint)
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedupe ON events(namespace, object_id, dedup_hash);

-- 5. Append-Only Trigger
CREATE OR REPLACE FUNCTION prevent_event_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'DELETE') THEN
        RAISE EXCEPTION 'Events are append-only. DELETE not allowed.';
    ELSIF (TG_OP = 'UPDATE') THEN
        -- Allow updating ONLY 'consolidated_into' for maintenance
        IF (OLD.consolidated_into IS DISTINCT FROM NEW.consolidated_into) THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'Events are append-only. UPDATE not allowed except for consolidation.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_event_mod ON events;
CREATE TRIGGER trg_prevent_event_mod
BEFORE UPDATE OR DELETE ON events
FOR EACH ROW EXECUTE FUNCTION prevent_event_modification();
