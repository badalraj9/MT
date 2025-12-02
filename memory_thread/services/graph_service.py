import json, logging
from uuid import UUID
from typing import Dict, Any, List
import psycopg2.extras
from memory_thread.models.memory_object import MemoryObject
from memory_thread.db.postgres_client import get_postgres_connection
log = logging.getLogger(__name__)

def store_memory_in_graph(memory_object: MemoryObject):
    sql = "INSERT INTO memories (id, content, memory_type, importance, entities, topics, created_at, last_accessed, relations, metadata, domain, current_value, history) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    conn = get_postgres_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (str(memory_object.id), memory_object.content, memory_object.memory_type, memory_object.importance, memory_object.entities, memory_object.topics, memory_object.created_at, memory_object.last_accessed, [str(r) for r in memory_object.relations], json.dumps(memory_object.metadata.dict()) if memory_object.metadata else None, memory_object.domain, memory_object.current_value, json.dumps(memory_object.history) if memory_object.history else None))
        conn.commit()
    finally:
        conn.close()

def store_memories_batch(memory_objects: List[MemoryObject]):
    sql = "INSERT INTO memories (id, content, memory_type, importance, entities, topics, created_at, last_accessed, relations, metadata, domain, current_value, history) VALUES %s"
    conn = get_postgres_connection()
    try:
        with conn.cursor() as cur:
            data_to_insert = [
                (
                    str(m.id), m.content, m.memory_type, m.importance, m.entities, m.topics,
                    m.created_at, m.last_accessed, [str(r) for r in m.relations],
                    json.dumps(m.metadata.dict()) if m.metadata else None,
                    m.domain, m.current_value, json.dumps(m.history) if m.history else None
                ) for m in memory_objects
            ]
            psycopg2.extras.execute_values(cur, sql, data_to_insert)
        conn.commit()
        log.info(f"Successfully stored batch of {len(memory_objects)} memories in Postgres.")
    except Exception as e:
        log.error(f"Error storing memory batch in Postgres: {e}")
        if conn: conn.rollback()
        raise
    finally:
        conn.close()

def get_memories_by_ids(ids: List[UUID]) -> List[Dict]:
    if not ids: return []
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM memories WHERE id = ANY(%s)", (tuple(str(i) for i in ids),))
        return cur.fetchall()
def get_neighbors(id: UUID) -> List[Dict]:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT m.*, e.weight, e.relation FROM memory_edges e JOIN memories m ON e.to_id = m.id WHERE e.from_id = %s", (str(id),))
        return cur.fetchall()
def keyword_search_memories(q: str, k: int=10) -> List[Dict]:
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT *, similarity(content, %s) AS score FROM memories ORDER BY score DESC LIMIT %s", (q, k))
        return cur.fetchall()
def create_graph_edges(obj: MemoryObject): log.info(f"Placeholder: Creating edges for {obj.id}.")
