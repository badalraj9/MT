import logging
from typing import List
from qdrant_client import QdrantClient, models
from memory_thread.models.memory_object import MemoryObject
from memory_thread.db.qdrant_client import get_qdrant_client
from memory_thread.db.qdrant_setup import COLLECTION_NAME

log = logging.getLogger(__name__)

def store_vectors(memory_objects: List[MemoryObject]):
    """
    Upserts a batch of memory vectors and payloads into the Qdrant collection.
    """
    client = get_qdrant_client()

    points_to_upsert = []
    for obj in memory_objects:
        if not obj.embedding:
            log.warning(f"Memory {obj.id} has no embedding. Skipping vector storage.")
            continue

        payload = {
            "memory_type": obj.memory_type,
            "importance": obj.importance,
            "entities": obj.entities,
            "topics": obj.topics,
            "metadata": obj.metadata.dict()
        }

        points_to_upsert.append(
            models.PointStruct(
                id=str(obj.id),
                vector=obj.embedding,
                payload=payload
            )
        )

    if not points_to_upsert:
        return

    try:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points_to_upsert,
            wait=True
        )
        log.info(f"Successfully stored a batch of {len(points_to_upsert)} vectors in Qdrant.")
    except Exception as e:
        log.error(f"Error storing vector batch in Qdrant: {e}")
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
            with_payload=True
        )
        return search_results
    except Exception as e:
        log.error(f"Error searching vectors in Qdrant: {e}")
        return []
