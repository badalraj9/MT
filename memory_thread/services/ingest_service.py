from datetime import datetime
import logging

from memory_thread.models.memory_object import MemoryObject, MemoryMetadata
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.extract_service import extract_structured_data
from memory_thread.services.vector_service import store_vector
from memory_thread.services.graph_service import store_memory_in_graph, create_graph_edges
from memory_thread.utils.embeddings import generate_embedding

log = logging.getLogger(__name__)

def ingest_text(text: str, importance: float = 0.5, source: str = "user"):
    """
    Orchestrates the ingestion pipeline, creating a MemoryObject aligned with
    the new plugin manifest schema.
    """
    now = datetime.utcnow()

    # Step 1 & 2: Classify text and detect negation
    classified_type, is_negated = classify_memory(text)

    # Step 3: Extract structured data
    extracted_data = extract_structured_data(text)

    # Step 4: Generate embedding
    embedding = generate_embedding(text)

    # Step 5: Build the MemoryObject
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
        metadata=metadata,
        embedding=embedding
    )

    # Future: Handle timeline logic here
    # if classified_type in ["preference", "timeline_update"]:
    #     manage_preference_timeline(memory)
    #     return memory

    # Step 6: Store in Postgres and Qdrant
    store_memory_in_graph(memory)
    store_vector(memory)

    # Step 7: Create graph edges (placeholder)
    create_graph_edges(memory)

    return memory
