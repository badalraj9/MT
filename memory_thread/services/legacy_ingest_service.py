import hashlib
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import logging
from typing import List
from memory_thread.models.memory_object import MemoryObject, MemoryMetadata
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.hybrid_ner_service import extract_entities
from memory_thread.services.vector_service import store_vectors
from memory_thread.services.graph_service import store_memories_batch, create_graph_edges
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.utils.caching import result_cache
log = logging.getLogger(__name__)

# --- Worker Process ---
def worker_process_chunk(texts: List[str], importance: float = 0.5, source: str = "user"):
    processed_objects = []
    for text in texts:
        now = datetime.utcnow()
        memory_object = MemoryObject(content=text, memory_type=(classified_type := classify_memory(text)[0]), importance=importance, entities=extract_entities(text), topics=[], created_at=now, last_accessed=now, metadata=MemoryMetadata(source=source, negation=classify_memory(text)[1]))
        embedding = generate_embeddings((memory_object.content,))[0]
        memory_object.embedding = embedding
        processed_objects.append(memory_object)
    return processed_objects

# --- Ingestion Service (Legacy) ---
class LegacyIngestionService:
    def __init__(self):
        self.pool = ProcessPoolExecutor(max_workers=mp.cpu_count() - 1)
        self.output_queue = mp.Queue()
        self.db_writer_process = mp.Process(target=self.db_writer_worker)
        self.db_writer_process.start()

    def db_writer_worker(self):
        while True:
            try:
                memory_objects = self.output_queue.get(timeout=1.0)
                if memory_objects is None: # Sentinel for shutdown
                    break
                store_vectors(memory_objects)
                store_memories_batch(memory_objects)
                for mem in memory_objects:
                    create_graph_edges(mem)
            except mp.queues.Empty:
                continue

    def ingest_texts(self, texts: List[str], importance: float = 0.5, source: str = "user"):
        texts_to_process = []
        for text in texts:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            if text_hash in result_cache:
                continue
            texts_to_process.append(text)
            result_cache[text_hash] = True

        if not texts_to_process:
            return []

        chunk_size = 100
        chunks = [texts_to_process[i:i + chunk_size] for i in range(0, len(texts_to_process), chunk_size)]

        futures = [self.pool.submit(worker_process_chunk, chunk, importance, source) for chunk in chunks]

        all_results = []
        for future in futures:
            processed_objects = future.result()
            if processed_objects:
                all_results.extend(processed_objects)

        if all_results:
            self.output_queue.put(all_results)

        return all_results

    def shutdown(self):
        self.output_queue.put(None)
        self.db_writer_process.join()
        self.pool.shutdown()

legacy_ingest_service = LegacyIngestionService()
