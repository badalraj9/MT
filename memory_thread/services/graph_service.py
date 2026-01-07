import uuid
import json
import logging
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class GraphService:
    def __init__(self):
        self.pg = PostgresClient()

    def add_relation(self, source_id: uuid.UUID, target_id: uuid.UUID,
                     relation_type: str, confidence: float = 1.0,
                     is_inferred: bool = False, metadata: Dict = None) -> uuid.UUID:
        """
        Creates or updates a relationship between two entities.
        """
        metadata = metadata or {}

        with self.pg.get_cursor() as cur:
            # Upsert logic: if exists, update confidence/last_confirmed
            cur.execute("""
                INSERT INTO relations (source_entity_id, target_entity_id, relation_type, confidence, is_inferred, metadata, last_confirmed)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source_entity_id, target_entity_id, relation_type)
                DO UPDATE SET
                    confidence = EXCLUDED.confidence,
                    last_confirmed = NOW(),
                    metadata = relations.metadata || EXCLUDED.metadata
                RETURNING id
            """, (
                str(source_id), str(target_id), relation_type, confidence,
                is_inferred, json.dumps(metadata)
            ))
            rel_id = cur.fetchone()['id'] # RealDictCursor

        log.info(f"Relation added: {source_id} -[{relation_type}]-> {target_id}")
        return rel_id

    def get_relations(self, entity_id: uuid.UUID, direction: str = "out") -> List[Dict]:
        """
        Gets relations for an entity.
        direction: 'out' (source=entity), 'in' (target=entity), 'both'
        """
        sql = "SELECT * FROM relations WHERE "
        params = []

        if direction == "out":
            sql += "source_entity_id = %s"
            params.append(str(entity_id))
        elif direction == "in":
            sql += "target_entity_id = %s"
            params.append(str(entity_id))
        else:
            sql += "(source_entity_id = %s OR target_entity_id = %s)"
            params.append(str(entity_id))
            params.append(str(entity_id))

        with self.pg.get_cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

        return rows

    def delete_relation(self, relation_id: uuid.UUID):
        with self.pg.get_cursor() as cur:
            cur.execute("DELETE FROM relations WHERE id = %s", (str(relation_id),))

    def get_neighbors(self, entity_id: uuid.UUID) -> List[Dict]:
        """
        Returns a list of neighbor relations (outgoing).
        Compatible with retrieval service usage.
        """
        return self.get_relations(entity_id, direction="out")

    def get_memories_by_ids(self, ids: List[uuid.UUID]) -> List[Dict]:
        """
        Fetches entity states by IDs.
        """
        if not ids:
            return []

        str_ids = [str(id_) for id_ in ids]
        with self.pg.get_cursor() as cur:
            # Using ANY for list of IDs
            cur.execute("""
                SELECT
                    entity_id as id,
                    current_value as content,
                    truth_vector,
                    updated_at as created_at,
                    'entity' as type
                FROM entity_state
                WHERE entity_id = ANY(%s)
            """, (str_ids,))
            rows = cur.fetchall()

        return [dict(row) for row in rows]

    def keyword_search_memories(self, q: str, k: int = 20) -> List[Dict]:
        """
        Simple keyword search using ILIKE on the JSONB content.
        For production this should use Full Text Search (tsvector).
        """
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT
                    entity_id as id,
                    current_value as content,
                    truth_vector,
                    1.0 as keyword_score -- Placeholder score
                FROM entity_state
                WHERE current_value::text ILIKE %s
                LIMIT %s
            """, (f"%{q}%", k))
            rows = cur.fetchall()

        return [dict(row) for row in rows]
