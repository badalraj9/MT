import uuid
from typing import List, Dict
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class InferenceEngine:
    """
    Rule-based inference engine.
    Applies logic patterns to deduce new relations.
    """
    def __init__(self):
        self.graph = GraphService()

    def infer_transitive_relations(self, entity_id: uuid.UUID):
        """
        Rule: If A works_at B and B located_in C -> A located_in C (contextual).
        Or simpler: A part_of B, B part_of C -> A part_of C.
        """
        rels = self.graph.get_relations(entity_id, direction="out")

        for r1 in rels:
            if r1['relation_type'] == 'part_of':
                mid_id = r1['target_entity_id']
                rels2 = self.graph.get_relations(uuid.UUID(mid_id), direction="out")
                for r2 in rels2:
                    if r2['relation_type'] == 'part_of':
                        target_id = r2['target_entity_id']
                        log.info(f"Inferring TRANSITIVE: {entity_id} part_of {target_id}")
                        self.graph.add_relation(
                            entity_id, uuid.UUID(target_id),
                            "part_of",
                            confidence=r1['confidence'] * r2['confidence'] * 0.9,
                            is_inferred=True,
                            metadata={"rule": "transitivity"}
                        )

    def infer_symmetry(self, entity_id: uuid.UUID):
        """
        Rule: If A friend_of B -> B friend_of A.
        """
        SYMMETRIC_RELATIONS = {'friend_of', 'spouse_of', 'colleague_of', 'near', 'similar_to'}

        rels = self.graph.get_relations(entity_id, direction="out")
        for r in rels:
            rtype = r['relation_type']
            if rtype in SYMMETRIC_RELATIONS:
                target_id = uuid.UUID(r['target_entity_id'])
                # Check if inverse exists
                inverse_rels = self.graph.get_relations(target_id, direction="out")
                exists = any(ir['target_entity_id'] == str(entity_id) and ir['relation_type'] == rtype for ir in inverse_rels)

                if not exists:
                    log.info(f"Inferring SYMMETRY: {target_id} {rtype} {entity_id}")
                    self.graph.add_relation(
                        target_id, entity_id,
                        rtype,
                        confidence=r['confidence'],
                        is_inferred=True,
                        metadata={"rule": "symmetry"}
                    )

    def infer_inverse(self, entity_id: uuid.UUID):
        """
        Rule: If A parent_of B -> B child_of A.
        """
        INVERSE_MAP = {
            'parent_of': 'child_of',
            'child_of': 'parent_of',
            'works_at': 'employer_of', # Maybe?
            'employer_of': 'works_at',
            'owned_by': 'owns',
            'owns': 'owned_by'
        }

        rels = self.graph.get_relations(entity_id, direction="out")
        for r in rels:
            rtype = r['relation_type']
            if rtype in INVERSE_MAP:
                inverse_type = INVERSE_MAP[rtype]
                target_id = uuid.UUID(r['target_entity_id'])

                log.info(f"Inferring INVERSE: {target_id} {inverse_type} {entity_id}")
                self.graph.add_relation(
                    target_id, entity_id,
                    inverse_type,
                    confidence=r['confidence'],
                    is_inferred=True,
                    metadata={"rule": "inverse"}
                )

    def infer_contradictions(self, entity_id: uuid.UUID) -> List[Dict]:
        """
        Rule: A located_in X AND A located_in Y AND X != Y -> Conflict.
        """
        rels = self.graph.get_relations(entity_id, direction="out")
        locations = [r for r in rels if r['relation_type'] == 'located_in']

        conflicts = []
        if len(locations) > 1:
            for i in range(len(locations)):
                for j in range(i + 1, len(locations)):
                    l1 = locations[i]
                    l2 = locations[j]
                    if l1['target_entity_id'] != l2['target_entity_id']:
                        conflicts.append({
                            "type": "contradiction",
                            "message": f"Entity {entity_id} located in both {l1['target_entity_id']} and {l2['target_entity_id']}",
                            "evidence": [l1, l2]
                        })
        return conflicts
