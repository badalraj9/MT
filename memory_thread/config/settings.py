import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    """
    Manages application settings and environment variables.
    """
    # Postgres Database Configuration
    POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "user")
    POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "password")
    POSTGRES_SERVER: str = os.environ.get("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: int = int(os.environ.get("POSTGRES_PORT", 5432))
    POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "memory_thread_db")
    DATABASE_URL: str = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    # Qdrant Configuration
    QDRANT_HOST: str = os.environ.get("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", 6333))

    # Graph Configuration
    MAX_EDGES_PER_NODE: int = 12
    SIMILARITY_THRESHOLD: float = 0.75

    class Config:
        case_sensitive = True

settings = Settings()
