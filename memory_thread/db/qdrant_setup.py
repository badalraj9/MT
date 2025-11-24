import qdrant_client
from qdrant_client.http import models

COLLECTION_NAME = "memory_vectors"
EMBEDDING_SIZE = 1536
DISTANCE = models.Distance.COSINE


def setup_qdrant_collection(client: qdrant_client.QdrantClient):
    """
    Creates the Qdrant collection with vector params + payload schema + indexes.
    Ensures the collection is fully Memory-Thread-compliant.
    """

    # Check if collection already exists
    existing = client.get_collections().collections
    existing_names = [c.name for c in existing]

    if COLLECTION_NAME not in existing_names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBEDDING_SIZE,
                distance=DISTANCE
            ),
            # Explicit payload schema for validation
            on_disk_payload=True,
            payload_schema={
                "importance": models.PayloadSchemaType.FLOAT,
                "domain": models.PayloadSchemaType.KEYWORD,
                "memory_type": models.PayloadSchemaType.KEYWORD,
                # NOTE: created_at must be stored as unix timestamp (int)
                "created_at": models.PayloadSchemaType.INTEGER
            }
        )

    # Create payload indexes
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="importance",
        field_schema=models.PayloadSchemaType.FLOAT
    )

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="domain",
        field_schema=models.PayloadSchemaType.KEYWORD
    )

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="memory_type",
        field_schema=models.PayloadSchemaType.KEYWORD
    )

    # created_at must be numeric unix timestamp (sec or ms)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="created_at",
        field_schema=models.PayloadSchemaType.INTEGER
    )

    print(f"Qdrant collection '{COLLECTION_NAME}' is ready.")