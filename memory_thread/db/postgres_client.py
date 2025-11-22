import psycopg2
from psycopg2.extras import RealDictCursor
from memory_thread.config.settings import settings
import logging

log = logging.getLogger(__name__)

def get_postgres_connection():
    """
    Establishes and returns a connection to the PostgreSQL database.
    """
    try:
        conn = psycopg2.connect(
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            host=settings.POSTGRES_SERVER,
            port=settings.POSTGRES_PORT,
            cursor_factory=RealDictCursor # Returns rows as dictionaries
        )
        log.info("Successfully connected to PostgreSQL.")
        return conn
    except psycopg2.OperationalError as e:
        log.error(f"Could not connect to PostgreSQL: {e}")
        # In a real application, you might want to retry or handle this more gracefully.
        raise

# Note: Managing a global connection or a connection pool is complex.
# For this phase, we will create a new connection each time it's needed.
# This can be optimized with a connection pool (e.g., using SQLAlchemy) in a later phase.
