import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from memory_thread.services.vector_service import search_vectors
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.config.settings import settings

log = logging.getLogger(__name__)

def retrieve_memories(query: str, top_k: int = 10, graph_filter: Dict = None) -> List[Dict]:
    """
    Hybrid Retrieval Pipeline:
    1. Vector Search (Semantic)
    2. Graph Filter (Structural) - Optional
    3. Reranking (Truth/Score)
    """
    graph_service = GraphService()

    # 1. Vector Search
    # Generate embedding for the query
    query_embedding = generate_embeddings((query,))[0]

    # Get candidates from Qdrant: Returns list of (id_str, score) tuples
    vector_results = search_vectors(query_embedding, top_k=40)

    # Safely convert to UUID and map
    vector_scores = {}
    for vid, score in vector_results:
        try:
            vector_scores[uuid.UUID(str(vid))] = score
        except ValueError:
            log.warning(f"Invalid UUID from vector search: {vid}")
            continue

    # 2. Keyword Search
    keyword_results = graph_service.keyword_search_memories(q=query, k=20)
    keyword_scores = {}
    for res in keyword_results:
        try:
            keyword_scores[uuid.UUID(str(res['id']))] = res.get('keyword_score', 0.0)
        except ValueError:
            continue

    # Combine candidates
    all_ids = set(vector_scores.keys()) | set(keyword_scores.keys())
    if not all_ids:
        return []

    # Fetch full data
    memories_data = graph_service.get_memories_by_ids(list(all_ids))
    if not memories_data:
        return []

    scored_memories = []
    now = datetime.now(timezone.utc)

    # 3. Scoring & Reranking
    for memory_data in memories_data:
        # memory_data['id'] should be a UUID from get_memories_by_ids (Postgres)
        # but check just in case
        memory_id = memory_data['id']
        if isinstance(memory_id, str):
            memory_id = uuid.UUID(memory_id)

        # Graph Connectivity Score
        neighbors = graph_service.get_neighbors(memory_id)
        edge_weight_sum = sum(n.get('confidence', 0.0) for n in neighbors)
        graph_score = edge_weight_sum / settings.MAX_EDGES_PER_NODE if settings.MAX_EDGES_PER_NODE > 0 else 0

        # Component Scores
        v_score = vector_scores.get(memory_id, 0.0)
        k_score = keyword_scores.get(memory_id, 0.0)

        # Metadata Scores
        truth = memory_data.get('truth_vector', {})
        # Truth vector might be a dict or object.
        # In this context (from DB), it's likely a dict.
        if hasattr(truth, 'dict'): truth = truth.dict()
        confidence = float(truth.get('confidence', 0.5))

        created_at = memory_data.get('created_at')
        recency = 0.5
        if created_at:
            # Ensure created_at is aware
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            delta_days = (now - created_at).days
            recency = 0.99 ** max(0, delta_days)

        # Final Weighted Score
        w_vector = getattr(settings, 'SCORE_WEIGHT_VECTOR', 1.0)
        w_keyword = getattr(settings, 'SCORE_WEIGHT_KEYWORD', 1.0)
        w_graph = getattr(settings, 'SCORE_WEIGHT_GRAPH', 1.0)
        w_freshness = getattr(settings, 'SCORE_WEIGHT_FRESHNESS', 1.0)
        w_truth = getattr(settings, 'SCORE_WEIGHT_TRUTH', 1.0)

        final_score = (
            (w_vector * v_score) +
            (w_keyword * k_score) +
            (w_graph * graph_score) +
            (w_freshness * recency) +
            (w_truth * confidence)
        )

        memory_data['score'] = final_score
        memory_data['vector_score'] = v_score
        memory_data['keyword_score'] = k_score
        memory_data['graph_score'] = graph_score

        scored_memories.append(memory_data)

    # Sort by score descending
    return sorted(scored_memories, key=lambda x: x['score'], reverse=True)[:top_k]
