import logging
from uuid import UUID
from qdrant_client import QdrantClient, models
from memory_thread.models.memory_object import MemoryObject
from memory_thread.db.qdrant_client import get_qdrant_client
from memory_thread.db.qdrant_setup import COLLECTION_NAME

log = logging.getLogger(__name__)

def store_vector(memory_object: MemoryObject):
    """
    Upserts a memory's vector and payload into the Qdrant collection.
    """
    if not memory_object.embedding:
        log.warning(f"Memory {memory_object.id} has no embedding. Skipping vector storage.")
        return

    client = get_qdrant_client()
    try:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=str(memory_object.id),
                    vector=memory_object.embedding,
                    payload={
                        "memory_type": memory_object.memory_type,
                        "importance": memory_object.importance,
                        "domain": memory_object.domain,
                        "created_at": int(memory_object.created_at.timestamp())
                    }
                )
            ],
            wait=True
        )
        log.info(f"Successfully stored vector for memory {memory_object.id} in Qdrant.")
    except Exception as e:
        log.error(f"Error storing vector for memory {memory_object.id} in Qdrant: {e}")
        raise

def search_vectors(query_embedding: list, top_k: int = 40) -> list:
    """
    Searches for the most similar vectors in Qdrant.
    """
    client = get_qdrant_client()
    try:
        search_results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            limit=top_k,
            with_payload=True,
            with_vectors=False # We don't need the vector itself, just the payload and score
        )
        return search_results
    except Exception as e:
        log.error(f"Error searching vectors in Qdrant: {e}")
        return []
