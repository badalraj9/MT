from datetime import datetime
import logging
from typing import List
from memory_thread.models.memory_object import MemoryObject, MemoryMetadata
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.extract_service import extract_structured_data
from memory_thread.services.vector_service import store_vectors
from memory_thread.services.graph_service import store_memories_batch, create_graph_edges
from memory_thread.utils.embeddings import generate_embeddings
log = logging.getLogger(__name__)
def ingest_texts(texts: List[str], importance: float = 0.5, source: str = "user"):
    now = datetime.utcnow()
    memory_objects = [MemoryObject(content=text, memory_type=(classified_type := classify_memory(text)[0]), importance=importance, entities=(extracted := extract_structured_data(text)).get("entities", []), topics=extracted.get("topics", []), created_at=now, last_accessed=now, metadata=MemoryMetadata(source=source, negation=classify_memory(text)[1], **extracted.get("metadata", {}))) for text in texts]
    embeddings = generate_embeddings(tuple(mem.content for mem in memory_objects))
    for mem, emb in zip(memory_objects, embeddings): mem.embedding = emb

    store_vectors(memory_objects)
    store_memories_batch(memory_objects)

    for mem in memory_objects:
        create_graph_edges(mem)

    log.info(f"Processed batch of {len(memory_objects)} memories.")
    return memory_objects
