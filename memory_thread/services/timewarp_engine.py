import uuid
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, Any
import json

from memory_thread.models.events import Event, EntityState, DeltaPatch, TruthVector, ActorEnum, ActionEnum, Provenance
from memory_thread.services.snapshot_service import SnapshotService
from memory_thread.services.replay_service import ReplayService
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TimewarpEngine:
    def __init__(self):
        self.snapshot_service = SnapshotService()
        # self.replay_service = ReplayService() # Removed dependency to avoid circular or redundant logic
        self.pg = PostgresClient()
        self.tms = TMSService()

    def insert_late_event(self, event: Event) -> Dict[str, Any]:
        """
        Inserts a late event and repairs the timeline.
        1. Insert event into DB (Chronological/Append log).
        2. Identify affected entities.
        3. Recompute state from T(event).
        """
        # Serialize fields manually as PostgresClient might expect specific format or handled by adapter
        delta_json = json.dumps([d.dict() for d in event.delta])
        truth_json = event.truth_vector.json()
        antecedents_json = json.dumps([str(u) for u in event.antecedents])
        provenance_json = event.provenance.json() if event.provenance else None

        with self.pg.get_cursor() as cur:
             cur.execute("""
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(event.id), event.namespace, event.timestamp,
                event.actor.value, event.action.value, str(event.object_id),
                delta_json,
                antecedents_json,
                truth_json,
                provenance_json
            ))

        # 2. Recompute State
        new_state = self._recompute_state(event.object_id)

        # 3. Update State in DB
        # TODO: This direct update is Phase 3 style. Phase 4/6 might require snapshot update.
        # But this function ensures 'current_state' in DB reflects the corrected timeline.

        if new_state:
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    UPDATE entity_state
                    SET current_value = %s, truth_vector = %s, last_event_id = %s, updated_at = %s, version = version + 1
                    WHERE entity_id = %s
                """, (
                    json.dumps(new_state.current_value),
                    new_state.truth_vector.json(),
                    str(new_state.last_event_id),
                    datetime.now(timezone.utc),
                    str(new_state.entity_id)
                ))

        log.info(f"Timewarp: Repaired state for {event.object_id} after late event {event.id}")
        return {"status": "repaired", "new_state": new_state.current_value if new_state else {}}

    def _recompute_state(self, entity_id: uuid.UUID) -> Optional[EntityState]:
        """
        Rebuilds state from scratch using ALL events in DB (including the new late one).
        """
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance
                FROM events
                WHERE object_id = %s
                ORDER BY timestamp ASC
            """, (str(entity_id),))
            rows = cur.fetchall()

        if not rows:
            return None

        # Rehydrate and Replay
        first_row = rows[0]

        # Helper to hydrate TruthVector safely
        def get_tv(row):
             d = row['truth_vector']
             if isinstance(d, str): d = json.loads(d)
             if isinstance(d, dict): return TruthVector(**d)
             # Fallback
             return TruthVector(confidence=0, authority=0, corroboration=0)

        # Helper to hydrate Delta
        def get_delta(row):
            d = row['delta']
            if isinstance(d, str): d = json.loads(d)
            if isinstance(d, list): return [DeltaPatch(**x) for x in d]
            return []

        initial_tv = get_tv(first_row)

        current_state = EntityState(
            entity_id=entity_id,
            namespace=first_row['namespace'],
            current_value={},
            truth_vector=initial_tv,
            version=0,
            last_event_id=uuid.UUID(first_row['id']),
            updated_at=first_row['timestamp'] # Use event timestamp for initial state time
        )

        for r in rows:
            evt = Event(
                id=uuid.UUID(r['id']),
                namespace=r['namespace'],
                timestamp=r['timestamp'],
                actor=ActorEnum(r['actor']),
                action=ActionEnum(r['action']),
                object_id=uuid.UUID(r['object_id']),
                delta=get_delta(r),
                antecedents=[uuid.UUID(u) for u in (json.loads(r['antecedents']) if isinstance(r['antecedents'], str) else r['antecedents'] or [])],
                truth_vector=get_tv(r),
                provenance=Provenance(**(json.loads(r['provenance']) if isinstance(r['provenance'], str) else r['provenance'])) if r['provenance'] else None
            )

            current_state = StateDerivationService.apply_event(current_state, evt)

        return current_state
