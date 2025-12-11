import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
import difflib

from memory_thread.models.events import Event, EntityState, TruthVector, DeltaPatch, Provenance
from memory_thread.services.tms_service import StateDerivationService
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class ReplayService:
    def __init__(self):
        self.pg = PostgresClient()

    def capture_trace(self, entity_id: UUID) -> Dict[str, Any]:
        """
        Captures the full history of an entity to create a 'Golden Trace'.
        This includes all events and the current final state.
        """
        # 1. Fetch Current Final State
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT entity_id, namespace, current_value, truth_vector, version, last_event_id, updated_at
                FROM entity_state
                WHERE entity_id = %s
            """, (str(entity_id),))
            row = cur.fetchone()

        if not row:
            raise ValueError(f"Entity {entity_id} not found in state.")

        # Reconstruct EntityState object (handle Pydantic parsing)
        tv_data = row['truth_vector']
        # Ensure TV is dict
        if isinstance(tv_data, str):
            tv_data = json.loads(tv_data)

        final_state = EntityState(
            entity_id=row['entity_id'],
            namespace=row['namespace'],
            current_value=row['current_value'],
            truth_vector=TruthVector(**tv_data),
            version=row['version'],
            last_event_id=row['last_event_id'],
            updated_at=row['updated_at']
        )

        # 2. Fetch All Events
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance
                FROM events
                WHERE object_id = %s
                ORDER BY timestamp ASC
            """, (str(entity_id),))
            event_rows = cur.fetchall()

        events = []
        for r in event_rows:
            tv_data = r['truth_vector']
            if isinstance(tv_data, str): tv_data = json.loads(tv_data)

            delta_data = r['delta']
            if isinstance(delta_data, str): delta_data = json.loads(delta_data)
            deltas = [DeltaPatch(**d) for d in delta_data]

            antecedents_data = r['antecedents']
            if isinstance(antecedents_data, str): antecedents_data = json.loads(antecedents_data)

            prov_data = r['provenance']
            if isinstance(prov_data, str): prov_data = json.loads(prov_data)
            prov = Provenance(**prov_data) if prov_data else None

            events.append(Event(
                id=r['id'],
                namespace=r['namespace'],
                timestamp=r['timestamp'],
                actor=r['actor'],
                action=r['action'],
                object_id=r['object_id'],
                delta=deltas,
                antecedents=antecedents_data or [],
                truth_vector=TruthVector(**tv_data),
                provenance=prov
            ))

        trace = {
            "entity_id": str(entity_id),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "final_state": json.loads(final_state.model_dump_json()),
            "events": [json.loads(e.model_dump_json()) for e in events]
        }
        return trace

    def replay_trace(self, trace: Dict[str, Any]) -> Tuple[bool, List[str], Optional[EntityState]]:
        """
        Replays the events from the trace and compares with the expected final state.
        Returns: (Success, DiffReport, ActualFinalState)
        """
        events_data = trace['events']
        expected_state_data = trace['final_state']

        first_evt_data = events_data[0]
        # Hydrate initial state logic
        # Assuming empty start if no S0 provided

        current_state = EntityState(
            entity_id=UUID(trace['entity_id']),
            namespace=first_evt_data['namespace'],
            current_value={},
            truth_vector=TruthVector(confidence=0, authority=0, corroboration=0),
            version=0,
            last_event_id=UUID(first_evt_data['id']),
            updated_at=datetime.now(timezone.utc)
        )

        for i, evt_data in enumerate(events_data):
            # Safe rehydration
            # If using Pydantic V2, model_validate(dict) is preferred. But using **dict for now.
            # Complex fields might need manual hydration if JSON didn't serialize them perfectly flat.
            # But Event(***) should work if the dict structure matches.
            try:
                 evt = Event(**evt_data)
            except Exception as e:
                # If DeltaPatch objects are dicts inside, Pydantic should auto-convert
                return False, [f"Hydration error at Event #{i}: {e}"], None

            try:
                current_state = StateDerivationService.apply_event(current_state, evt)
            except Exception as e:
                return False, [f"Crash at Event #{i} ({evt.id}): {e}"], current_state

        # 3. Compare Result
        expected_state = EntityState(**expected_state_data)

        diffs = []
        if current_state.current_value != expected_state.current_value:
            diffs.append("State Value Mismatch:")
            diffs.append(f"Expected: {expected_state.current_value}")
            diffs.append(f"Actual:   {current_state.current_value}")

        tv_act = current_state.truth_vector.dict()
        tv_exp = expected_state.truth_vector.dict()

        for k, v in tv_exp.items():
            if abs(tv_act.get(k, 0) - v) > 0.0001:
                diffs.append(f"TruthVector mismatch on '{k}': Exp={v}, Act={tv_act.get(k)}")

        success = len(diffs) == 0
        return success, diffs, current_state

    def save_trace(self, trace: Dict, filepath: str):
        with open(filepath, 'w') as f:
            json.dump(trace, f, indent=2)

    def load_trace(self, filepath: str) -> Dict:
        with open(filepath, 'r') as f:
            return json.load(f)
