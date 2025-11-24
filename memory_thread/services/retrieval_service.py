import logging
from datetime import datetime
from memory_thread.services.vector_service import search_vectors
from memory_thread.services.graph_service import get_neighbors
from memory_thread.utils.embeddings import generate_embedding
from memory_thread.config.settings import settings

log = logging.getLogger(__name__)

def retrieve_memories(query: str, top_k: int = 10) -> list:
    """
    Retrieves the most relevant memories for a given query, following the
    specified 3-step retrieval and scoring algorithm.
    """
    # Step 1: Vector Search (get top-40 candidates)
    query_embedding = generate_embedding(query)
    initial_candidates = search_vectors(query_embedding, top_k=40)

    if not initial_candidates:
        return []

    # Step 2: Graph Refinement & Scoring
    scored_candidates = {}
    now = datetime.utcnow()

    for candidate in initial_candidates:
        memory_id = candidate.id

        # Fetch neighbors from the graph
        neighbors = get_neighbors(memory_id)

        # Calculate combined score
        vector_similarity = candidate.score

        # Placeholder for edge weight and importance until fully implemented
        # In a real scenario, these would come from the database payload/edge data
        edge_weight_sum = sum(neighbor.get('weight', 0.0) for neighbor in neighbors)
        importance = candidate.payload.get('importance', 0.5)

        # Recency decay calculation
        created_at_ts = candidate.payload.get('created_at')
        if created_at_ts:
            created_at_dt = datetime.fromtimestamp(created_at_ts)
            days_since_creation = (now - created_at_dt).days
            recency_decay = 0.99 ** days_since_creation # Simple exponential decay
        else:
            recency_decay = 0.5

        # Final score calculation based on the specification's formula
        final_score = (
            0.6 * vector_similarity +
            0.2 * (edge_weight_sum / MAX_EDGES_PER_NODE if neighbors else 0) + # Normalize edge weight
            0.1 * importance +
            0.1 * recency_decay
        )

        scored_candidates[memory_id] = {
            "score": final_score,
            "content": candidate.payload.get('content', ''), # Assuming content is in payload
            "memory_type": candidate.payload.get('memory_type', 'unknown')
        }

    # Step 3: Sort and Return Top-K
    sorted_memories = sorted(scored_candidates.values(), key=lambda x: x['score'], reverse=True)

    return sorted_memories[:top_k]
