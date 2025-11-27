from datetime import datetime
import logging
from typing import List

from memory_thread.models.memory_object import MemoryObject, MemoryMetadata
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.extract_service import extract_structured_data
from memory_thread.services.vector_service import store_vectors
from memory_thread.services.graph_service import store_memory_in_graph, create_graph_edges
from memory_thread.utils.embeddings import generate_embeddings

log = logging.getLogger(__name__)

def ingest_texts(texts: List[str], importance: float = 0.5, source: str = "user"):
    """
    Orchestrates the batch ingestion pipeline for a list of texts.
    """
    now = datetime.utcnow()
    memory_objects = []

    # Step 1-5: Process each text into a MemoryObject (without embedding yet)
    for text in texts:
        classified_type, is_negated = classify_memory(text)
        extracted_data = extract_structured_data(text)

        metadata = MemoryMetadata(
            source=source,
            negation=is_negated,
            **extracted_data.get("metadata", {})
        )

        memory = MemoryObject(
            content=text,
            memory_type=classified_type,
            importance=importance,
            entities=extracted_data.get("entities", []),
            topics=extracted_data.get("topics", []),
            created_at=now,
            last_accessed=now,
            metadata=metadata
        )
        memory_objects.append(memory)

    # Step 6: Generate embeddings in a single batch
    content_tuple = tuple(mem.content for mem in memory_objects)
    embeddings = generate_embeddings(content_tuple)
    for mem, emb in zip(memory_objects, embeddings):
        mem.embedding = emb

    # Step 7: Store in databases
    # Qdrant is updated to handle batches
    store_vectors(memory_objects)

    # Postgres is still one-by-one, but can be batched with psycopg2.extras.execute_batch
    # For now, we loop to keep it simple.
    for mem in memory_objects:
        store_memory_in_graph(mem)
        create_graph_edges(mem) # Still a placeholder

    log.info(f"Successfully processed and stored a batch of {len(memory_objects)} memories.")
    return memory_objects
