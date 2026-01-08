"""
Memory Thread: Identity Service
================================
Manages entity identity, deduplication, and merge operations.

Features:
- Entity creation with vector indexing
- Duplicate detection via vector similarity
- Safe merge operations with audit logging
"""

import uuid
import json
import logging
from typing import List, Optional, Dict
from datetime import datetime

from memory_thread.models.entity import Entity, MergeProposal, EntityMergeLog
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.db.qdrant_client import QdrantClientWrapper
from memory_thread.utils.embeddings import generate_embeddings, is_model_available, get_zero_vector

# Graceful Qdrant import
try:
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue
    QDRANT_MODELS_AVAILABLE = True
except ImportError:
    QDRANT_MODELS_AVAILABLE = False
    Filter = None
    FieldCondition = None
    MatchValue = None

log = logging.getLogger(__name__)

# Default embedding dimension
EMBEDDING_DIM = 384  # sentence-transformers default


class IdentityService:
    """Service for entity identity management and deduplication."""
    
    def __init__(self):
        self.pg = PostgresClient()
        self.qdrant = QdrantClientWrapper()
        self.collection_name = "entities"
        self._qdrant_available = self.qdrant.is_available()
        
        if self._qdrant_available:
            self._ensure_collection()
        else:
            log.warning("Qdrant not available - vector operations will be skipped")

    def _ensure_collection(self) -> bool:
        """Ensure Qdrant collection exists. Returns True if successful."""
        if not self._qdrant_available:
            return False
            
        try:
            self.qdrant.ensure_collection(
                collection_name=self.collection_name,
                vector_size=EMBEDDING_DIM
            )
            return True
        except Exception as e:
            log.error(f"Failed to ensure collection: {e}")
            self._qdrant_available = False
            return False

    def create_entity(self, name: str, entity_type: str, attributes: Dict = None) -> Entity:
        """
        Creates a new entity in Postgres and indexes it in Qdrant.
        
        Args:
            name: Entity name
            entity_type: Type of entity (person, organization, etc.)
            attributes: Additional entity attributes
            
        Returns:
            Created Entity object
            
        Raises:
            Exception: If Postgres insert fails
        """
        if attributes is None:
            attributes = {}
            
        entity = Entity(
            name=name,
            entity_type=entity_type,
            attributes=attributes
        )

        # 1. Postgres Insert (required - must succeed)
        try:
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    INSERT INTO entities (id, namespace, entity_type, name, attributes, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    str(entity.id), entity.namespace, entity.entity_type, entity.name,
                    json.dumps(entity.attributes), entity.created_at, entity.updated_at
                ))
        except Exception as e:
            log.error(f"Failed to create entity {name}: {e}")
            raise

        # 2. Embedding & Qdrant Upsert (optional - graceful degradation)
        if self._qdrant_available:
            try:
                text_representation = f"{entity.name}: {entity.entity_type} {json.dumps(entity.attributes)}"
                
                if is_model_available():
                    embedding = generate_embeddings(tuple([text_representation]))[0]
                else:
                    embedding = get_zero_vector(EMBEDDING_DIM)
                    log.warning(f"Using zero vector for entity {entity.id} - model not available")

                self.qdrant.upsert(
                    collection_name=self.collection_name,
                    points=[{
                        "id": str(entity.id),
                        "vector": embedding,
                        "payload": {
                            "entity_type": entity.entity_type,
                            "name": entity.name,
                            "namespace": entity.namespace
                        }
                    }]
                )
            except Exception as e:
                log.warning(f"Failed to index entity in Qdrant: {e}")
                # Continue - Postgres is source of truth

        log.info(f"Created entity: {entity.name} ({entity.entity_type})")
        return entity

    def list_entities(self, entity_type: Optional[str] = None) -> List[Entity]:
        query = "SELECT id, namespace, entity_type, name, attributes, created_at, updated_at, merged_into FROM entities WHERE merged_into IS NULL"
        params = []
        if entity_type:
            query += " AND entity_type = %s"
            params.append(entity_type)

        with self.pg.get_cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        return [
            Entity(
                id=row[0], namespace=row[1], entity_type=row[2], name=row[3],
                attributes=row[4], created_at=row[5], updated_at=row[6], merged_into=row[7]
            )
            for row in rows
        ]

    def get_entity(self, entity_id: uuid.UUID) -> Optional[Entity]:
        with self.pg.get_cursor() as cur:
            cur.execute("SELECT id, namespace, entity_type, name, attributes, created_at, updated_at, merged_into FROM entities WHERE id = %s", (str(entity_id),))
            row = cur.fetchone()

        if not row:
            return None

        return Entity(
            id=row[0], namespace=row[1], entity_type=row[2], name=row[3],
            attributes=row[4], created_at=row[5], updated_at=row[6], merged_into=row[7]
        )

    def scan_duplicates(self, entity_type: str, threshold: float = 0.95) -> List[MergeProposal]:
        """
        Scans active entities of a given type for duplicates using vector similarity.
        
        Args:
            entity_type: Type of entities to scan
            threshold: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            List of MergeProposal objects for potential duplicates
        """
        # Check Qdrant availability
        if not self._qdrant_available or not QDRANT_MODELS_AVAILABLE:
            log.warning("Qdrant not available - cannot scan for duplicates")
            return []
        
        entities = self.list_entities(entity_type)
        proposals = []
        processed_ids = set()

        for entity in entities:
            if entity.id in processed_ids:
                continue

            try:
                # Retrieve embedding from Qdrant
                points = self.qdrant.client.retrieve(
                    collection_name=self.collection_name,
                    ids=[str(entity.id)],
                    with_vectors=True
                )
                if not points:
                    log.debug(f"No vector found for entity {entity.id}")
                    continue
                vector = points[0].vector
            except Exception as e:
                log.warning(f"Failed to retrieve vector for {entity.id}: {e}")
                continue

            try:
                # Search for similar entities
                search_result = self.qdrant.client.search(
                    collection_name=self.collection_name,
                    query_vector=vector,
                    query_filter=Filter(
                        must=[
                            FieldCondition(key="entity_type", match=MatchValue(value=entity_type)),
                        ]
                    ),
                    score_threshold=threshold,
                    limit=5
                )
            except Exception as e:
                log.warning(f"Similarity search failed for {entity.id}: {e}")
                continue

            for hit in search_result:
                try:
                    target_id = uuid.UUID(hit.id)
                except (ValueError, TypeError):
                    continue
                    
                if target_id == entity.id or target_id in processed_ids:
                    continue

                target_entity = self.get_entity(target_id)
                if not target_entity or target_entity.merged_into:
                    continue

                # Build reason string
                reason = f"Vector similarity {hit.score:.4f}"
                if entity.name.lower() == target_entity.name.lower():
                    reason += " + Exact name match"

                # Keep older entity, merge newer into it
                if entity.created_at > target_entity.created_at:
                    src, tgt = entity, target_entity
                else:
                    src, tgt = target_entity, entity

                proposal = MergeProposal(
                    source_entity=src,
                    target_entity=tgt,
                    confidence=hit.score,
                    reason=reason
                )
                proposals.append(proposal)
                processed_ids.add(src.id)
                processed_ids.add(tgt.id)

        log.info(f"Found {len(proposals)} potential duplicates for {entity_type}")
        return proposals

    def execute_merge(self, proposal: MergeProposal) -> bool:
        """
        Executes the merge: marks source as merged_into target, logs the merge.
        
        Args:
            proposal: MergeProposal with source and target entities
            
        Returns:
            True if merge succeeded, False otherwise
        """
        try:
            # 1. Update Source Entity and Log Merge (atomic transaction)
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    UPDATE entities
                    SET merged_into = %s, updated_at = NOW()
                    WHERE id = %s AND merged_into IS NULL
                """, (str(proposal.target_entity.id), str(proposal.source_entity.id)))
                
                if cur.rowcount == 0:
                    log.warning(f"Entity {proposal.source_entity.id} already merged or not found")
                    return False

                # 2. Log Merge
                cur.execute("""
                    INSERT INTO entity_merges (source_entity_id, target_entity_id, confidence, reason)
                    VALUES (%s, %s, %s, %s)
                """, (
                    str(proposal.source_entity.id),
                    str(proposal.target_entity.id),
                    proposal.confidence,
                    proposal.reason
                ))

            # 3. Remove from Qdrant (optional - graceful degradation)
            if self._qdrant_available:
                try:
                    self.qdrant.delete(
                        collection_name=self.collection_name,
                        points=[str(proposal.source_entity.id)]
                    )
                except Exception as e:
                    log.warning(f"Failed to remove merged entity from Qdrant: {e}")
                    # Continue - Postgres is source of truth

            log.info(f"Merged {proposal.source_entity.name} into {proposal.target_entity.name}")
            return True
            
        except Exception as e:
            log.error(f"Merge failed: {e}")
            return False
    
    def is_qdrant_available(self) -> bool:
        """Check if Qdrant is available for vector operations."""
        return self._qdrant_available
