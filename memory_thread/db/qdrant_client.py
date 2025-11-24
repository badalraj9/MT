from qdrant_client import QdrantClient
from memory_thread.config.settings import settings

def get_qdrant_client() -> QdrantClient:
    """
    Initializes and returns a Qdrant client instance.
    """
    client = QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT
    )
    return client

# Global client instance for reuse
qdrant_client = get_qdrant_client()
