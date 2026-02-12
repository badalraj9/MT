import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from memory_thread.config.settings import settings
from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import json
from memory_thread.models.events import Event, DeltaPatch, TruthVector, ActorEnum, ActionEnum, Provenance

class PostgresClient:
    _pool = None

    def __init__(self):
        if not PostgresClient._pool:
            PostgresClient._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_SERVER,
                port=settings.POSTGRES_PORT,
                cursor_factory=RealDictCursor
            )

    @contextmanager
    def get_connection(self):
        conn = PostgresClient._pool.getconn()
        try:
            yield conn
        finally:
            PostgresClient._pool.putconn(conn)

    @contextmanager
    def get_cursor(self, isolation_level=None):
        with self.get_connection() as conn:
            if isolation_level:
                conn.set_isolation_level(isolation_level)
            try:
                with conn.cursor() as cur:
                    yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise

class EventStore(PostgresClient):

    def fetch_next_gateway_seq(self, batch_size: int = 1) -> int:
        """
        Fetches the next value from the gateway sequence.
        Since `nextval` is atomic, we can just call it once or use setval logic?
        Actually, `nextval` increments by 1. To reserve a batch, we can call it repeatedly or use `setval` (unsafe).
        Better: Use `nextval` in a loop inside a single query or use `generate_series`.
        Example: SELECT nextval('gateway_seq') FROM generate_series(1, 10);
        Wait, we just need the *start* of the range if we assume exclusive access? No.
        Postgres sequences are safe. We can fetch one by one or fetch N values.

        Optimized: `SELECT nextval('gateway_seq')` returns one.
        If we want a batch, we can execute:
        `SELECT nextval('gateway_seq') FROM generate_series(1, %s)`
        and get the first one, knowing the rest follow?
        Actually, `nextval` isn't guaranteed to be contiguous if other transactions roll back (gaps),
        but it IS distinct and monotonic.

        If we want a batch of *contiguous* numbers assigned to *this* batch, we just need *unique* numbers.
        Fetching N values works.
        """
        # Fetching N values
        with self.get_cursor() as cur:
            cur.execute("SELECT nextval('gateway_seq') FROM generate_series(1, %s)", (batch_size,))
            rows = cur.fetchall()
            # rows is a list of RealDictRow, e.g. [{'nextval': 101}, {'nextval': 102}...]
            # Return the first one, or the list?
            # The Gateway needs to assign them.
            # Let's return the first value and assume the caller knows they have [first ... first+N-1]?
            # NO! Postgres sequence might have gaps if accessed concurrently by others.
            # We MUST use the values returned.
            return [r['nextval'] for r in rows]

    def append_event(self, event: Event) -> None:
        """
        Appends a single event.
        Uses ON CONFLICT DO NOTHING for deduplication.
        """
        query = """
            INSERT INTO events (
                id, namespace, timestamp, actor, action, object_id,
                delta, antecedents, truth_vector, provenance,
                gateway_seq, dedup_hash
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (namespace, object_id, dedup_hash) DO NOTHING
        """
        # Serialize complex types
        delta_json = json.dumps([d.dict() for d in event.delta])
        antecedents_json = json.dumps([str(u) for u in event.antecedents])
        truth_json = event.truth_vector.json()
        provenance_json = event.provenance.json()

        with self.get_cursor(isolation_level=psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE) as cur:
            cur.execute(query, (
                str(event.id), event.namespace, event.timestamp, event.actor, event.action,
                str(event.object_id), delta_json, antecedents_json, truth_json, provenance_json,
                event.gateway_seq, event.dedup_hash
            ))

    def get_event(self, event_id: UUID) -> Optional[Event]:
        query = "SELECT * FROM events WHERE id = %s"
        with self.get_cursor() as cur:
            cur.execute(query, (str(event_id),))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    def list_events_by_object(self, object_id: UUID) -> List[Event]:
        query = "SELECT * FROM events WHERE object_id = %s ORDER BY gateway_seq ASC" # Order by Seq!
        with self.get_cursor() as cur:
            cur.execute(query, (str(object_id),))
            rows = cur.fetchall()
            return [self._row_to_event(r) for r in rows]

    def insert_event_timewarp(self, event: Event) -> None:
        self.append_event(event)

    def _row_to_event(self, row: Dict[str, Any]) -> Event:
        delta_raw = row['delta'] if isinstance(row['delta'], list) else json.loads(row['delta'])
        deltas = [DeltaPatch(**d) for d in delta_raw]

        antecedents_raw = row['antecedents'] if isinstance(row['antecedents'], list) else json.loads(row['antecedents'])
        antecedents = [UUID(u) for u in antecedents_raw]

        truth_vector = TruthVector(**(row['truth_vector'] if isinstance(row['truth_vector'], dict) else json.loads(row['truth_vector'])))
        provenance = Provenance(**(row['provenance'] if isinstance(row['provenance'], dict) else json.loads(row['provenance'])))

        return Event(
            id=UUID(row['id']),
            namespace=row['namespace'],
            timestamp=row['timestamp'],
            actor=ActorEnum(row['actor']),
            action=ActionEnum(row['action']),
            object_id=UUID(row['object_id']),
            delta=deltas,
            antecedents=antecedents,
            truth_vector=truth_vector,
            provenance=provenance,
            gateway_seq=row['gateway_seq'],
            dedup_hash=row['dedup_hash']
        )

class SnapshotStore(PostgresClient):
    def save_snapshot(self, entity_id: UUID, version: int, state: Dict[str, Any]) -> None:
        query = """
            INSERT INTO snapshots (entity_id, version, state, created_at)
            VALUES (%s, %s, %s, NOW())
        """
        with self.get_cursor() as cur:
            cur.execute(query, (str(entity_id), version, json.dumps(state)))

    def get_latest_snapshot(self, entity_id: UUID) -> Optional[Dict[str, Any]]:
        query = """
            SELECT state, version FROM snapshots
            WHERE entity_id = %s
            ORDER BY version DESC LIMIT 1
        """
        with self.get_cursor() as cur:
            cur.execute(query, (str(entity_id),))
            row = cur.fetchone()
            if row:
                return row
            return None
