import hashlib
import multiprocessing as mp
import zmq
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import logging
import zlib
from typing import List
from memory_thread.models.memory_object import MemoryObject, MemoryMetadata
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.hybrid_ner_service import extract_entities
from memory_thread.services.vector_service import store_vectors
from memory_thread.services.graph_service import store_memories_batch, create_graph_edges
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.utils.caching import result_cache
from memory_thread.utils.shared_memory import SharedMemoryRingBuffer
log = logging.getLogger(__name__)

# --- Worker Process ---
def worker_process(shared_memory_name, size, zmq_push_address):
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(zmq_push_address)

    shm = mp.shared_memory.SharedMemory(name=shared_memory_name)
    ring_buffer = SharedMemoryRingBuffer(size_bytes=size, shm=shm)

    while True:
        data = ring_buffer.read(1024) # Read in chunks
        if not data:
            continue

        message = data.decode('utf-8')
        route, text = message.split("::", 1)

        now = datetime.utcnow()

        # Adaptive pipeline based on route
        entities = extract_entities(text)
        embedding = None
        if route == "NATURAL":
            embedding = generate_embeddings((text,))[0]
        elif route == "COMPLEX":
            embedding = generate_embeddings((text,))[0]

        memory_object = MemoryObject(content=text, memory_type=(classified_type := classify_memory(text)[0]), importance=0.5, entities=entities, topics=[], created_at=now, last_accessed=now, metadata=MemoryMetadata(source="user", negation=classify_memory(text)[1]))
        if embedding:
            memory_object.embedding = embedding

        socket.send_pyobj(memory_object)

# --- Ingestion Service ---
class IngestionService:
    def __init__(self):
        self.ring_buffer = SharedMemoryRingBuffer(size_bytes=1024 * 1024 * 100) # 100MB buffer
        self.zmq_context = zmq.Context()
        self.zmq_pull_address = "inproc://db_writer"
        self.consumers = []
        self.db_writer_process = mp.Process(target=self.db_writer_worker)
        self.db_writer_process.start()
        self.start_consumers()

    def db_writer_worker(self):
        socket = self.zmq_context.socket(zmq.PULL)
        socket.bind(self.zmq_pull_address)

        while True:
            memory_object = socket.recv_pyobj()
            if memory_object is None: # Sentinel for shutdown
                break
            store_vectors([memory_object])
            store_memories_batch([memory_object])
            create_graph_edges(memory_object)

    def start_consumers(self):
        for _ in range(mp.cpu_count() - 1):
            p = mp.Process(target=worker_process, args=(self.ring_buffer.shm.name, self.ring_buffer.size_bytes, self.zmq_pull_address))
            p.start()
            self.consumers.append(p)

    def ingest_texts(self, texts: List[str], importance: float = 0.5, source: str = "user"):
        from memory_thread.services.routing_service import route_text
        for text in texts:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            if text_hash in result_cache:
                log.info(f"Cache hit for text: {text}")
                continue

            route = route_text(text)
            # Pass text and route to worker via shared memory
            # For simplicity, we'll encode them with a separator
            message = f"{route}::{text}"
            self.ring_buffer.write(message.encode('utf-8'))
            result_cache[text_hash] = True

        log.info(f"Wrote {len(texts)} texts to the ring buffer.")
        return []

    def shutdown(self):
        # Send shutdown signal to DB writer
        shutdown_socket = self.zmq_context.socket(zmq.PUSH)
        shutdown_socket.connect(self.zmq_pull_address)
        shutdown_socket.send_pyobj(None)
        shutdown_socket.close()

        self.db_writer_process.join()
        for p in self.consumers:
            p.terminate()
            p.join()
        self.ring_buffer.close()

ingest_service = IngestionService()
