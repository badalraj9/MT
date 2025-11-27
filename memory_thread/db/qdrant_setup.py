import qdrant_client
from qdrant_client.http import models

COLLECTION_NAME = "memory_vectors"
EMBEDDING_SIZE = 1536
DISTANCE = models.Distance.COSINE


def setup_qdrant_collection(client: qdrant_client.QdrantClient):
    """
    Creates the Qdrant collection with vector params + payload schema + indexes
    aligned with the new plugin manifest.
    """
    existing_collections = client.get_collections().collections
    existing_names = [c.name for c in existing_collections]

    if COLLECTION_NAME not in existing_names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBEDDING_SIZE,
                distance=DISTANCE
            )
        )

    # Create payload indexes for efficient filtering
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="memory_type",
        field_schema=models.PayloadSchemaType.KEYWORD
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="importance",
        field_schema=models.PayloadSchemaType.FLOAT
    )
    # Indexing nested metadata fields. Qdrant uses dot notation for this.
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="metadata.source",
        field_schema=models.PayloadSchemaType.KEYWORD
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="metadata.negation",
        field_schema=models.PayloadSchemaType.BOOL
    )

    print(f"Qdrant collection '{COLLECTION_NAME}' is ready.")
