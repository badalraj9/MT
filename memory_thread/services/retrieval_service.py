"""
Memory Thread: Retrieval Service
==================================
Multi-layer memory retrieval with hybrid scoring.

Retrieval Layers:
- Layer 2: Entity State (Truth) - Highest priority
- Layer 3: Vector + Keyword Search - Semantic relevance
- Graph Context: Edge weights boost connected memories

Scoring combines:
- Vector similarity
- Keyword overlap
- Graph connectivity
- Importance score
- Recency decay
"""

import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from uuid import UUID

from memory_thread.config.settings import settings
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.services.vector_service import search_vectors, VectorSearchResult
from memory_thread.services.graph_service import get_neighbors, get_memories_by_ids, keyword_search_memories
from memory_thread.utils.embeddings import generate_embeddings, is_model_available, get_zero_vector

log = logging.getLogger(__name__)

# Embedding dimension
EMBEDDING_DIM = 384


def retrieve_memories(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieve relevant memories using multi-layer hybrid search.
    
    Args:
        query: Natural language query
        top_k: Maximum number of results to return
        
    Returns:
        List of memory dicts with scores, sorted by relevance
    """
    if not query or not query.strip():
        log.warning("Empty query provided")
        return []
    
    try:
        # Generate query embedding
        if is_model_available():
            query_embedding = generate_embeddings((query,))[0]
        else:
            log.warning("Embedding model unavailable - using zero vector")
            query_embedding = get_zero_vector(EMBEDDING_DIM)
        
        # Layer 2: Entity State Search (High Priority)
        layer2_results = _search_entity_states(query)
        
        # Layer 3: Vector + Keyword Hybrid Search
        layer3_results = _search_layer3(query, query_embedding, top_k * 4)
        
        # Combine and deduplicate
        seen_ids: Set[str] = set()
        final_results: List[Dict[str, Any]] = []
        
        # Layer 2 results first (boost score)
        for result in layer2_results:
            rid = str(result.get('id', ''))
            if rid and rid not in seen_ids:
                result['score'] = result.get('score', 1.0) + 1.0  # Boost
                final_results.append(result)
                seen_ids.add(rid)
        
        # Layer 3 results
        for result in layer3_results:
            rid = str(result.get('id', ''))
            if rid and rid not in seen_ids:
                final_results.append(result)
                seen_ids.add(rid)
        
        # Sort by score and limit
        final_results.sort(key=lambda x: x.get('score', 0.0), reverse=True)
        return final_results[:top_k]
        
    except Exception as e:
        log.error(f"Retrieval failed: {e}")
        return []


def _search_entity_states(query: str) -> List[Dict[str, Any]]:
    """
    Search Layer 2 entity states mentioned in query.
    
    Returns state information for entities mentioned by name.
    """
    results: List[Dict[str, Any]] = []
    
    try:
        # Extract entities from query
        from memory_thread.utils.ner import extract_entities
        ner_result = extract_entities(query)
        mentioned_names = (
            ner_result.get("persons", []) + 
            ner_result.get("orgs", []) + 
            ner_result.get("locations", [])
        )
        
        if not mentioned_names:
            return results
        
        pg = PostgresClient()
        with pg.get_cursor() as cur:
            # Find entities by name
            cur.execute(
                "SELECT id, name, entity_type FROM entities WHERE name = ANY(%s)",
                (mentioned_names,)
            )
            entity_rows = cur.fetchall()
            
            for row in entity_rows:
                try:
                    entity_id = row['id'] if isinstance(row, dict) else row[0]
                    name = row['name'] if isinstance(row, dict) else row[1]
                    
                    # Fetch current state
                    cur.execute(
                        "SELECT current_value, truth_vector, updated_at FROM entity_state WHERE entity_id = %s",
                        (str(entity_id),)
                    )
                    state_row = cur.fetchone()
                    
                    if state_row:
                        curr_val = state_row['current_value'] if isinstance(state_row, dict) else state_row[0]
                        tv = state_row['truth_vector'] if isinstance(state_row, dict) else state_row[1]
                        updated = state_row['updated_at'] if isinstance(state_row, dict) else state_row[2]
                        
                        results.append({
                            "id": str(entity_id),
                            "content": f"Current State of {name}: {json.dumps(curr_val)}",
                            "memory_type": "entity_state",
                            "importance": 1.0,
                            "score": 2.0,  # High priority for entity states
                            "metadata": {
                                "source_layer": "Layer 2 (State Truth)",
                                "truth_vector": tv,
                                "updated_at": updated.isoformat() if updated else None
                            }
                        })
                except Exception as e:
                    log.warning(f"Error processing entity state: {e}")
                    continue
                    
    except Exception as e:
        log.warning(f"Entity state search failed: {e}")
    
    return results


def _search_layer3(query: str, query_embedding: List[float], candidate_limit: int) -> List[Dict[str, Any]]:
    """
    Search Layer 3 using vector similarity and keyword matching.
    
    Combines results and applies hybrid scoring.
    """
    results: List[Dict[str, Any]] = []
    
    try:
        # Vector search
        vector_candidates: List[VectorSearchResult] = []
        try:
            vector_candidates = search_vectors(query_embedding, top_k=candidate_limit)
        except Exception as e:
            log.warning(f"Vector search failed: {e}")
        
        # Keyword search
        keyword_candidates: List[Dict[str, Any]] = []
        try:
            keyword_candidates = keyword_search_memories(q=query, k=candidate_limit // 2)
        except Exception as e:
            log.warning(f"Keyword search failed: {e}")
        
        # Collect candidate IDs
        candidate_ids: Set[UUID] = set()
        for c in vector_candidates:
            try:
                candidate_ids.add(UUID(c.id))
            except (ValueError, TypeError):
                continue
        for res in keyword_candidates:
            if res.get('id'):
                try:
                    candidate_ids.add(res['id'] if isinstance(res['id'], UUID) else UUID(str(res['id'])))
                except (ValueError, TypeError):
                    continue
        
        if not candidate_ids:
            return results
        
        # Fetch full memory data
        try:
            memories_data = get_memories_by_ids(list(candidate_ids))
        except Exception as e:
            log.warning(f"Failed to fetch memories: {e}")
            return results
        
        if not memories_data:
            return results
        
        # Build score maps
        vector_scores = {}
        for c in vector_candidates:
            try:
                vector_scores[UUID(c.id)] = c.score
            except (ValueError, TypeError):
                continue
                
        keyword_scores = {res.get('id'): res.get('keyword_score', 0.0) for res in keyword_candidates if res.get('id')}
        
        # Score each memory
        now = datetime.utcnow()
        for memory_data in memories_data:
            try:
                memory_id = memory_data.get('id')
                if not memory_id:
                    continue
                
                # Get graph neighbors
                neighbors: List[Dict[str, Any]] = []
                try:
                    neighbors = get_neighbors(memory_id)
                except Exception:
                    pass
                
                # Calculate component scores
                vector_similarity = vector_scores.get(memory_id, 0.0)
                keyword_score = keyword_scores.get(memory_id, 0.0)
                edge_weight_sum = sum(n.get('weight', 0.0) for n in neighbors)
                importance = memory_data.get('importance', 0.5)
                
                # Recency factor
                recency = 0.5
                created_at = memory_data.get('created_at')
                if created_at:
                    days_old = (now - created_at).days
                    recency = 0.99 ** days_old
                
                # Combined score
                max_edges = getattr(settings, 'MAX_EDGES_PER_NODE', 20)
                graph_score = edge_weight_sum / max_edges if neighbors and max_edges > 0 else 0.0
                
                final_score = (
                    (getattr(settings, 'SCORE_WEIGHT_VECTOR', 0.4) * vector_similarity) +
                    (getattr(settings, 'SCORE_WEIGHT_KEYWORD', 0.2) * keyword_score) +
                    (getattr(settings, 'SCORE_WEIGHT_GRAPH', 0.15) * graph_score) +
                    (getattr(settings, 'SCORE_WEIGHT_IMPORTANCE', 0.15) * importance) +
                    (getattr(settings, 'SCORE_WEIGHT_RECENCY', 0.1) * recency)
                )
                
                memory_data['score'] = final_score
                memory_data['metadata'] = memory_data.get('metadata', {})
                memory_data['metadata']['source_layer'] = 'Layer 3 (Semantic)'
                results.append(memory_data)
                
            except Exception as e:
                log.warning(f"Error scoring memory: {e}")
                continue
        
        # Sort by score
        results.sort(key=lambda x: x.get('score', 0.0), reverse=True)
        
    except Exception as e:
        log.error(f"Layer 3 search failed: {e}")
    
    return results

