import multiprocessing as mp
import time
import struct
import json
import uuid
from typing import List, Union, Dict
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.services.hybrid_ner_service import extract_entities
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.models.events import Event, EntityState, ActorEnum, ActionEnum
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.utils.logger import get_logger
from memory_thread.utils.shared_cache import result_cache

log = get_logger(__name__)

def worker_process(allocator: SlabAllocator, output_queue: mp.Queue):
    log.info("Worker process started.")

    # Initialize Services
    tms_service = TMSService()
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
                text = ""

                if raw_data.startswith(b'{'):
                    try:
                        content_obj = json.loads(raw_data)
                        text = content_obj.get("content", "")
                    except json.JSONDecodeError:
                        text = raw_data.decode('utf-8')
                else:
                    text = raw_data.decode('utf-8')

                log.info(f"Worker processing slab {slab.slab_id}: {text[:30]}...")

                # 2. META-STABILITY CHECK (Layer 0)
                # Check for rate limiting or anomalies (mock call)
                if meta_service.check_drift(text, domain="general"):
                    log.warning("Drift detected, quarantining event.")
                    # Continue but flag? Or skip? For now, proceed.

                # 3. TMS PIPELINE (Layer 1 -> Layer 2)
                # Parse action/delta from input or infer it
                # For Phase 3.4, we support explicit Event objects in JSON
                # or infer from text (simulated).

                if "action" in content_obj and "delta" in content_obj:
                    # Explicit Event Mode
                    action = ActionEnum[content_obj.get("action", "UPDATE")]
                    delta = content_obj.get("delta", {})
                    object_id_str = content_obj.get("object_id")
                    object_id = uuid.UUID(object_id_str) if object_id_str else uuid.uuid4()
                else:
                    # Infer Mode (Legacy Text Support)
                    # "User added 500 trees" -> action=ADD, delta={tree_count: 500}
                    # Mock inference for benchmark compatibility
                    action = ActionEnum.UPDATE
                    delta = {"content": text}
                    object_id = uuid.uuid4()

                # Layer 1: Create Event
                event = tms_service.create_event(
                    actor=ActorEnum.USER,
                    action=action,
                    object_id=object_id,
                    delta=delta
                )

                # Layer 2: Derive State (Mock fetch of current state T=0)
                # Real app would fetch from DB
                current_state = EntityState(
                    entity_id=object_id,
                    namespace="user",
                    current_value={}, # Empty initial state
                    truth_vector=event.truth_vector,
                    last_event_id=uuid.uuid4()
                )

                new_state = StateDerivationService.apply_event(current_state, event)

                # Check Integrity
                if not meta_service.check_integrity(new_state):
                    log.error("State integrity check failed!")

                # 4. OUTPUT (Send to DB Writer)
                # We package the TMS artifacts to queue
                output_payload = {
                    "event": event,
                    "state": new_state,
                    "original_text": text
                }

                # Embedding (Optional/Legacy support)
                # embedding = generate_embeddings((text,))[0]
                # output_payload["embedding"] = embedding

                output_queue.put(output_payload)
                allocator.release_slab(slab.slab_id)
            except Exception as e:
                log.error(f"Error processing slab {slab.slab_id}: {e}")
                allocator.release_slab(slab.slab_id)
        else:
            time.sleep(0.001)

class IngestionService:
    def __init__(self, num_slabs=128, slab_size=65536):
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self.output_queue = mp.Queue()
        self.workers = []
        # DB Writer needs update to handle TMS payload, but for benchmark we focus on Pipeline Throughput
        self.db_writer_process = mp.Process(target=self.db_writer_worker)

    def db_writer_worker(self):
        log.info("DB writer process started.")
        while True:
            try:
                obj = self.output_queue.get(timeout=1)
                if obj is None: break
                # Mock DB Write for TMS objects
                # In real Phase 3.4, we INSERT INTO events, entity_state
                pass
            except mp.queues.Empty:
                continue

    def start(self):
        if not self.db_writer_process.is_alive():
            self.db_writer_process.start()
        for p in self.workers:
            if p.is_alive(): p.terminate()
        self.workers = []
        for _ in range(max(1, mp.cpu_count() - 2)):
            p = mp.Process(target=worker_process, args=(self.allocator, self.output_queue))
            p.start()
            self.workers.append(p)
        log.info(f"Started {len(self.workers)} worker processes.")

    def ingest_texts(self, texts: List[Union[str, Dict]]):
        import hashlib
        for item in texts:
            if isinstance(item, dict):
                # Ensure JSON serializable
                # For UUIDs in dicts, convert to str
                def json_serial(obj):
                    if isinstance(obj, (datetime.datetime, datetime.date)):
                        return obj.isoformat()
                    if isinstance(obj, uuid.UUID):
                        return str(obj)
                    raise TypeError (f"Type {type(obj)} not serializable")

                text_content = str(item) # Hash source
                encoded_data = json.dumps(item, default=json_serial).encode('utf-8')
            else:
                text_content = item
                encoded_data = item.encode('utf-8')

            text_hash = hashlib.sha256(text_content.encode()).hexdigest()
            # Cache logic skipped for benchmark throughput focus

            msg_len = len(encoded_data)
            if msg_len + 4 > self.allocator.slab_size:
                continue

            slab = self.allocator.reserve_slab()
            slab.memory[:4] = struct.pack("!I", msg_len)
            slab.memory[4:4+msg_len] = encoded_data
            self.allocator.mark_as_written(slab.slab_id)

    def shutdown(self):
        self.output_queue.put(None)
        if self.db_writer_process.is_alive():
            self.db_writer_process.join()
        for p in self.workers:
            p.terminate()
            p.join()
        self.allocator.unlink()

# Global instance
ingestion_service = IngestionService()
