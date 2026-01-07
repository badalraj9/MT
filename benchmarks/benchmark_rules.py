import time
import uuid
import random
from memory_thread.services.reasoning.inference_engine import InferenceEngine
from unittest.mock import MagicMock

def benchmark_rules():
    print("Initializing Benchmark...")
    engine = InferenceEngine()

    # Mock Graph to avoid DB hits
    mock_data = {} # id -> list of relations

    # Generate 1000 entities
    entities = [uuid.uuid4() for _ in range(1000)]

    # Create chains: A -> works_at -> B -> part_of -> C
    print("Generating 1000 entities and relation chains...")
    for i in range(0, 1000, 3):
        if i+2 >= 1000: break
        p = entities[i]
        d = entities[i+1]
        o = entities[i+2]

        # P -> D
        mock_data[str(p)] = [{
            "source_entity_id": str(p),
            "target_entity_id": str(d),
            "relation_type": "works_at",
            "confidence": 0.9
        }]

        # D -> O
        mock_data[str(d)] = [{
            "source_entity_id": str(d),
            "target_entity_id": str(o),
            "relation_type": "part_of",
            "confidence": 0.9
        }]

    engine.graph = MagicMock()

    def get_rels(entity_id, direction="out"):
        return mock_data.get(str(entity_id), [])

    def add_rel(*args, **kwargs):
        pass

    engine.graph.get_relations.side_effect = get_rels
    engine.graph.add_relation.side_effect = add_rel

    print("Running Inference on 1000 entities...")
    start_time = time.time()

    count = 0
    for e in entities:
        # We only expect inference on 'persons' (index 0, 3, 6...)
        # But we run on all to simulate naive sweep
        res = engine.apply_rules(e)
        count += res["inferred_relations"]

    end_time = time.time()
    total_time = end_time - start_time
    avg_time_ms = (total_time / 1000) * 1000

    print(f"Total Time: {total_time:.4f}s")
    print(f"Avg Time per Entity: {avg_time_ms:.4f}ms")
    print(f"Total Inferred: {count}")

    if avg_time_ms < 10.0:
        print("PASS: Performance < 10ms/entity")
    else:
        print("FAIL: Performance > 10ms/entity")

if __name__ == "__main__":
    benchmark_rules()
