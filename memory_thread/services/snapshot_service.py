import uuid
import json
import hashlib
from typing import Dict, Any, Optional, List
from memory_thread.models.events import EntityState, Event
from memory_thread.services.tms_service import StateDerivationService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class SnapshotService:
    def __init__(self):
        # Mock DB for snapshots
        self.snapshots_db: Dict[uuid.UUID, List[Dict]] = {}

    def take_snapshot(self, state: EntityState) -> str:
        """
        Persists current state as a checkpoint.
        Returns the snapshot ID (or hash).
        """
        state_json = state.json()
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()

        snapshot_record = {
            "id": uuid.uuid4(),
            "entity_id": state.entity_id,
            "last_event_id": state.last_event_id,
            "state_data": state.current_value,
            "truth_vector": state.truth_vector,
            "timestamp": state.updated_at,
            "state_hash": state_hash
        }

        if state.entity_id not in self.snapshots_db:
            self.snapshots_db[state.entity_id] = []
        self.snapshots_db[state.entity_id].append(snapshot_record)

        log.info(f"Snapshot taken for {state.entity_id} at event {state.last_event_id}")
        return state_hash

    def get_latest_snapshot(self, entity_id: uuid.UUID) -> Optional[EntityState]:
        """Retrieves the most recent snapshot."""
        if entity_id not in self.snapshots_db:
            return None

        # Sort by timestamp desc (simple list mock)
        snaps = sorted(self.snapshots_db[entity_id], key=lambda x: x['timestamp'], reverse=True)
        if not snaps:
            return None

        latest = snaps[0]
        return EntityState(
            entity_id=entity_id,
            namespace="user", # Need to store namespace in snapshot ideally
            current_value=latest["state_data"],
            truth_vector=latest["truth_vector"],
            last_event_id=latest["last_event_id"],
            updated_at=latest["timestamp"]
        )

class ReplayService:
    def __init__(self, snapshot_service: SnapshotService):
        self.snapshot_service = snapshot_service
        # Mock Event Store
        self.event_store: Dict[uuid.UUID, List[Event]] = {}

    def add_event_to_log(self, event: Event):
        if event.object_id not in self.event_store:
            self.event_store[event.object_id] = []
        self.event_store[event.object_id].append(event)

    def replay_events(self, entity_id: uuid.UUID, target_time=None) -> EntityState:
        """
        Reconstructs state by loading latest snapshot < target_time
        and replaying subsequent events.
        """
        # 1. Load Snapshot
        snapshot = self.snapshot_service.get_latest_snapshot(entity_id)

        # 2. Get Events
        all_events = self.event_store.get(entity_id, [])
        # Sort by time
        all_events.sort(key=lambda x: x.timestamp)

        # 3. Determine Replay Start
        start_index = 0
        current_state = None

        if snapshot:
            # Validate snapshot isn't *after* target_time (if time travel)
            # For simplistic "Current State" replay:
            current_state = snapshot
            # Find where to start in event list
            # Ideally DB query: SELECT * FROM events WHERE timestamp > snapshot.timestamp
            for i, e in enumerate(all_events):
                if e.id == snapshot.last_event_id:
                    start_index = i + 1
                    break
        else:
            # Init empty state
            if not all_events:
                return None
            first_evt = all_events[0]
            # Create a dummy empty state to start application
            current_state = EntityState(
                entity_id=entity_id,
                namespace=first_evt.namespace,
                current_value={},
                truth_vector=first_evt.truth_vector, # placeholder
                last_event_id=uuid.uuid4()
            )

        # 4. Replay Loop
        for i in range(start_index, len(all_events)):
            evt = all_events[i]
            # Time travel check
            if target_time and evt.timestamp > target_time:
                break

            current_state = StateDerivationService.apply_event(current_state, evt)

        return current_state
