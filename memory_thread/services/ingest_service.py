import multiprocessing as mp
import time
import struct
import json
from typing import List, Union, Dict
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.services.hybrid_ner_service import extract_entities
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.models.memory_object import MemoryObject, MemoryMetadata
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.vector_service import store_vectors
from memory_thread.services.graph_service import store_memories_batch, create_graph_edges
from memory_thread.utils.logger import get_logger
from memory_thread.utils.shared_cache import result_cache

log = get_logger(__name__)

def worker_process(allocator: SlabAllocator, output_queue: mp.Queue):
    log.info("Worker process started.")
    while True:
        slab = allocator.get_written_slab()
        if slab:
            try:
                # Read 4-byte Length Header
                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]

                # Read Body
                raw_data = slab.memory[4:4+msg_len].tobytes()

                # Determine content type (simple heuristic: starts with { is JSON, else String)
                # Ideally we'd have a type flag in header, but this works for now
                if raw_data.startswith(b'{'):
                    try:
                        content_obj = json.loads(raw_data)
                        text = content_obj.get("content", "")
                        # Could pass full object if we support pre-structured input
                    except json.JSONDecodeError:
                        text = raw_data.decode('utf-8')
                else:
                    text = raw_data.decode('utf-8')

                log.info(f"Worker processing slab {slab.slab_id}: {text[:50]}...")

                # Full processing pipeline
                now = time.time()

                # In Phase 3.4 (TMS), we will replace this simplistic MemoryObject creation
                # with an Event -> TMS Pipeline. For now, we maintain existing logic.
                memory_object = MemoryObject(
                    content=text,
                    memory_type=(classify_memory(text)[0]),
                    importance=0.5,
                    entities=extract_entities(text),
                    topics=[],
                    created_at=now,
                    last_accessed=now,
                    metadata=MemoryMetadata(source="user", negation=classify_memory(text)[1])
                )

                # Phase 3.4 Optimization: Move embedding to separate process?
                # For now, keep here as per current architecture.
                embedding = generate_embeddings((text,))[0]
                memory_object.embedding = embedding

                output_queue.put(memory_object)
                allocator.release_slab(slab.slab_id)
            except Exception as e:
                log.error(f"Error processing slab {slab.slab_id}: {e}")
                allocator.release_slab(slab.slab_id) # Ensure slab is released on error
        else:
            time.sleep(0.001) # Yield CPU

class IngestionService:
    def __init__(self, num_slabs=128, slab_size=65536): # Increased to 64KB for safety
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self.output_queue = mp.Queue()
        self.workers = []
        self.db_writer_process = mp.Process(target=self.db_writer_worker)

    def db_writer_worker(self):
        log.info("DB writer process started.")
        batch = []
        while True:
            try:
                obj = self.output_queue.get(timeout=1)
                if obj is None: break
                batch.append(obj)
                if len(batch) >= 32: # Batch size
                    store_vectors(batch)
                    store_memories_batch(batch)
                    for mem in batch:
                        create_graph_edges(mem)
                    batch = []
            except mp.queues.Empty:
                if batch:
                    store_vectors(batch)
                    store_memories_batch(batch)
                    for mem in batch:
                        create_graph_edges(mem)
                    batch = []
                continue

    def start(self):
        if not self.db_writer_process.is_alive():
            self.db_writer_process.start()

        # Clear existing workers if any (restart logic)
        for p in self.workers:
            if p.is_alive(): p.terminate()
        self.workers = []

        for _ in range(max(1, mp.cpu_count() - 2)): # Leave 1 for API, 1 for DB Writer
            p = mp.Process(target=worker_process, args=(self.allocator, self.output_queue))
            p.start()
            self.workers.append(p)
        log.info(f"Started {len(self.workers)} worker processes.")

    def ingest_texts(self, texts: List[Union[str, Dict]]):
        import hashlib
        for item in texts:
            # Handle both strings and dicts (future-proofing for Phase 3.4 events)
            if isinstance(item, dict):
                text_content = item.get("content", str(item))
                encoded_data = json.dumps(item).encode('utf-8')
            else:
                text_content = item
                encoded_data = item.encode('utf-8')

            text_hash = hashlib.sha256(text_content.encode()).hexdigest()
            if text_hash in result_cache:
                log.info(f"Cache hit for text: {text_content[:30]}...")
                continue

            msg_len = len(encoded_data)
            if msg_len + 4 > self.allocator.slab_size:
                log.warning(f"Data too large for slab ({msg_len} > {self.allocator.slab_size}), skipping.")
                continue

            slab = self.allocator.reserve_slab()
            # Write Header (4 bytes)
            slab.memory[:4] = struct.pack("!I", msg_len)
            # Write Body
            slab.memory[4:4+msg_len] = encoded_data

            self.allocator.mark_as_written(slab.slab_id)
            result_cache.set(text_hash, True)
            # log.info(f"Wrote to slab {slab.slab_id}.")

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
