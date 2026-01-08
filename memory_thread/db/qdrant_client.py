"""
Memory Thread: Qdrant Client
=============================
Production-grade vector database client with:
- Graceful connection handling
- Health checks
- Common operation helpers
"""

import logging
from typing import List, Dict, Any, Optional

from memory_thread.config.settings import settings

log = logging.getLogger(__name__)

# Attempt to import qdrant_client
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    log.warning("qdrant-client not installed, vector operations will be unavailable")


def get_qdrant_client():
    """Get Qdrant client with graceful fallback"""
    if not QDRANT_AVAILABLE:
        raise ImportError("qdrant-client is not installed. Run: pip install qdrant-client")
    
    try:
        return QdrantClient(
            host=settings.QDRANT_HOST, 
            port=settings.QDRANT_PORT,
            timeout=10.0
        )
    except Exception as e:
        log.error(f"Failed to connect to Qdrant: {e}")
        raise


class QdrantClientWrapper:
    """
    Production-grade Qdrant client wrapper.
    
    Features:
    - Graceful connection handling
    - Health check method
    - Common operation helpers
    """
    
    def __init__(self):
        self.client = None
        self._connected = False
        self._connect()
    
    def _connect(self):
        """Establish connection with error handling"""
        try:
            if QDRANT_AVAILABLE:
                self.client = get_qdrant_client()
                self._connected = True
                log.info("Connected to Qdrant vector database")
        except Exception as e:
            log.warning(f"Qdrant connection failed: {e}")
            self._connected = False
    
    def is_available(self) -> bool:
        """Check if Qdrant is available"""
        return self._connected and self.client is not None
    
    def health_check(self) -> bool:
        """Check Qdrant health"""
        if not self.is_available():
            return False
        try:
            # Simple ping via collections list
            self.client.get_collections()
            return True
        except Exception as e:
            log.warning(f"Qdrant health check failed: {e}")
            return False
    
    def ensure_collection(self, name: str, vector_size: int = 384):
        """Create collection if it doesn't exist"""
        if not self.is_available():
            log.warning("Qdrant not available, skipping collection creation")
            return False
        
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == name for c in collections)
            
            if not exists:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=Distance.COSINE
                    )
                )
                log.info(f"Created Qdrant collection: {name}")
            return True
        except Exception as e:
            log.error(f"Failed to ensure collection {name}: {e}")
            return False
    
    def upsert(self, collection: str, points: List[Dict[str, Any]]) -> bool:
        """Upsert points to collection"""
        if not self.is_available():
            return False
        
        try:
            point_structs = [
                PointStruct(
                    id=p['id'],
                    vector=p['vector'],
                    payload=p.get('payload', {})
                )
                for p in points
            ]
            self.client.upsert(collection_name=collection, points=point_structs)
            return True
        except Exception as e:
            log.error(f"Qdrant upsert failed: {e}")
            return False
    
    def search(self, collection: str, vector: List[float], 
               limit: int = 10) -> List[Dict]:
        """Search for similar vectors"""
        if not self.is_available():
            return []
        
        try:
            results = self.client.search(
                collection_name=collection,
                query_vector=vector,
                limit=limit
            )
            return [
                {
                    'id': r.id,
                    'score': r.score,
                    'payload': r.payload
                }
                for r in results
            ]
        except Exception as e:
            log.error(f"Qdrant search failed: {e}")
            return []

