import logging
from datetime import datetime
from uuid import UUID
from memory_thread.services.vector_service import search_vectors
from memory_thread.services.graph_service import get_neighbors, get_memories_by_ids, keyword_search_memories
from memory_thread.utils.embeddings import generate_embedding
from memory_thread.config.settings import settings

log = logging.getLogger(__name__)

def retrieve_memories(query: str, top_k: int = 10) -> list:
    """
    Retrieves memories using a hybrid keyword + vector search, then re-ranks.
    """
    # Step 1: Parallel Search
    query_embedding = generate_embedding(query)
    vector_candidates = search_vectors(query_embedding, top_k=40)
    keyword_candidates = keyword_search_memories(query, top_k=20)

    # Step 2: Merge and Hydrate
    # Combine IDs, ensuring uniqueness
    candidate_ids = {UUID(c.id) for c in vector_candidates}
    keyword_scores = {res['id']: res['keyword_score'] for res in keyword_candidates}
    for res in keyword_candidates:
        candidate_ids.add(res['id'])

    if not candidate_ids:
        return []

    # Fetch full memory objects for all unique candidates
    memories_data = get_memories_by_ids(list(candidate_ids))
    if not memories_data:
        return []

    # Step 3: Graph Refinement & Hybrid Scoring
    scored_memories = []
    now = datetime.utcnow()
    vector_scores = {UUID(c.id): c.score for c in vector_candidates}

    for memory_data in memories_data:
        memory_id = memory_data['id']

        neighbors = get_neighbors(memory_id)

        vector_similarity = vector_scores.get(memory_id, 0.0)
        keyword_score = keyword_scores.get(memory_id, 0.0)

        edge_weight_sum = sum(neighbor.get('weight', 0.0) for neighbor in neighbors)
        importance = memory_data.get('importance', 0.5)

        created_at_dt = memory_data.get('created_at')
        recency_decay = 0.5 # Default
        if created_at_dt:
            days_since_creation = (now - created_at_dt).days
            recency_decay = 0.99 ** days_since_creation

        # New hybrid scoring formula, giving keyword search a boost
        final_score = (
            (0.5 * vector_similarity) +
            (0.2 * keyword_score) + # Added keyword score
            (0.15 * (edge_weight_sum / settings.MAX_EDGES_PER_NODE if neighbors else 0)) +
            (0.1 * importance) +
            (0.05 * recency_decay) # Adjusted weights
        )

        memory_data['score'] = final_score
        scored_memories.append(memory_data)

    # Step 4: Sort and Return Top-K
    sorted_memories = sorted(scored_memories, key=lambda x: x['score'], reverse=True)

    return sorted_memories[:top_k]
