import uuid
import yaml
import os
from typing import List, Dict, Any
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class InferenceEngine:
    """
    Rule-based inference engine.
    Applies logic patterns to deduce new relations from a YAML configuration.
    """
    def __init__(self, rule_file: str = "config/rules/rule_library.yaml"):
        self.graph = GraphService()
        self.rules = self._load_rules(rule_file)

    def _load_rules(self, rule_file: str) -> List[Dict]:
        """Loads rules from YAML file."""
        if not os.path.exists(rule_file):
            log.warning(f"Rule file {rule_file} not found. Using empty ruleset.")
            return []

        with open(rule_file, "r") as f:
            try:
                data = yaml.safe_load(f)
                return data.get("rules", [])
            except yaml.YAMLError as e:
                log.error(f"Error parsing rule file: {e}")
                return []

    def apply_rules(self, entity_id: uuid.UUID) -> Dict[str, Any]:
        """
        Applies all loaded rules to the given entity.
        Returns summary of actions taken.

        Optimized to fetch 1-hop relations only once per entity.
        """
        results = {
            "inferred_relations": 0,
            "conflicts": [],
            "rules_triggered": []
        }

        # 1. Fetch Local Context (1-hop outgoing edges) ONCE
        # This reduces N+1 queries.
        local_relations = self.graph.get_relations(entity_id, direction="out")

        for rule in self.rules:
            triggered = False
            try:
                if rule['type'] == 'inference':
                    triggered = self._apply_inference_rule(entity_id, rule, local_relations)
                elif rule['type'] == 'inverse':
                    triggered = self._apply_inverse_rule(entity_id, rule, local_relations)
                # Future: elif rule['type'] == 'contradiction': ...

                if triggered:
                    results["rules_triggered"].append(rule['name'])
                    results["inferred_relations"] += 1
            except Exception as e:
                log.error(f"Error applying rule {rule.get('name')}: {e}")

        results["conflicts"] = self.infer_contradictions(entity_id, local_relations)

        return results

    def _apply_inverse_rule(self, entity_id: uuid.UUID, rule: Dict, local_relations: List[Dict]) -> bool:
        """
        Handles simple inverse rules (A->B implies B->A).
        Uses pre-fetched local_relations.
        """
        pattern = rule['pattern'][0]
        infer_def = rule['infer']

        if pattern['source'].startswith("?"):
            # Entity matches source, check local outgoing relations
            # Filter in memory instead of DB query
            matching_rels = [r for r in local_relations if r['relation_type'] == pattern['relation']]

            triggered = False
            for match in matching_rels:
                target_id = uuid.UUID(match['target_entity_id'])

                new_source = target_id if infer_def['source'] == pattern['target'] else entity_id
                new_target = entity_id if infer_def['target'] == pattern['source'] else target_id

                self.graph.add_relation(
                    new_source, new_target,
                    infer_def['relation'],
                    confidence=match['confidence'] * float(infer_def.get('confidence_factor', 1.0)),
                    is_inferred=True,
                    metadata={"rule": rule['name']}
                )
                triggered = True
                log.info(f"Rule {rule['name']} triggered: {new_source} -> {new_target}")

            return triggered
        return False

    def _apply_inference_rule(self, entity_id: uuid.UUID, rule: Dict, local_relations: List[Dict]) -> bool:
        """
        Handles chain inference (A->B, B->C implies A->C).
        Uses pre-fetched local_relations for Step 1.
        Step 2 still queries DB (2-hop), but Step 1 is optimized.
        """
        pattern = rule['pattern']
        infer_def = rule['infer']

        if len(pattern) == 2:
            p1 = pattern[0]
            p2 = pattern[1]

            if p1['source'].startswith("?"):
                # Step 1: Find A -> B (In Memory)
                matches1 = [r for r in local_relations if r['relation_type'] == p1['relation']]

                triggered = False
                for m1 in matches1:
                    mid_id = uuid.UUID(m1['target_entity_id'])

                    # Step 2: Find B -> C (DB Query - unavoidable without full graph in memory)
                    if p2['source'] == p1['target']:
                        # Fetch outgoing from neighbor B
                        rels2 = self.graph.get_relations(mid_id, direction="out")
                        matches2 = [r for r in rels2 if r['relation_type'] == p2['relation']]

                        for m2 in matches2:
                            final_target_id = uuid.UUID(m2['target_entity_id'])

                            self.graph.add_relation(
                                entity_id, final_target_id,
                                infer_def['relation'],
                                confidence=m1['confidence'] * m2['confidence'] * float(infer_def.get('confidence_factor', 0.9)),
                                is_inferred=True,
                                metadata={"rule": rule['name']}
                            )
                            triggered = True
                            log.info(f"Rule {rule['name']} triggered: {entity_id} -> {final_target_id}")
                return triggered

        return False

    def infer_contradictions(self, entity_id: uuid.UUID, local_relations: List[Dict] = None) -> List[Dict]:
        """
        Legacy contradiction check, updated to use pre-fetched relations.
        """
        if local_relations is None:
            local_relations = self.graph.get_relations(entity_id, direction="out")

        locations = [r for r in local_relations if r['relation_type'] == 'located_in']

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
