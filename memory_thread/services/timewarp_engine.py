import uuid
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from memory_thread.models.events import Event, EntityState
from memory_thread.services.snapshot_service import SnapshotService
from memory_thread.services.replay_service import ReplayService
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TimewarpEngine:
    def __init__(self):
        self.snapshot_service = SnapshotService()
        self.pg = PostgresClient()

    def insert_late_event(self, event: Event, save_mismatch_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Insert a late event, recompute canonical state via ReplayService, persist entity_state, save snapshot.
        Returns dict with status and debug info.
        """
        rs = ReplayService()
        # 1) Insert late event into events table
        # Use a short transaction to insert then commit so replay can see it
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO events (
                    id, namespace, timestamp, actor, action, object_id,
                    delta, antecedents, truth_vector, provenance,
                    gateway_seq, dedup_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(event.id),
                event.namespace,
                event.timestamp,
                event.actor.value if hasattr(event.actor, "value") else event.actor,
                event.action.value if hasattr(event.action, "value") else event.action,
                str(event.object_id),
                json.dumps([d.model_dump() if hasattr(d, "model_dump") else d.__dict__ for d in (event.delta or [])]),
                json.dumps([str(a) for a in (event.antecedents or [])]),
                event.truth_vector.model_dump() if hasattr(event.truth_vector, "model_dump") else (event.truth_vector.__dict__ if event.truth_vector else None),
                event.provenance.model_dump() if (event.provenance and hasattr(event.provenance, "model_dump")) else (event.provenance.__dict__ if event.provenance else None),
                getattr(event, "gateway_seq", None),
                getattr(event, "dedup_hash", None)
            ))
            # commit is automatic after context exit if using connection pool

        # Acquire an advisory lock on the entity to prevent concurrent repairs / writes
        # Using hashtext for simplicity as agreed
        lock_sql = "SELECT pg_advisory_lock(hashtext(%s))"
        unlock_sql = "SELECT pg_advisory_unlock(hashtext(%s))"

        try:
            with self.pg.get_cursor() as cur:
                cur.execute(lock_sql, (str(event.object_id),))

            # 2) Capture golden trace (now includes late event)
            trace = rs.capture_trace(event.object_id)

            # 3) Replay trace deterministically
            ok, diffs, actual_state = rs.replay_trace(trace, save_mismatch_path=save_mismatch_path)

            if not ok:
                # Save trace + diffs for triage if not done by replay_trace
                return {"status": "replay_failed", "diffs": diffs}

            # 4) Persist repaired state and snapshot atomically
            # Use last_event_id/timestamp from actual_state
            # Fallback logic handled by ReplayService state derivation, but double check
            last_evt_ts = actual_state.updated_at
            last_evt_id = actual_state.last_event_id
            version = getattr(actual_state, "version", None)

            with self.pg.get_cursor() as cur:
                cur.execute("""
                    UPDATE entity_state
                    SET current_value = %s, truth_vector = %s, last_event_id = %s, updated_at = %s, version = %s
                    WHERE entity_id = %s
                """, (
                    json.dumps(actual_state.current_value),
                    actual_state.truth_vector.model_dump() if hasattr(actual_state.truth_vector, "model_dump") else actual_state.truth_vector.__dict__,
                    str(last_evt_id) if last_evt_id else None,
                    last_evt_ts,
                    version,
                    str(actual_state.entity_id)
                ))

            # 5) Persist canonical snapshot via SnapshotService
            try:
                self.snapshot_service.take_snapshot(actual_state)
            except Exception:
                log.exception("Snapshot save failed (nonfatal)")

            # 6) Emit maintenance/orchestrator event or log
            log.info("Timewarp repaired entity %s after late event %s", str(event.object_id), str(event.id))

            return {"status": "repaired", "entity": str(event.object_id), "new_version": version}

        finally:
            # release advisory lock
            try:
                with self.pg.get_cursor() as cur:
                    cur.execute(unlock_sql, (str(event.object_id),))
            except Exception:
                log.exception("Failed to release advisory lock for entity %s", str(event.object_id))
