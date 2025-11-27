import json
import logging
from uuid import UUID
from typing import Dict, Any, List

from memory_thread.models.memory_object import MemoryObject
from memory_thread.db.postgres_client import get_postgres_connection

log = logging.getLogger(__name__)

def store_memory_in_graph(memory_object: MemoryObject):
    """
    Inserts a MemoryObject into the 'memories' table, consistent with the final schema.
    """
    sql = """
        INSERT INTO memories (
            id, content, memory_type, importance, entities, topics,
            created_at, last_accessed, relations, metadata,
            domain, current_value, history
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    conn = None
    try:
        conn = get_postgres_connection()
        with conn.cursor() as cur:
            cur.execute(sql, (
                str(memory_object.id),
                memory_object.content,
                memory_object.memory_type,
                memory_object.importance,
                memory_object.entities,
                memory_object.topics,
                memory_object.created_at,
                memory_object.last_accessed,
                [str(r) for r in memory_object.relations],
                json.dumps(memory_object.metadata.dict()) if memory_object.metadata else None,
                memory_object.domain,
                memory_object.current_value,
                json.dumps(memory_object.history) if memory_object.history else None
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
    Placeholder function to create edges for a new memory in the graph.
    """
    log.info(f"Placeholder: Creating graph edges for memory ID {memory_object.id}.")
    pass

def keyword_search_memories(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Performs a keyword search on the 'content' of memories using the trigram index.
    """
    # The '%' signs are wildcards for the LIKE query.
    sql = "SELECT *, similarity(content, %s) AS keyword_score FROM memories ORDER BY keyword_score DESC LIMIT %s"
    conn = None
    try:
        conn = get_postgres_connection()
        with conn.cursor() as cur:
            cur.execute(sql, (query, top_k))
            results = cur.fetchall()
        return results
    except Exception as e:
        log.error(f"Error during keyword search: {e}")
        return []
    finally:
        if conn:
            conn.close()

# Other functions like get_neighbors, get_memories_by_ids would go here
# For now, this is the critical function to fix consistency.
