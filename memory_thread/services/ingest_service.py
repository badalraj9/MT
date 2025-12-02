import multiprocessing as mp
import time
from typing import List
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
                # Assuming the data is a utf-8 encoded string
                text = slab.memory.tobytes().decode('utf-8').strip('\x00')
                log.info(f"Worker processing slab {slab.slab_id}: {text}")

                # Full processing pipeline
                now = time.time()
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
                embedding = generate_embeddings((text,))[0]
                memory_object.embedding = embedding

                output_queue.put(memory_object)
                allocator.release_slab(slab.slab_id)
            except Exception as e:
                log.error(f"Error processing slab {slab.slab_id}: {e}")
                allocator.release_slab(slab.slab_id) # Ensure slab is released on error
        else:
            time.sleep(0.01) # No work to do, sleep a bit

class IngestionService:
    def __init__(self, num_slabs=128, slab_size=4096):
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
        self.db_writer_process.start()
        for _ in range(mp.cpu_count() - 1):
            p = mp.Process(target=worker_process, args=(self.allocator, self.output_queue))
            p.start()
            self.workers.append(p)
        log.info(f"Started {len(self.workers)} worker processes.")

    def ingest_texts(self, texts: List[str]):
        import hashlib
        for text in texts:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            if text_hash in result_cache:
                log.info(f"Cache hit for text: {text}")
                continue

            encoded_text = text.encode('utf-8')
            if len(encoded_text) >= self.allocator.slab_size:
                log.warning(f"Text too large for slab, skipping: {text[:100]}...")
                continue

            slab = self.allocator.reserve_slab()
            slab.memory[:len(encoded_text)] = encoded_text
            self.allocator.mark_as_written(slab.slab_id)
            result_cache.set(text_hash, True) # Mark as in-flight/processed
            log.info(f"Wrote to slab {slab.slab_id}.")

    def shutdown(self):
        self.output_queue.put(None)
        self.db_writer_process.join()
        for p in self.workers:
            p.terminate()
            p.join()
        self.allocator.unlink()

# Global instance
ingestion_service = IngestionService()
