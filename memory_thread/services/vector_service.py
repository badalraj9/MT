"""
Memory Thread: Vector Service
==============================
Handles vector storage and search in Qdrant.

Production Features:
- Graceful degradation when Qdrant unavailable
- Error handling with logging
- Batch operations
"""

import logging
from typing import List, Optional
from dataclasses import dataclass

from memory_thread.db.qdrant_client import QdrantClientWrapper
from memory_thread.db.qdrant_setup import COLLECTION_NAME

log = logging.getLogger(__name__)

# Singleton wrapper
_qdrant: Optional[QdrantClientWrapper] = None


def _get_client() -> QdrantClientWrapper:
    """Get or create Qdrant client wrapper"""
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClientWrapper()
    return _qdrant


@dataclass
class VectorSearchResult:
    """Result from vector search"""
    id: str
    score: float
    payload: dict = None


def store_vectors(memory_objects: List) -> bool:
    """
    Store memory objects in Qdrant.
    
    Args:
        memory_objects: List of MemoryObject instances with embeddings
        
    Returns:
        True if successful, False otherwise
    """
    client = _get_client()
    
    if not client.is_available():
        log.warning("Qdrant not available, skipping vector storage")
        return False
    
    try:
        from qdrant_client import models
        
        points = []
        for obj in memory_objects:
            if hasattr(obj, 'embedding') and obj.embedding:
                points.append(
                    models.PointStruct(
                        id=str(obj.id),
                        vector=obj.embedding,
                        payload={
                            "memory_type": getattr(obj, 'memory_type', 'memory'),
                            "importance": getattr(obj, 'importance', 0.5),
                            "entities": getattr(obj, 'entities', []),
                            "topics": getattr(obj, 'topics', []),
                            "metadata": obj.metadata.dict() if hasattr(obj, 'metadata') else {}
                        }
                    )
                )
        
        if not points:
            log.debug("No vectors to store")
            return True
        
        client.client.upsert(
            collection_name=COLLECTION_NAME, 
            points=points, 
            wait=True
        )
        log.info(f"Stored {len(points)} vectors in Qdrant")
        return True
        
    except Exception as e:
        log.error(f"Failed to store vectors: {e}")
        return False


def search_vectors(embedding: List[float], top_k: int = 20) -> List[VectorSearchResult]:
    """
    Search for similar vectors.
    
    Args:
        embedding: Query vector
        top_k: Number of results to return
        
    Returns:
        List of VectorSearchResult (empty list if Qdrant unavailable)
    """
    client = _get_client()
    
    if not client.is_available():
        log.warning("Qdrant not available, returning empty results")
        return []
    
    try:
        results = client.client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            limit=top_k,
            with_payload=True,
            with_vectors=False
        )
        
        return [
            VectorSearchResult(
                id=str(hit.id),
                score=hit.score,
                payload=hit.payload
            )
            for hit in results.points
        ]
        
    except Exception as e:
        log.error(f"Vector search failed: {e}")
        return []


def delete_vectors(ids: List[str]) -> bool:
    """Delete vectors by ID"""
    client = _get_client()
    
    if not client.is_available():
        return False
    
    try:
        from qdrant_client import models
        
        client.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(points=ids)
        )
        log.info(f"Deleted {len(ids)} vectors")
        return True
        
    except Exception as e:
        log.error(f"Failed to delete vectors: {e}")
        return False


def get_collection_info() -> Optional[dict]:
    """Get information about the vector collection"""
    client = _get_client()
    
    if not client.is_available():
        return None
    
    try:
        info = client.client.get_collection(COLLECTION_NAME)
        return {
            'name': COLLECTION_NAME,
            'vectors_count': info.vectors_count,
            'points_count': info.points_count,
            'status': info.status.value
        }
    except Exception as e:
        log.error(f"Failed to get collection info: {e}")
        return None

