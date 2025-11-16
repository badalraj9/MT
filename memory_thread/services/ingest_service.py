import uuid
from datetime import datetime

from memory_thread.models.memory_object import MemoryObject
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.extract_service import extract_structured_data
from memory_thread.services.vector_service import store_vector
from memory_thread.services.graph_service import store_memory_in_graph, create_graph_edges
from memory_thread.utils.embeddings import generate_embedding
# from memory_thread.services.eviction_service import run_eviction_check # To be implemented later

def ingest_text(text: str, importance: float = 0.5):
    """
    Orchestrates the entire ingestion pipeline for a piece of text.

    This follows the steps outlined in the specification:
    1. Normalize (implicitly handled by lowercasing in classify)
    2. Classify (stable vs. temporal, negation)
    3. Field Extraction (NER, LLM)
    4. Domain Detection (placeholder for now, part of timeline service)
    5. Build Memory Object
    6. Generate Embedding
    7. Store in DB (Postgres) + Qdrant
    8. Create Graph Edges
    9. Run Eviction Check (async placeholder)
    """

    # Step 1 & 2: Classify text and detect negation
    # Note: `classify_memory` returns a general type. The final `memory_type` in the
    # object might be refined (e.g., to 'preference' or 'identity') later.
    classified_type, is_negated = classify_memory(text)

    # Step 3: Extract structured data
    extracted_data = extract_structured_data(text)

    # Step 4: Domain detection (to be implemented in timeline_service)
    detected_domain = None # Placeholder

    # Step 5: Build the Memory Object
    now = datetime.utcnow()
    memory_id = str(uuid.uuid4())

    # Step 6: Generate embedding
    embedding = generate_embedding(text)

    memory = MemoryObject(
        id=memory_id,
        content=text,
        # The memory_type will be refined later. For now, we use a placeholder.
        # This will be properly handled when timeline logic is introduced.
        memory_type="event", # Defaulting to 'event' as a safe base type
        extracted=extracted_data,
        importance=importance,
        created_at=now,
        updated_at=now,
        pinned=False,
        domain=detected_domain,
        current_value=None, # To be managed by timeline_service
        history=None,       # To be managed by timeline_service
        embedding=embedding
    )

    # Step 7: Store in Postgres and Qdrant (using placeholders)
    store_memory_in_graph(memory)
    # store_vector(memory) # The vector service needs a Qdrant client, will integrate later.

    # Step 8: Create graph edges (using placeholder)
    create_graph_edges(memory)

    # Step 9: Run eviction check (async, placeholder)
    print(f"Placeholder: Running async eviction check for memory ID {memory.id}.")
    # run_eviction_check(memory)

    return memory
