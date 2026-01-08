"""
Memory Thread: Emergent Reasoner
=================================
Phase 10.2: Autonomic Cognition

Emergent capabilities that arise from pattern observation:
1. Concept Formation (discover new concepts)
2. Analogical Reasoning (find similar situations)
3. Causal Discovery (infer causation from patterns)
4. Pattern Generalization (learn from examples)

Target: 70% accuracy on novel inferences
"""

import logging
import json
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict, Counter

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class EmergentConcept:
    """A concept discovered from patterns"""
    id: str
    name: str
    members: List[str]  # Entity IDs that belong to this concept
    defining_properties: List[str]
    confidence: float
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    source: str = "pattern_detection"  # How it was discovered


@dataclass
class Analogy:
    """An analogical mapping between situations"""
    source_pattern: Dict[str, Any]
    target_pattern: Dict[str, Any]
    mapping: Dict[str, str]  # Source element -> Target element
    similarity: float
    prediction: str
    confidence: float


@dataclass
class CausalHypothesis:
    """A hypothesized causal relationship"""
    cause: str
    effect: str
    correlation: float
    temporal_order_verified: bool
    sample_size: int
    confidence: float
    discovered_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# CONCEPT FORMATION
# ============================================================================

class ConceptFormer:
    """
    Discovers new concepts by identifying clusters of entities
    that share common properties or relationships.
    """
    
    def __init__(self):
        self.pg = PostgresClient()
        self.graph = GraphService()
        self._concepts: Dict[str, EmergentConcept] = {}
    
    def discover_concepts(self, min_members: int = 3) -> List[EmergentConcept]:
        """Find emergent concepts from entity patterns"""
        concepts = []
        
        # 1. Find entities that share the same relation to the same target
        concepts.extend(self._discover_from_shared_relations(min_members))
        
        # 2. Find entities with similar attribute patterns
        concepts.extend(self._discover_from_similar_attributes(min_members))
        
        # Store discovered concepts
        for concept in concepts:
            self._concepts[concept.id] = concept
        
        return concepts
    
    def _discover_from_shared_relations(self, min_members: int) -> List[EmergentConcept]:
        """Find entities sharing the same relation to the same target"""
        concepts = []
        
        with self.pg.get_cursor() as cur:
            # Find groups sharing the same target relation
            cur.execute("""
                SELECT target_entity_id, relation_type, 
                       array_agg(source_entity_id) as members,
                       COUNT(*) as member_count
                FROM relations
                WHERE relation_type IN ('works_at', 'is_a', 'belongs_to', 'is_part_of')
                GROUP BY target_entity_id, relation_type
                HAVING COUNT(*) >= %s
            """, (min_members,))
            
            for row in cur.fetchall():
                target = str(row[0])
                rel_type = row[1]
                members = [str(m) for m in row[2]]
                
                # Get target name
                cur.execute("SELECT name FROM entities WHERE id = %s", (target,))
                name_row = cur.fetchone()
                target_name = name_row[0] if name_row else target[:8]
                
                concept_name = f"{target_name}_{rel_type}_group"
                
                concepts.append(EmergentConcept(
                    id=f"concept-{target[:8]}",
                    name=concept_name,
                    members=members,
                    defining_properties=[f"{rel_type} {target_name}"],
                    confidence=min(0.9, 0.5 + 0.1 * len(members)),
                    source="shared_relation"
                ))
        
        return concepts
    
    def _discover_from_similar_attributes(self, min_members: int) -> List[EmergentConcept]:
        """Find entities with similar attribute patterns"""
        concepts = []
        
        with self.pg.get_cursor() as cur:
            # Get entities with their types
            cur.execute("""
                SELECT entity_type, array_agg(id) as members, COUNT(*) as count
                FROM entities
                GROUP BY entity_type
                HAVING COUNT(*) >= %s
            """, (min_members,))
            
            for row in cur.fetchall():
                entity_type = row[0]
                members = [str(m) for m in row[1]]
                
                if entity_type and entity_type != 'unknown':
                    concepts.append(EmergentConcept(
                        id=f"type-{entity_type}",
                        name=f"All_{entity_type}s",
                        members=members,
                        defining_properties=[f"is_a {entity_type}"],
                        confidence=0.95,  # Type-based grouping is high confidence
                        source="type_clustering"
                    ))
        
        return concepts
    
    def get_concept(self, concept_id: str) -> Optional[EmergentConcept]:
        """Get a discovered concept by ID"""
        return self._concepts.get(concept_id)
    
    def suggest_membership(self, entity_id: str) -> List[Tuple[str, float]]:
        """Suggest which concepts an entity might belong to"""
        suggestions = []
        
        for concept_id, concept in self._concepts.items():
            if entity_id not in concept.members:
                # Check if entity shares defining properties
                similarity = self._calculate_membership_similarity(entity_id, concept)
                if similarity > 0.5:
                    suggestions.append((concept_id, similarity))
        
        return sorted(suggestions, key=lambda x: x[1], reverse=True)
    
    def _calculate_membership_similarity(self, entity_id: str, concept: EmergentConcept) -> float:
        """Calculate how similar an entity is to a concept's members"""
        if not concept.members:
            return 0.0
        
        # Simple: check if entity has similar relations to concept members
        with self.pg.get_cursor() as cur:
            # Get entity's relations
            cur.execute("""
                SELECT target_entity_id, relation_type 
                FROM relations 
                WHERE source_entity_id = %s
            """, (entity_id,))
            entity_relations = set((str(r[0]), r[1]) for r in cur.fetchall())
            
            # Get typical member relations
            member = concept.members[0]
            cur.execute("""
                SELECT target_entity_id, relation_type 
                FROM relations 
                WHERE source_entity_id = %s
            """, (member,))
            member_relations = set((str(r[0]), r[1]) for r in cur.fetchall())
        
        if not entity_relations or not member_relations:
            return 0.0
        
        overlap = len(entity_relations & member_relations)
        total = len(entity_relations | member_relations)
        
        return overlap / total if total > 0 else 0.0


# ============================================================================
# ANALOGICAL REASONING
# ============================================================================

class AnalogyEngine:
    """
    Finds similar situations and transfers knowledge between them.
    """
    
    def __init__(self):
        self.pg = PostgresClient()
        self.graph = GraphService()
    
    def find_analogies(self, pattern: Dict[str, Any], 
                       max_results: int = 5) -> List[Analogy]:
        """Find situations analogous to the given pattern"""
        analogies = []
        
        # Extract pattern structure
        # Pattern format: {"entity": "X", "action": "planted", "value": 5000}
        
        action = pattern.get('action', '')
        
        # Search for similar patterns
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT object_id, action, delta
                FROM events
                WHERE action = %s
                ORDER BY timestamp DESC
                LIMIT 100
            """, (action,))
            
            similar_events = cur.fetchall()
        
        for event in similar_events:
            entity_id = str(event[0])
            delta = event[2]
            
            if isinstance(delta, str):
                delta = json.loads(delta)
            
            # Calculate similarity
            similarity = self._calculate_pattern_similarity(pattern, {
                'entity': entity_id,
                'action': action,
                'delta': delta
            })
            
            if similarity > 0.5:
                # Generate prediction based on analogy
                prediction = self._generate_analogical_prediction(pattern, delta)
                
                analogies.append(Analogy(
                    source_pattern={'entity': entity_id, 'action': action, 'delta': delta},
                    target_pattern=pattern,
                    mapping={'entity': pattern.get('entity', '')},
                    similarity=similarity,
                    prediction=prediction,
                    confidence=similarity * 0.7  # Reduce confidence for analogical inference
                ))
        
        # Sort by similarity and return top results
        analogies.sort(key=lambda x: x.similarity, reverse=True)
        return analogies[:max_results]
    
    def _calculate_pattern_similarity(self, pattern1: Dict, pattern2: Dict) -> float:
        """Calculate structural similarity between patterns"""
        score = 0.0
        checks = 0
        
        # Action match
        if pattern1.get('action') == pattern2.get('action'):
            score += 1.0
        checks += 1
        
        # Delta structure similarity
        delta1 = pattern1.get('delta', {})
        delta2 = pattern2.get('delta', {})
        
        if isinstance(delta1, dict) and isinstance(delta2, dict):
            keys1 = set(delta1.keys())
            keys2 = set(delta2.keys())
            if keys1 and keys2:
                key_overlap = len(keys1 & keys2) / len(keys1 | keys2)
                score += key_overlap
            checks += 1
        
        return score / checks if checks > 0 else 0.0
    
    def _generate_analogical_prediction(self, pattern: Dict, 
                                        source_outcome: Dict) -> str:
        """Generate prediction based on analogical pattern"""
        if isinstance(source_outcome, dict):
            # If source had positive outcome, predict similar for target
            for key, value in source_outcome.items():
                if isinstance(value, (int, float)) and value > 0:
                    return f"Likely positive outcome for {key}"
        
        return "Similar outcome expected based on analogical pattern"
    
    def predict_by_analogy(self, entity_id: str, 
                           question: str) -> Optional[Analogy]:
        """Answer a question by finding an analogous situation"""
        # Extract pattern from question
        pattern = {'entity': entity_id, 'question': question}
        
        analogies = self.find_analogies(pattern)
        return analogies[0] if analogies else None


# ============================================================================
# CAUSAL DISCOVERY
# ============================================================================

class CausalDiscovery:
    """
    Discovers causal relationships from correlations + temporal order.
    """
    
    def __init__(self):
        self.pg = PostgresClient()
    
    def discover_causal_links(self, min_correlation: float = 0.6,
                               min_samples: int = 5) -> List[CausalHypothesis]:
        """Find potential causal relationships"""
        hypotheses = []
        
        with self.pg.get_cursor() as cur:
            # Find event pairs that frequently co-occur with consistent temporal order
            cur.execute("""
                WITH event_pairs AS (
                    SELECT 
                        e1.action as cause_action,
                        e2.action as effect_action,
                        e1.object_id,
                        COUNT(*) as pair_count
                    FROM events e1
                    JOIN events e2 ON e1.object_id = e2.object_id
                    WHERE e1.timestamp < e2.timestamp
                      AND e1.timestamp + INTERVAL '1 day' > e2.timestamp
                      AND e1.id != e2.id
                    GROUP BY e1.action, e2.action, e1.object_id
                    HAVING COUNT(*) >= %s
                )
                SELECT cause_action, effect_action, SUM(pair_count) as total_pairs
                FROM event_pairs
                GROUP BY cause_action, effect_action
                ORDER BY total_pairs DESC
                LIMIT 20
            """, (min_samples,))
            
            for row in cur.fetchall():
                cause = row[0]
                effect = row[1]
                count = row[2]
                
                # Calculate pseudo-correlation based on frequency
                correlation = min(1.0, count / 100)  # Normalize
                
                if correlation >= min_correlation:
                    hypotheses.append(CausalHypothesis(
                        cause=cause,
                        effect=effect,
                        correlation=round(correlation, 2),
                        temporal_order_verified=True,
                        sample_size=count,
                        confidence=round(correlation * 0.8, 2)  # Reduce for uncertainty
                    ))
        
        return hypotheses


# ============================================================================
# EMERGENT REASONER
# ============================================================================

class EmergentReasoner:
    """
    Unified interface for all emergent reasoning capabilities.
    """
    
    def __init__(self):
        self.concept_former = ConceptFormer()
        self.analogy_engine = AnalogyEngine()
        self.causal_discovery = CausalDiscovery()
    
    def discover_all(self) -> Dict[str, Any]:
        """Run all discovery processes"""
        log.info("Running emergent discovery...")
        
        # Discover concepts
        concepts = self.concept_former.discover_concepts()
        
        # Discover causal links
        causal_links = self.causal_discovery.discover_causal_links()
        
        return {
            'concepts_discovered': len(concepts),
            'causal_links_discovered': len(causal_links),
            'concepts': [c.name for c in concepts[:5]],
            'causal_examples': [(h.cause, h.effect) for h in causal_links[:3]]
        }
    
    def find_similar(self, pattern: Dict) -> List[Analogy]:
        """Find analogous situations"""
        return self.analogy_engine.find_analogies(pattern)
    
    def suggest_concept(self, entity_id: str) -> List[Tuple[str, float]]:
        """Suggest concept memberships for an entity"""
        return self.concept_former.suggest_membership(entity_id)
    
    def get_causal_chain(self, action: str) -> List[CausalHypothesis]:
        """Get causal hypotheses involving an action"""
        all_links = self.causal_discovery.discover_causal_links()
        return [h for h in all_links if h.cause == action or h.effect == action]


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def discover_concepts() -> List[EmergentConcept]:
    """Quick concept discovery"""
    return ConceptFormer().discover_concepts()


def find_analogy(pattern: Dict) -> List[Analogy]:
    """Quick analogy search"""
    return AnalogyEngine().find_analogies(pattern)


def discover_causation() -> List[CausalHypothesis]:
    """Quick causal discovery"""
    return CausalDiscovery().discover_causal_links()
