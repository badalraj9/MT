from pydantic_settings import BaseSettings
import os
import uuid

class Settings(BaseSettings):
    POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "user")
    POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "password")
    POSTGRES_SERVER: str = os.environ.get("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: int = int(os.environ.get("POSTGRES_PORT", 5432))
    POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "memory_thread_db")
    QDRANT_HOST: str = os.environ.get("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", 6333))

    # Core Identity
    # Deterministic Namespace for UUID5 generation
    EVENT_NAMESPACE_UUID: str = os.environ.get("EVENT_NAMESPACE_UUID", "6ba7b810-9dad-11d1-80b4-00c04fd430c8")

    # Graph
    MAX_EDGES_PER_NODE: int = 12

    # Retrieval Scoring
    SCORE_WEIGHT_VECTOR: float = 0.4
    SCORE_WEIGHT_KEYWORD: float = 0.2
    SCORE_WEIGHT_GRAPH: float = 0.2
    SCORE_WEIGHT_IMPORTANCE: float = 0.1
    SCORE_WEIGHT_FRESHNESS: float = 0.05
    SCORE_WEIGHT_TRUTH: float = 0.05

settings = Settings()
