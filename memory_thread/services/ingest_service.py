import multiprocessing as mp
import time
import struct
import json
import uuid
import datetime
from typing import List, Union, Dict, Any
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.services.hybrid_ner_service import extract_entities
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.models.events import Event, EntityState, ActorEnum, ActionEnum
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.utils.logger import get_logger
from memory_thread.utils.shared_cache import result_cache
from memory_thread.nervous.persistence_engine import PersistenceEngine

log = get_logger(__name__)

# Function to handle JSON serialization for non-standard types
def json_serial(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "dict"): # Pydantic models
        return obj.dict()
    raise TypeError(f"Type {type(obj)} not serializable")


    log.info("Worker process started.")

    tms_service = TMSService()
    meta_service = MetaStabilityService()
    
    # 5. Ingest Envelope
    NAMESPACE_MT = uuid.uuid5(uuid.NAMESPACE_DNS, "memory_thread.ai")

    try:
        while not shutdown_event.is_set():
            slab = allocator.get_written_slab()
            if slab:
                try:
                    # 1. READ (Length-Header Protocol)
                    header = slab.memory[:4].tobytes()
                    msg_len = struct.unpack("!I", header)[0]
                    raw_data = slab.memory[4:4+msg_len].tobytes()

                    content_obj = {}
                    text = ""

                    if raw_data.startswith(b'{'):
                        try:
                            content_obj = json.loads(raw_data)
                            text = content_obj.get("content", "")
                        except json.JSONDecodeError:
                            text = raw_data.decode('utf-8')
                    else:
                        text = raw_data.decode('utf-8')

                    # 2. META-STABILITY CHECK (Layer 0)
                    drift_decision = meta_service.check_drift(text, domain="general")
                    if not drift_decision.allowed:
                        log.warning(f"Drift/Stability Rejection: {drift_decision.reason}. Quarantining.")
                        # Strict Hardening: REJECT or QUARANTINE.
                        # We release slab and CONTINUE (Drop Event from Pipeline but Log it).
                        # "Route to quarantine channel" -> In real app, write to 'quarantine' queue.
                        # For Phase 6 Prototype: We drop and log.
                        allocator.release_slab(slab.slab_id)
                        continue
                    
                    # If allowed but low confidence?
                    if drift_decision.confidence < 0.5:
                         log.info(f"Low Confidence Ingestion: {drift_decision.reason}")

                    # 3. TMS PIPELINE (Layer 1 -> Layer 2)
                    if "action" in content_obj and "delta" in content_obj:
                        action = ActionEnum[content_obj.get("action", "UPDATE")]
                        delta = content_obj.get("delta", {})
                    else:
                        action = ActionEnum.UPDATE
                        delta = {"content": text}
                    
                    # 1. Identity & Determinism
                    # Remove uuid.uuid4(). Derive from content hash.
                    import hashlib
                    # content hash incl action and delta for uniqueness per ingestion
                    content_hash = hashlib.sha256(json.dumps({
                        "text": text, 
                        "action": action.value, 
                        "delta": json.dumps(delta, default=json_serial)
                    }).encode()).hexdigest()
                    
                    # Timestamp seed to distinguish identical events at different times?
                    # "Same input + same state -> same output"
                    # If user sends "Hi" twice, should it be same event ID?
                    # Determinism says YES if stateless. 
                    # But memory is stateful. Time matters.
                    # Requirement: "Content hash OR upstream provided ID"
                    # If upstream ID provided, use it. Else, generate from Content + Time or just Content?
                    # "No random UUIDs where identity matters"
                    # Let's use Content Hash. If duplicates arrive, they are idempotent?
                    # Or do we mix in ingest timestamp?
                    # Let's use Content Hash + Ingest Timestamp (ns) to ensure uniqueness if intended, 
                    # or pure Content Hash if idempotency desired.
                    # Given "Memory is a Function of Time", time is input.
                    
                    # object_id derivation:
                    # If provided in input, use it (must be deterministic upstream).
                    # Else, derive from content hash.
                    
                    provided_oid = content_obj.get("object_id")
                    if provided_oid:
                         object_id = uuid.UUID(provided_oid)
                    else:
                         # Deterministic Entity ID from content? 
                         # Usually entity ID is persistent. If new, generate.
                         # We'll generate a deterministic ID from content hash for this session/context.
                         object_id = uuid.uuid5(NAMESPACE_MT, content_hash)
                    
                    # Deterministic Event ID
                    # Derive from Unique Content Hash (which includes time if we want temporal uniqueness, or just content for deduplication)
                    # "Same input + same state -> same output"
                    # We utilize content_hash which includes action/delta/text. 
                    event_id = uuid.uuid5(NAMESPACE_MT, content_hash)
                    
                    # Explicit Timestamp Injection
                    ingest_ts = datetime.datetime.utcnow()

                    event = tms_service.create_event(
                        actor=ActorEnum.USER,
                        action=action,
                        object_id=object_id,
                        delta=delta,
                        namespace="user",
                        event_id=event_id,
                        timestamp=ingest_ts
                    )

                    current_state = EntityState(
                        entity_id=object_id,
                        namespace="user",
                        current_value={},
                        truth_vector=event.truth_vector,
                        last_event_id=event.id, # Linkage
                        updated_at=ingest_ts
                    )

                    new_state = StateDerivationService.apply_event(current_state, event, updated_at=ingest_ts)

                    if not meta_service.check_integrity(new_state):
                        log.error("State integrity check failed!")
                        allocator.release_slab(slab.slab_id)
                        continue

                    # 4. OUTPUT TO ZMQ (Q2 -> Q3)
                    # Hardening: Generate Vector for Qdrant Storage
                    # Must allow exception to propagate (Fail Closed)
                    vector = generate_embeddings(text)[0] 

                    # 5. Ingest Envelope
                    envelope = {
                        "ingest_id": str(uuid.uuid5(NAMESPACE_MT, event.id.hex)), # Linear linkage
                        "ingest_ts": datetime.datetime.utcnow().isoformat(),
                        "source": "ingest_service",
                        "event": event.dict(),
                        "state": new_state.dict(),
                        "vector": vector,
                        "meta": {
                            "replayed": False,
                            "determinism_hash": content_hash
                        }
                    }

                    # Serialize properly for ZMQ
                    qm.send(json.loads(json.dumps(envelope, default=json_serial)))

                    allocator.release_slab(slab.slab_id)
                except Exception as e:
                    log.error(f"Error processing slab {slab.slab_id}: {e}")
                    # Release slab so we don't leak memory, BUT we dropped data.
                    # Strict Mode: Halt worker? 
                    # "Partial success = failure".
                    # We logged error. Use 'persistence_engine' to maybe log fatal error?
                    allocator.release_slab(slab.slab_id)
            else:
                time.sleep(0.001)

    qm.close()

class IngestionService:
    def __init__(self, num_slabs=128, slab_size=65536):
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self.workers = []
        self.shutdown_event = mp.Event()
        # Phase 3.5: Use Persistence Engine instead of mp.Queue writer
        self.persistence_engine = PersistenceEngine()

    def start(self):
        self.persistence_engine.start()

        for p in self.workers:
            if p.is_alive(): p.terminate()
        self.workers = []

        for _ in range(max(1, mp.cpu_count() - 2)):
            # Workers self-initialize ZMQ producers
            # Pass shutdown_event
            p = mp.Process(target=worker_process, args=(self.allocator, None, self.shutdown_event))
            p.start()
            self.workers.append(p)
        log.info(f"Started {len(self.workers)} worker processes.")

    def ingest_texts(self, texts: List[Union[str, Dict]]):
        import hashlib
        for item in texts:
            if isinstance(item, dict):
                text_content = str(item)
                encoded_data = json.dumps(item, default=json_serial).encode('utf-8')
            else:
                text_content = item
                encoded_data = item.encode('utf-8')

            text_hash = hashlib.sha256(text_content.encode()).hexdigest()

            msg_len = len(encoded_data)
            if msg_len + 4 > self.allocator.slab_size:
                continue

            slab = self.allocator.reserve_slab()
            slab.memory[:4] = struct.pack("!I", msg_len)
            slab.memory[4:4+msg_len] = encoded_data
            self.allocator.mark_as_written(slab.slab_id)

    def shutdown(self):
        self.persistence_engine.stop()
        self.shutdown_event.set()
        for p in self.workers:
            p.join()
        self.allocator.unlink()

# Global instance
ingestion_service = IngestionService()
