import unittest
import uuid
import os
from unittest.mock import MagicMock, patch
from memory_thread.services.reasoning.inference_engine import InferenceEngine

class TestInferenceRules(unittest.TestCase):
    def setUp(self):
        # Create a temporary rule file for testing
        self.rule_file = "config/rules/test_rules.yaml"
        with open(self.rule_file, "w") as f:
            f.write("""
rules:
  - name: test_hierarchical
    type: inference
    pattern:
      - { source: "?person", relation: "works_at", target: "?dept" }
      - { source: "?dept", relation: "part_of", target: "?org" }
    infer:
      source: "?person"
      relation: "affiliated_with"
      target: "?org"
      confidence_factor: 0.9

  - name: test_inverse
    type: inverse
    pattern:
      - { source: "?parent", relation: "parent_of", target: "?child" }
    infer:
      source: "?child"
      relation: "child_of"
      target: "?parent"
      confidence_factor: 1.0
            """)

        self.engine = InferenceEngine(rule_file=self.rule_file)
        self.engine.graph = MagicMock()

    def tearDown(self):
        if os.path.exists(self.rule_file):
            os.remove(self.rule_file)

    def test_inverse_rule(self):
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()

        # Mock existing relation: parent -> child
        self.engine.graph.get_relations.return_value = [
            {
                "source_entity_id": str(parent_id),
                "target_entity_id": str(child_id),
                "relation_type": "parent_of",
                "confidence": 0.8
            }
        ]

        self.engine.apply_rules(parent_id)

        # Verify call to add child -> parent
        self.engine.graph.add_relation.assert_called_with(
            child_id, parent_id, "child_of",
            confidence=0.8,
            is_inferred=True,
            metadata={"rule": "test_inverse"}
        )

    def test_hierarchical_rule(self):
        person_id = uuid.uuid4()
        dept_id = uuid.uuid4()
        org_id = uuid.uuid4()

        # Mock call 1: person -> dept
        def side_effect(entity_id, direction):
            if str(entity_id) == str(person_id):
                return [{
                    "source_entity_id": str(person_id),
                    "target_entity_id": str(dept_id),
                    "relation_type": "works_at",
                    "confidence": 0.9
                }]
            if str(entity_id) == str(dept_id):
                return [{
                    "source_entity_id": str(dept_id),
                    "target_entity_id": str(org_id),
                    "relation_type": "part_of",
                    "confidence": 0.9
                }]
            return []

        self.engine.graph.get_relations.side_effect = side_effect

        self.engine.apply_rules(person_id)

        # Verify call to add person -> org
        # Instead of exact match, capture args and check float almost equal
        args, kwargs = self.engine.graph.add_relation.call_args
        self.assertEqual(args[0], person_id)
        self.assertEqual(args[1], org_id)
        self.assertEqual(args[2], "affiliated_with")
        self.assertAlmostEqual(kwargs['confidence'], 0.729)
        self.assertTrue(kwargs['is_inferred'])
        self.assertEqual(kwargs['metadata'], {"rule": "test_hierarchical"})

if __name__ == '__main__':
    unittest.main()
