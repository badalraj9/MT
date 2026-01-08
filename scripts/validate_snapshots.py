import sys
import os
import logging
from typing import List
from uuid import UUID

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory_thread.services.replay_service import ReplayService
from memory_thread.services.snapshot_service import SnapshotService
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger("SNAPSHOT_VALIDATOR")
logging.basicConfig(level=logging.INFO)

def validate_recent_snapshots(limit: int = 5):
    """
    Validates the integrity of the N most recent snapshots.
    """
    pg = PostgresClient()
    replay = ReplayService()
    
    log.info(f"--- Validating Last {limit} Snapshots ---")
    
    with pg.get_cursor() as cur:
        # Fetch recent snapshots
        cur.execute("""
            SELECT id, entity_id, timestamp 
            FROM snapshots 
            ORDER BY timestamp DESC 
            LIMIT %s
        """, (limit,))
        snapshots = cur.fetchall()
        
    if not snapshots:
        log.warning("No snapshots found to validate.")
        return

    failures = 0
    passed = 0

    for snap in snapshots:
        # Handle dict or tuple cursor
        snap_id = snap['id'] if isinstance(snap, dict) else snap[0]
        entity_id = snap['entity_id'] if isinstance(snap, dict) else snap[1]
        ts = snap['timestamp'] if isinstance(snap, dict) else snap[2]
        
        log.info(f"Checking Snapshot {snap_id} for Entity {entity_id}...")
        
        try:
            # 1. Capture Trace (Golden Source)
            # ReplayService captures CURRENT state. We need to verify the SNAPSHOT state.
            # But ReplayService also fetches all events.
            # Let's manually fetch the specific snapshot state to compare against.
            
            # Fetch expected state from snapshot
            # (In a real CI, we might load this via SnapshotService, but we need the exact object)
            # ReplayService has logic to verify CURRENT state. We can adapt it?
            # Or just use ReplayService.capture_trace() to get events, and assume current state IS the snapshot
            # IF the entity hasn't changed since.
            # But the entity likely changed.
            
            # Correct Approach:
            # 1. Fetch Snapshot State (S_snap)
            # 2. Fetch Events <= Snapshot.Timestamp (E_hist)
            # 3. Replay E_hist -> S_derived
            # 4. Assert S_snap == S_derived
            
            # We can use ReplayService.replay_trace if we construct a "trace" object manually.
            
            # A. Get Snapshot
            # We need full data.
            with pg.get_cursor() as cur:
                cur.execute("SELECT state_data, truth_vector FROM snapshots WHERE id = %s", (str(snap_id),))
                s_row = cur.fetchone()
                s_data = s_row['state_data'] if isinstance(s_row, dict) else s_row[0]
                s_tv = s_row['truth_vector'] if isinstance(s_row, dict) else s_row[1]
                
            # Create "Expected State" dict for ReplayService
            import json
            if isinstance(s_tv, str): s_tv = json.loads(s_tv)
            
            # B. Get Events
            # We need events where timestamp <= snap_ts
            # ReplayService doesn't have a time-bounded fetch public method easily.
            # We'll fetch manually matching ReplayService logic.
            with pg.get_cursor() as cur:
                cur.execute("""
                    SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector
                    FROM events
                    WHERE object_id = %s AND timestamp <= %s
                    ORDER BY timestamp ASC
                """, (str(entity_id), ts))
                event_rows = cur.fetchall()
            
            if not event_rows:
                log.warning("Skipping: No events found before snapshot.")
                continue

            # Construct Trace Dict
            events_json = []
            for r in event_rows:
                # Handle mapping (assuming RealDictCursor or tuple)
                # Being lazy/robust: access by index if tuple, key if dict
                # ... let's assume we can map or use ReplayService logic if we can import Query.
                # To be safe, let's map assuming tuple since PG client defaults often tuple.
                # id=0, ns=1, ts=2, act=3, action=4, obj=5, delta=6, ant=7, tv=8
                if isinstance(r, dict):
                    e_dict = {
                        "id": str(r['id']), "namespace": r['namespace'], "timestamp": r['timestamp'].isoformat(),
                        "actor": r['actor'], "action": r['action'], "object_id": str(r['object_id']),
                        "delta": r['delta'], "antecedents": r['antecedents'], 
                        "truth_vector": json.loads(r['truth_vector']) if isinstance(r['truth_vector'], str) else r['truth_vector']
                    }
                else: 
                     e_dict = {
                        "id": str(r[0]), "namespace": r[1], "timestamp": r[2].isoformat(),
                        "actor": r[3], "action": r[4], "object_id": str(r[5]),
                        "delta": r[6], "antecedents": r[7], 
                        "truth_vector": json.loads(r[8]) if isinstance(r[8], str) else r[8]
                    }
                events_json.append(e_dict)

            # Construct Fake Final State for comparison
            expected_final = {
                "entity_id": str(entity_id),
                "namespace": events_json[0]["namespace"], # Assume same
                "current_value": s_data,
                "truth_vector": s_tv,
                "version": 0, # Ignored in loose comparison?
                "last_event_id": str(UUID("00000000-0000-0000-0000-000000000000")), # Dummy
                "updated_at": ts.isoformat()
            }
            
            trace = {
                "entity_id": str(entity_id),
                "captured_at": ts.isoformat(),
                "final_state": expected_final,
                "events": events_json
            }
            
            # Run Verification
            success, diffs, _ = replay.replay_trace(trace)
            
            if success:
                log.info(f"✅ Snapshot {snap_id}: VALID")
                passed += 1
            else:
                log.error(f"❌ Snapshot {snap_id}: INVALID")
                for d in diffs:
                    log.error(f"   Diff: {d}")
                failures += 1

        except Exception as e:
            log.error(f"❌ Error validating snapshot {snap_id}: {e}")
            failures += 1

    log.info(f"--- Validation Complete: {passed} Passed, {failures} Failed ---")
    if failures > 0:
        sys.exit(1)

if __name__ == "__main__":
    validate_recent_snapshots()
