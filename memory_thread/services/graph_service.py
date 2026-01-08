import uuid
import json
import logging
from typing import List, Dict, Optional, Tuple
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
            sql += "source_entity_id = %s OR target_entity_id = %s"
            params.append(str(entity_id))
            params.append(str(entity_id))

        with self.pg.get_cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

        return rows

    def delete_relation(self, relation_id: uuid.UUID):
        with self.pg.get_cursor() as cur:
            cur.execute("DELETE FROM relations WHERE id = %s", (str(relation_id),))

    def get_inferred_relations(self, entity_id: uuid.UUID) -> List[Dict]:
        """Get all inferred (rule-generated) relations for an entity"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT * FROM relations 
                WHERE is_inferred = TRUE 
                  AND (source_entity_id = %s OR target_entity_id = %s)
            """, (str(entity_id), str(entity_id)))
            return cur.fetchall()

    def find_path(self, source_id: uuid.UUID, target_id: uuid.UUID, 
                  max_depth: int = 3) -> Optional[List[Dict]]:
        """
        BFS path finding between two entities.
        Returns list of relations forming the path, or None if no path found.
        """
        if source_id == target_id:
            return []
        
        visited = set()
        queue = [(str(source_id), [])]  # (current_node, path_so_far)
        
        with self.pg.get_cursor() as cur:
            while queue:
                current, path = queue.pop(0)
                
                if len(path) >= max_depth:
                    continue
                
                if current in visited:
                    continue
                visited.add(current)
                
                # Get outgoing relations
                cur.execute("""
                    SELECT source_entity_id, target_entity_id, relation_type, confidence
                    FROM relations
                    WHERE source_entity_id = %s
                """, (current,))
                
                for row in cur.fetchall():
                    tgt = row['target_entity_id'] if isinstance(row, dict) else row[1]
                    rel = row['relation_type'] if isinstance(row, dict) else row[2]
                    conf = row['confidence'] if isinstance(row, dict) else row[3]
                    
                    new_path = path + [{'from': current, 'to': str(tgt), 'type': rel, 'confidence': conf}]
                    
                    if str(tgt) == str(target_id):
                        return new_path
                    
                    queue.append((str(tgt), new_path))
        
        return None  # No path found

    def get_common_neighbors(self, entity_a: uuid.UUID, entity_b: uuid.UUID) -> List[Dict]:
        """Find entities connected to both A and B"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT DISTINCT r1.target_entity_id as common_entity, 
                       r1.relation_type as rel_from_a,
                       r2.relation_type as rel_from_b
                FROM relations r1
                JOIN relations r2 ON r1.target_entity_id = r2.target_entity_id
                WHERE r1.source_entity_id = %s 
                  AND r2.source_entity_id = %s
                  AND r1.target_entity_id != %s
                  AND r1.target_entity_id != %s
            """, (str(entity_a), str(entity_b), str(entity_a), str(entity_b)))
            return cur.fetchall()

