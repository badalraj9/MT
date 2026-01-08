import multiprocessing as mp
import time
import zmq
from memory_thread.nervous.queue_manager import QueueManager
from memory_thread.nervous.spillover_buffer import SpilloverBuffer
from memory_thread.nervous.persistence_scheduler import PersistenceScheduler
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class PersistenceEngine:
    def __init__(self):
        self.zm_ctx = zmq.Context()
        self.queue_manager = QueueManager(self.zm_ctx)
        self.spillover = SpilloverBuffer()
        self.scheduler = PersistenceScheduler()
        self.running = mp.Value('b', True)
        self.consumer_process = mp.Process(target=self._consumer_loop)

    def start(self):
        # Ingestion calls setup_producer(), Consumer calls setup_consumer()
        # But we spawn consumer process here.
        self.consumer_process.start()
        # Allow time for bind
        time.sleep(0.1)
        self.queue_manager.setup_producer()

    def push(self, item):
        self.queue_manager.send(item)

    def stop(self):
        self.running.value = False
        self.queue_manager.close()
        self.consumer_process.join()
        self.spillover.close()

    def _consumer_loop(self):
        # Re-init for process safety
        qm = QueueManager(address="ipc://persistence_pipe")
        qm.setup_consumer()
        qm = QueueManager(address="ipc://persistence_pipe")
        qm.setup_consumer()
        # Hardening: max_memory_size=0 ensures ALL items hit disk for durability/replay
        spill = SpilloverBuffer(max_memory_size=0) 
        sched = PersistenceScheduler()

        log.info("Persistence Engine Consumer Started")
        
        # Hardening: Initialize Real DB Clients
        from memory_thread.db.postgres_client import PostgresClient
        from memory_thread.db.qdrant_client import QdrantClientWrapper
        import json
        
        pg_client = None
        qdrant_client = None
        
        try:
            pg_client = PostgresClient()
            qdrant_client = QdrantClientWrapper()
            log.info("Persistence Engine: DB Clients Initialized")
        except Exception as e:
            log.error(f"Persistence Engine: Failed to init DB clients: {e}")

        last_stat_time = time.time()

        while self.running.value:
            # Stats Logging
            if time.time() - last_stat_time > 1.0:
                stats = spill.get_stats()
                if stats['disk_count'] > 0:
                    log.warning(f"Persistence Backpressure: {stats['disk_count']} items on disk, {stats['memory_count']} in memory")
                last_stat_time = time.time()

            # 1. Pull from ZMQ (Q2)
            item = qm.receive(timeout_ms=10)

            # 2. Buffer (Spillover Logic)
            if item:
                spill.push(item)

            # 3. Process from Buffer (Q3) -> DB
            # We fetch from spillover to maintain order
            next_item = spill.pop()
            if next_item:
                if sched.add(next_item):
                    # Batch Ready
                    # Batch Ready
                    batch = sched.get_batch()
                    self._write_batch(batch, sched, pg_client, qdrant_client)
            else:
                time.sleep(0.01) # Idle

        qm.close()
        spill.close()

    def _write_batch(self, batch, sched, pg_client, qdrant_client):
        if not batch: return

        start = time.time()
        
        # 1. Segregate Data
        events_data = []
        states_data = []
        vectors_points = []
        
        from qdrant_client.models import PointStruct
        
        for item in batch:
            # item payload structure from ingest_service:
            # { "event": dict, "state": dict, "original_text": str }
            
            evt = item.get("event")
            state = item.get("state")
            
            if evt:
                events_data.append(evt)
            
            if state:
                states_data.append(state)
                # Prepare Vector (using state/event data)
                vec = item.get("vector")
                if vec and evt: # Need event ID for Qdrant Point ID usually, or Object ID
                     # Qdrant PointStruct(id=uuid, vector=vec, payload=payload)
                     # We use object_id as point ID? or Event ID? 
                     # Thesis says "Associative memory". Typically Entity ID.
                     # But one entity has many events.
                     # Usually we store "Memories" (Events or Summary).
                     # Let's use Event ID for unique points in event log vector store.
                     try:
                         point = PointStruct(
                             id=str(evt['id']), 
                             vector=vec, 
                             payload={"content": item.get("original_text"), "object_id": str(evt['object_id'])}
                         )
                         vectors_points.append(point)
                     except Exception as ex:
                         log.error(f"Vector Point creation error: {ex}")

        # ATOMICITY & FAIL CLOSED LOGIC
        # We must succeed in both Postgres and Qdrant, or fail batch.
        # Strict Rule: "Failures are observable and recoverable". "No silent degradation".
        
        try:
            with pg_client.get_cursor() as cur:
                # 2. Postgres Writes (Events)
                if events_data:
                    values = []
                    for e in events_data:
                         values.append((
                             str(e['id']),
                             e['timestamp'],
                             e['actor'],
                             e['action'],
                             str(e['object_id']),
                             json.dumps(e['delta']),
                             json.dumps(e['truth_vector'])
                         ))
                     args_str = ','.join(cur.mogrify("(%s, %s, %s, %s, %s, %s, %s)", x).decode('utf-8') for x in values)
                     # Idempotency: ON CONFLICT DO NOTHING to support Crash Replay
                     cur.execute("INSERT INTO events (id, timestamp, actor, action, object_id, delta, truth_vector) VALUES " + args_str + " ON CONFLICT (id) DO NOTHING")

                # 3. Postgres Writes (Entity State)
                if states_data:
                    for s in states_data:
                        cur.execute("""
                            INSERT INTO entity_state (entity_id, version, current_value, truth_vector, last_event_id, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (entity_id) DO UPDATE SET
                                version = EXCLUDED.version,
                                current_value = EXCLUDED.current_value,
                                truth_vector = EXCLUDED.truth_vector,
                                last_event_id = EXCLUDED.last_event_id,
                                updated_at = EXCLUDED.updated_at
                        """, (
                            str(s['entity_id']),
                            s['version'],
                            json.dumps(s['current_value']),
                            json.dumps(s['truth_vector']),
                            str(s['last_event_id']),
                            s['updated_at']
                        ))
                
                # 4. Qdrant Writes (Inside Postgres Transaction Context?)
                # If Qdrant fails, Postgres will rollback because we are in `with pg_client.get_cursor()`.
                # Wait, Qdrant is external. If Qdrant fails, we raise Exception.
                # `get_cursor` context manager catches exception and calls rollback.
                # So we must do Qdrant write HERE, before the `with` block exits.
                
                if vectors_points:
                    # Strict Mode: Write to Qdrant. If fail, raise.
                    qdrant_client.client.upsert(
                        collection_name="memories",
                        points=vectors_points
                    )
            
            # If we reach here, Postgres commit happened (context manager exit) AND Qdrant succeeded.
            # ACK Scheduler
            if hasattr(sched, 'commit_batch'):
                 sched.commit_batch(batch) # If we implemented this

        except Exception as e:
            log.critical(f"PERSISTENCE FAILURE: Batch Failed. Rolling back. Error: {e}")
            # Fail Closed: We halt.
            # In a real system we might retry or dead-letter.
            # "No silent error logging". We logged CRITICAL.
            # We should probably raise to stop the process or signal health check.
            # For now, we drop the batch if recoverability isn't implemented?
            # User said: "Items are requeued or system halts"
            # We don't have requeue logic easily here without ACKs.
            # We will HALT the consumer to prevent data loss.
            self.running.value = False
            raise e

