import multiprocessing as mp
import time
import struct
import json
import uuid
from datetime import datetime, timezone
from typing import List, Union, Dict, Any
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.models.events import Event, EntityState, ActorEnum, ActionEnum, DeltaPatch, DeltaOp, TruthVector, Provenance
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.utils.logger import get_logger
from memory_thread.nervous.persistence_engine import PersistenceEngine

log = get_logger(__name__)

# Function to handle JSON serialization for non-standard types
def json_serial(obj):
    if isinstance(obj, (datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "dict"): # Pydantic models
        return obj.dict()
    raise TypeError(f"Type {type(obj)} not serializable")

def worker_process(allocator: SlabAllocator, persistence_engine: Any):
    from memory_thread.nervous.queue_manager import QueueManager
    qm = QueueManager(address="ipc://persistence_pipe")
    qm.setup_producer()

    log.info("Worker process started.")
    meta_service = MetaStabilityService()

    while True:
        slab = allocator.get_written_slab()
        if slab:
            try:
                # 1. READ (Length-Header Protocol)
                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]
                raw_data = slab.memory[4:4+msg_len].tobytes()

                content_obj = {}

                # Strict expectation: Data MUST be a serialized EVENT dict from Gateway
                # Raw text ingestion is no longer supported at this layer.
                # The Gateway must have already converted it.
                try:
                    content_obj = json.loads(raw_data)
                except json.JSONDecodeError:
                    log.error("Ingestion Worker received non-JSON data. Dropping.")
                    allocator.release_slab(slab.slab_id)
                    continue

                # 2. REHYDRATE EVENT
                try:
                     # Helper to parse fields safely
                     if isinstance(content_obj.get("delta"), list):
                         deltas = [DeltaPatch(**d) for d in content_obj.get("delta")]
                     else:
                         deltas = []

                     event = Event(
                        id=uuid.UUID(content_obj['id']),
                        namespace=content_obj['namespace'],
                        timestamp=datetime.fromisoformat(content_obj['timestamp']),
                        actor=ActorEnum(content_obj['actor']),
                        action=ActionEnum(content_obj['action']),
                        object_id=uuid.UUID(content_obj['object_id']),
                        delta=deltas,
                        truth_vector=TruthVector(**content_obj['truth_vector']),
                        provenance=Provenance(**content_obj['provenance']) if content_obj.get('provenance') else None
                     )
                except Exception as e:
                    log.error(f"Failed to rehydrate event in worker: {e}")
                    allocator.release_slab(slab.slab_id)
                    continue

                # 3. META-STABILITY CHECK (Layer 0)
                # We check the content/delta
                # drift_check = meta_service.check_drift(str(event.delta), domain="general")

                # 4. TMS STATE DERIVATION
                # We need the PREVIOUS state to derive the NEW state.
                # In a distributed worker, we can't easily fetch DB state synchronously without slowing down.
                # Typically, workers just log the event, and a separate 'Projector' or 'Consumer' updates the read model.
                # However, for Phase 3.4 logic "Layers 1->2", we calculate it here.
                # We will mock the "Current State" as empty for now, assuming this is an ADD or new entity
                # OR, we should rely on a StateStore.get_state(event.object_id)

                # Mock current state fetching for the purpose of derivation check
                current_state = EntityState(
                    entity_id=event.object_id,
                    namespace=event.namespace,
                    current_value={},
                    truth_vector=event.truth_vector, # Inherit for seed
                    last_event_id=event.id, # Point to itself if new
                    updated_at=event.timestamp,
                    version=0
                )

                new_state = StateDerivationService.apply_event(current_state, event)

                if not meta_service.check_integrity(new_state):
                    log.error("State integrity check failed!")

                # 5. OUTPUT TO ZMQ
                output_payload = {
                    "event": event.dict(),
                    "state": new_state.dict()
                }

                qm.send(json.loads(json.dumps(output_payload, default=json_serial)))

                allocator.release_slab(slab.slab_id)
            except Exception as e:
                log.error(f"Error processing slab {slab.slab_id}: {e}")
                allocator.release_slab(slab.slab_id)
        else:
            time.sleep(0.001)

    qm.close()

class IngestionService:
    def __init__(self, num_slabs=128, slab_size=65536):
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self.workers = []
        self.persistence_engine = PersistenceEngine()

    def start(self):
        self.persistence_engine.start()

        for p in self.workers:
            if p.is_alive(): p.terminate()
        self.workers = []

        for _ in range(max(1, mp.cpu_count() - 2)):
            p = mp.Process(target=worker_process, args=(self.allocator, None))
            p.start()
            self.workers.append(p)
        log.info(f"Started {len(self.workers)} worker processes.")

    def ingest_event_dict(self, event_dict: Dict[str, Any]):
        """
        Accepts a pre-validated Event dictionary (from Gateway).
        """
        encoded_data = json.dumps(event_dict, default=json_serial).encode('utf-8')

        msg_len = len(encoded_data)
        if msg_len + 4 > self.allocator.slab_size:
            log.error("Event too large for slab")
            return

        slab = self.allocator.reserve_slab()
        slab.memory[:4] = struct.pack("!I", msg_len)
        slab.memory[4:4+msg_len] = encoded_data
        self.allocator.mark_as_written(slab.slab_id)

    def shutdown(self):
        self.persistence_engine.stop()
        for p in self.workers:
            p.terminate()
            p.join()
        self.allocator.unlink()

# Global instance
ingestion_service = IngestionService()
