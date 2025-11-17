import qdrant_client
from qdrant_client.http import models

COLLECTION_NAME = "memory_vectors"

def setup_qdrant_collection(client: qdrant_client.QdrantClient):
    """
    Creates the 'memory_vectors' collection in Qdrant if it does not exist,
    with the schema specified in the project plan.
    """
    try:
        client.get_collection(collection_name=COLLECTION_NAME)
        # Collection already exists, no action needed.
        return
    except Exception:
        # Collection does not exist, proceed to create it.
        pass

    client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
    )

    # Create payload indexes on the specified fields to ensure efficient filtering.
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="memory_id",
        field_schema=models.PayloadSchemaType.KEYWORD
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="memory_type",
        field_schema=models.PayloadSchemaType.KEYWORD
    )
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="created_at",
        field_schema=models.PayloadSchemaType.KEYWORD
    )
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
