import json
import logging
from uuid import UUID
from memory_thread.models.memory_object import MemoryObject
from memory_thread.db.postgres_client import get_postgres_connection
from memory_thread.config.settings import settings

log = logging.getLogger(__name__)

def store_memory_in_graph(memory_object: MemoryObject):
    """
    Inserts a MemoryObject into the 'memories' table in PostgreSQL.
    """
    sql = """
        INSERT INTO memories (id, content, memory_type, extracted, importance,
                              created_at, updated_at, last_accessed)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    conn = None
    try:
        conn = get_postgres_connection()
        with conn.cursor() as cur:
            cur.execute(sql, (
                str(memory_object.id),
                memory_object.content,
                memory_object.memory_type,
                json.dumps(memory_object.extracted) if memory_object.extracted else None,
                memory_object.importance,
                memory_object.created_at,
                memory_object.updated_at,
                memory_object.last_accessed
            ))
        conn.commit()
        log.info(f"Successfully stored memory {memory_object.id} in Postgres.")
    except Exception as e:
        log.error(f"Error storing memory {memory_object.id} in Postgres: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def create_graph_edges(memory_object: MemoryObject):
    """
    Creates edges for a new memory object based on semantic similarity
    to existing memories.
    """
    # This is a simplified placeholder for a more complex process.
    # In a real system, this would involve:
    # 1. Finding candidate memories (e.g., from Qdrant).
    # 2. Calculating semantic similarity.
    # 3. Adhering to the MAX_EDGES_PER_NODE constraint.

    log.info(f"Placeholder: Creating graph edges for memory {memory_object.id}.")
    # No-op for this phase, as the full logic depends on retrieval.
    pass

def get_neighbors(memory_id: UUID) -> list:
    """
    Retrieves the neighbors of a given memory from the 'memory_edges' table.
    """
    sql = """
        SELECT m.*, e.weight, e.relation
        FROM memory_edges e
        JOIN memories m ON e.to_id = m.id
        WHERE e.from_id = %s
    """
    conn = None
    try:
        conn = get_postgres_connection()
        with conn.cursor() as cur:
            cur.execute(sql, (str(memory_id),))
            neighbors = cur.fetchall()
        return neighbors
    except Exception as e:
        log.error(f"Error fetching neighbors for memory {memory_id}: {e}")
        return []
    finally:
        if conn:
            conn.close()
