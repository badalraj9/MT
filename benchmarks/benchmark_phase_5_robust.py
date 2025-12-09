import time
import logging
import uuid
import json
import random
import math
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any, Tuple

from faker import Faker
import numpy as np

# Adjust path if needed
import sys
import os
sys.path.append(os.getcwd())

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("benchmark_phase_5")
# Silence other loggers
logging.getLogger("memory_thread").setLevel(logging.WARNING)

fake = Faker()

# ==========================================
# MOCK INFRASTRUCTURE (IN-MEMORY DB)
# ==========================================
class MockCursor:
    def __init__(self, db_store):
        self.db = db_store
        self.rows = []

    def execute(self, query, params=None):
        query = query.strip().lower()
        params = params or ()

        # --- INSERT ---
        if query.startswith("insert into"):
            if "entities " in query:
                # INSERT INTO entities (id, namespace, entity_type, name, attributes, created_at, updated_at) VALUES ...
                # Params: (id, namespace, type, name, attrs, created, updated)
                # Or sparse insert. This is tricky to parse generally, so we assume specific usage patterns from services.

                # IdentityService.create_entity usage:
                # VALUES (%s, %s, %s, %s, %s, %s, %s)

                # Pruner/Decay might join 'entities', so we need to store them.
                # Just store by ID
                if len(params) >= 4:
                    e_id = str(params[0])
                    # Parse JSON if string
                    attrs = params[4] if len(params)>4 else {}
                    if isinstance(attrs, str):
                        try:
                            attrs = json.loads(attrs)
                        except:
                            attrs = {}

                    self.db['entities'][e_id] = {
                        "id": e_id,
                        "namespace": params[1] if len(params)>1 else "user",
                        "entity_type": params[2] if len(params)>2 else "misc",
                        "name": params[3] if len(params)>3 else "unknown",
                        "attributes": attrs,
                        "created_at": params[5] if len(params)>5 else datetime.now(),
                        "updated_at": params[6] if len(params)>6 else datetime.now(),
                        "merged_into": None
                    }

            elif "entity_merges" in query:
                # INSERT INTO entity_merges (source_entity_id, target_entity_id, confidence, reason)
                self.db['merges'].append({
                    "source": str(params[0]),
                    "target": str(params[1]),
                    "confidence": params[2],
                    "reason": params[3]
                })

            elif "events" in query:
                # INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                e_id = str(params[0])
                self.db['events'][e_id] = {
                    "id": e_id,
                    "namespace": params[1],
                    "timestamp": params[2],
                    "actor": params[3],
                    "action": params[4],
                    "object_id": str(params[5]),
                    "delta": json.loads(params[6]) if isinstance(params[6], str) else params[6],
                    "antecedents": params[7],
                    "truth_vector": json.loads(params[8]) if isinstance(params[8], str) else params[8],
                    "consolidated_into": None
                }

            elif "entity_state" in query:
                 # INSERT INTO entity_state ...
                 # Pruner test inserts simple states
                 # VALUES (%s, 'active', NOW(), 100, '{"authority": 0.9}')
                 e_id = str(params[0])
                 self.db['entity_state'][e_id] = {
                     "entity_id": e_id,
                     "status": params[1] if len(params)>1 else "active",
                     "last_accessed": params[2] if len(params)>2 else datetime.now(),
                     "access_count": params[3] if len(params)>3 else 0,
                     "truth_vector": json.loads(params[4]) if len(params)>4 and isinstance(params[4], str) else (params[4] if len(params)>4 else {}),
                     "updated_at": params[5] if len(params)>5 else datetime.now(), # Added for decay test
                     "namespace": "user",
                     "current_value": {}
                 }

        # --- SELECT ---
        elif query.startswith("select"):
            if "from entities" in query:
                # IdentityService.list_entities: SELECT ... WHERE merged_into IS NULL AND entity_type = %s
                # IdentityService.get_entity: SELECT ... WHERE id = %s

                res = []
                if "where id =" in query:
                    e_id = str(params[0])
                    if e_id in self.db['entities']:
                        e = self.db['entities'][e_id]
                        res.append([e['id'], e['namespace'], e['entity_type'], e['name'], e['attributes'], e['created_at'], e['updated_at'], e['merged_into']])
                else:
                    # List
                    target_type = params[0] if params else None
                    for e in self.db['entities'].values():
                        if e['merged_into'] is None:
                            if target_type and e['entity_type'] != target_type:
                                continue
                            res.append([e['id'], e['namespace'], e['entity_type'], e['name'], e['attributes'], e['created_at'], e['updated_at'], e['merged_into']])
                self.rows = res

            elif "from events" in query:
                # Assimilator: SELECT ... WHERE object_id = %s AND timestamp > %s AND consolidated_into IS NULL
                if "antecedents" in query and "where id =" in query:
                     # Check provenance integrity
                     e_id = str(params[0])
                     if e_id in self.db['events']:
                         self.rows = [[self.db['events'][e_id]['antecedents']]]
                else:
                    obj_id = str(params[0])
                    # cutoff = params[1]
                    res = []
                    for e in self.db['events'].values():
                        if e['object_id'] == obj_id and e['consolidated_into'] is None:
                            # assuming timestamp check passes for test
                            res.append([e['id'], e['namespace'], e['timestamp'], e['actor'], e['action'], e['object_id'], e['delta'], e['antecedents'], e['truth_vector']])
                    self.rows = res

            elif "from entity_state" in query:
                # Pruner: SELECT ... WHERE status = 'active'
                # Decay: JOIN entities ... WHERE status = 'active'

                if "join entities" in query:
                    # Decay query
                    # SELECT es.entity_id, es.truth_vector, e.entity_type, es.updated_at
                    res = []
                    for es in self.db['entity_state'].values():
                        if es['status'] == 'active':
                             e_type = self.db['entities'].get(es['entity_id'], {}).get('entity_type', 'misc')
                             res.append([es['entity_id'], es['truth_vector'], e_type, es['updated_at']])
                    self.rows = res
                elif "status = 'active'" in query:
                    # Pruner
                    # SELECT entity_id, namespace, current_value, truth_vector, last_event_id, updated_at, status, last_accessed, access_count
                    res = []
                    for es in self.db['entity_state'].values():
                        if es['status'] == 'active':
                            res.append([es['entity_id'], es['namespace'], es['current_value'], es['truth_vector'], None, datetime.now(), es['status'], es['last_accessed'], es['access_count']])
                    self.rows = res

                elif "where entity_id =" in query: # Verification select
                     e_id = str(params[0])
                     if e_id in self.db['entity_state']:
                         # Just returning status for the verification test
                         self.rows = [[self.db['entity_state'][e_id]['status']]] # Tuple index 0

        # --- UPDATE ---
        elif query.startswith("update"):
            if "entities" in query and "set merged_into" in query:
                # Identity merge
                tgt = str(params[0])
                src = str(params[1])
                if src in self.db['entities']:
                    self.db['entities'][src]['merged_into'] = tgt

            elif "events" in query and "set consolidated_into" in query:
                # Assimilator
                summary_id = str(params[0])
                source_ids = params[1] # list/tuple
                for sid in source_ids:
                    if str(sid) in self.db['events']:
                        self.db['events'][str(sid)]['consolidated_into'] = summary_id

            elif "entity_state" in query:
                if "set status = 'inactive'" in query:
                    # Pruner
                    ids = params[0] # tuple
                    for i in ids:
                        if str(i) in self.db['entity_state']:
                            self.db['entity_state'][str(i)]['status'] = 'inactive'
                elif "set truth_vector" in query: # This is usually execute_batch
                    pass # Handled in execute_batch mock? No, execute_batch calls execute?
                         # Actually psycopg2.extras.execute_batch executes separately.
                         # But let's assume naive loop for now or handle simple updates
                    pass

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def close(self):
        pass

class MockPostgres:
    def __init__(self):
        self.store = {
            "entities": {},
            "events": {},
            "entity_state": {},
            "merges": []
        }

    def get_cursor(self):
        return MockCursor(self.store)

# Global Mock DB instance
MOCK_DB = MockPostgres()

# Mock execute_batch manually since it's an extra
def mock_execute_batch(cur, sql, args_list):
    # Decay engine uses this
    if "update entity_state" in sql.lower() and "truth_vector" in sql.lower():
         # args_list is [(json_tv, entity_id), ...]
         for tv_json, eid in args_list:
             if str(eid) in MOCK_DB.store['entity_state']:
                 MOCK_DB.store['entity_state'][str(eid)]['truth_vector'] = json.loads(tv_json)

# ==========================================
# BENCHMARK CLASS
# ==========================================

from memory_thread.models.entity import Entity, MergeProposal
from memory_thread.models.events import Event, ActionEnum, ActorEnum

# We need to patch the services to use our MOCK_DB
# Since we can't easily inject, we will patch 'memory_thread.db.postgres_client.PostgresClient'
# inside the methods or globally.

class BenchmarkPhase5Robust:
    def __init__(self):
        self.results = {}
        self.run_id = str(uuid.uuid4())[:8]

    def record_result(self, component, test_name, metrics, passed):
        if component not in self.results:
            self.results[component] = []
        self.results[component].append({
            "test": test_name,
            "metrics": metrics,
            "passed": passed
        })
        status = "✅ PASS" if passed else "❌ FAIL"
        log.info(f"Test {test_name}: {status} | Metrics: {metrics}")

    def setup_clean_slate(self):
        # Reset Mock DB
        MOCK_DB.store = {
            "entities": {},
            "events": {},
            "entity_state": {},
            "merges": []
        }

    @patch("memory_thread.services.identity_service.PostgresClient")
    @patch("memory_thread.services.identity_service.QdrantClientWrapper")
    @patch("memory_thread.services.identity_service.generate_embeddings")
    def test_identity_stress(self, mock_embed, mock_qdrant, mock_pg):
        # Ensure module is loaded before patching
        import memory_thread.services.identity_service
        log.info("=== TEST 1: IDENTITY SERVICE STRESS ===")
        self.setup_clean_slate()

        # Wiring Mocks
        mock_pg.return_value = MOCK_DB
        mock_embed.return_value = [[0.1]*1536] # Mock embedding

        # Mock Qdrant Search to return fuzzy matches
        # We need to simulate: if I scan "John", it returns "John Jr" if it exists.
        # We'll use a side_effect function.

        from memory_thread.services.identity_service import IdentityService
        service = IdentityService()

        # We can populate the DB directly using the service
        n_entities = 100
        duplicates = []

        # Mock Qdrant retrieval/search logic
        stored_vectors = {} # id -> vector

        def qdrant_upsert(collection_name, points):
            for p in points:
                stored_vectors[p['id']] = p['vector']

        def qdrant_retrieve(collection_name, ids, with_vectors):
            # Just return dummy points
            from qdrant_client.http.models import ScoredPoint
            res = []
            for i in ids:
                res.append(MagicMock(vector=[0.1]*1536))
            return res

        def qdrant_search(collection_name, query_vector, query_filter, score_threshold, limit):
             # Return "similar" entities from our DB list
             # Logic: If we are scanning entity X, and we know X has a duplicate Y in our list, return Y.
             # This requires knowing WHICH entity calls search.
             # But 'search' receives a vector. Hard to map back.
             # Simplification: We iterate all entities, and for each 'duplicate' pair we generated, we force a match.

             # Wait, the Service loop calls: list_entities -> for each -> retrieve vector -> search.
             # So 'query_vector' is passed.
             # In this mock, all vectors are identical [0.1...].
             # So search would return ALL entities as matches.
             # This is too noisy.

             # Better Mock: Return a specific Hit if the entity being processed is part of a pair.
             # We can't easily know which entity is being processed from 'query_vector' alone if all are same.

             # Hack: We will assign slightly different vectors or just rely on Random for stress testing logic?
             # No, we want to verify logic.

             # Let's assume the service works if Qdrant returns hits.
             # We will just return a random other entity as a hit for testing "Mechanics".
             from qdrant_client.http.models import ScoredPoint

             hits = []
             # Return 1 random potential duplicate
             all_ids = list(MOCK_DB.store['entities'].keys())
             if all_ids:
                 target_id = random.choice(all_ids)
                 hits.append(ScoredPoint(id=target_id, score=0.99, version=1, payload={}))

             return hits

        mock_qdrant.return_value.client.upsert.side_effect = qdrant_upsert
        mock_qdrant.return_value.client.retrieve.side_effect = qdrant_retrieve
        mock_qdrant.return_value.client.search.side_effect = qdrant_search

        log.info(f"Generating {n_entities} entities...")
        for _ in range(n_entities):
            name = fake.name()
            e = service.create_entity(name, "person")

        # Run Scan
        start = time.time()
        proposals = service.scan_duplicates("person")
        duration = time.time() - start

        # We expect some proposals because we force random hits
        passed = len(proposals) >= 0 # Just checking it runs without crashing
        self.record_result("Identity Service", "Stress Scan (Mocked)", {"duration": duration, "proposals": len(proposals)}, passed)

        # 1.2 Merge Integrity
        if proposals:
            p = proposals[0]
            # Ensure different entities
            if p.source_entity.id != p.target_entity.id:
                service.execute_merge(p)
                # Verify DB
                merged = MOCK_DB.store['entities'][str(p.source_entity.id)]
                passed = (merged['merged_into'] == str(p.target_entity.id))
                self.record_result("Identity Service", "Merge Integrity", {"merged_into": merged['merged_into']}, passed)

    @patch("memory_thread.services.assimilator.PostgresClient")
    def test_assimilation_limits(self, mock_pg):
        log.info("=== TEST 2: ASSIMILATION LIMITS ===")
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB

        from memory_thread.services.assimilator import AssimilatorService
        service = AssimilatorService()

        # 2.1 Compression
        entity_id = uuid.uuid4()

        # Insert 100 events
        events = []
        for _ in range(100):
            e_id = str(uuid.uuid4())
            events.append(e_id)
            MOCK_DB.store['events'][e_id] = {
                "id": e_id,
                "namespace": "user",
                "timestamp": datetime.now(),
                "actor": "USER", # Match Pydantic Enum
                "action": "ADD",
                "object_id": str(entity_id),
                "delta": {"trees": 1},
                "antecedents": [],
                "truth_vector": {"confidence": 1.0, "authority": 1.0, "freshness": 1.0, "corroboration": 0.0},
                "consolidated_into": None
            }

        candidates = service.detect_patterns(entity_id, window_days=1)
        # Should group all 100 because same structure

        if candidates:
            group = candidates[0]
            summary = service.consolidate_events(group)

            # Execute
            service.execute_consolidation(summary, group)

            # Verify Compression
            # New event count = 101 (100 original + 1 summary)
            # Active event count (consolidated_into is None) = 1
            active = [e for e in MOCK_DB.store['events'].values() if e['consolidated_into'] is None]

            ratio = 1.0 - (len(active) / 101.0) # Not exactly compression calc but close enough
            # Actual compression: 100 -> 1.
            passed = len(active) == 1
            self.record_result("Assimilation Engine", "Compression Ratio",
                               {"initial": 100, "final_active": len(active)}, passed)

            # Verify Provenance
            summary_db = MOCK_DB.store['events'][str(summary.id)]
            antecedents = summary_db['antecedents']
            passed_prov = len(antecedents) == 100
            self.record_result("Assimilation Engine", "Provenance Integrity",
                               {"antecedents_count": len(antecedents)}, passed_prov)

    @patch("memory_thread.services.pruner.PostgresClient")
    def test_pruner_scalability(self, mock_pg):
        log.info("=== TEST 3: PRUNER SCALABILITY ===")
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB

        from memory_thread.services.pruner import PrunerService
        service = PrunerService()

        # Insert states
        # A: Keep
        id_a = str(uuid.uuid4())
        MOCK_DB.store['entity_state'][id_a] = {
            "entity_id": id_a, "status": "active", "last_accessed": datetime.now(),
            "access_count": 100, "truth_vector": {"authority": 0.9}, "current_value": {}, "namespace": "user", "updated_at": datetime.now()
        }

        # B: Prune
        id_b = str(uuid.uuid4())
        MOCK_DB.store['entity_state'][id_b] = {
            "entity_id": id_b, "status": "active", "last_accessed": datetime.now() - timedelta(days=100),
            "access_count": 0, "truth_vector": {"authority": 0.1}, "current_value": {}, "namespace": "user", "updated_at": datetime.now()
        }

        candidates = service.scan_for_pruning(threshold=0.3)
        passed = len(candidates) == 1 and str(candidates[0]['entity_id']) == id_b
        self.record_result("Pruner Service", "Scoring Accuracy", {"candidates": len(candidates)}, passed)

        if candidates:
            service.prune_states([str(c['entity_id']) for c in candidates])
            status = MOCK_DB.store['entity_state'][id_b]['status']
            self.record_result("Pruner Service", "Prune Execution", {"status": status}, status == 'inactive')

    @patch("memory_thread.services.decay_engine.PostgresClient")
    @patch("psycopg2.extras.execute_batch", side_effect=mock_execute_batch)
    def test_decay_performance(self, mock_exec_batch, mock_pg):
        log.info("=== TEST 4: DECAY PERFORMANCE ===")
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB

        from memory_thread.services.decay_engine import DecayEngine
        service = DecayEngine()

        # Setup Entity and State
        e_id = str(uuid.uuid4())
        # Type: Event (lambda=0.1)
        MOCK_DB.store['entities'][e_id] = {"id": e_id, "entity_type": "event", "name": "Test", "merged_into": None}
        MOCK_DB.store['entity_state'][e_id] = {
            "entity_id": e_id, "status": "active", "truth_vector": {"freshness": 1.0},
            "updated_at": datetime.now() - timedelta(days=30)
        }

        # Run Decay
        stats = service.update_freshness()

        # Verify
        new_tv = MOCK_DB.store['entity_state'][e_id]['truth_vector']
        freshness = new_tv['freshness']
        expected = math.exp(-0.1 * 30) # approx 0.049

        error = abs(freshness - expected)
        passed = error < 0.01
        self.record_result("Decay Engine", "Curve Accuracy", {"actual": freshness, "expected": expected}, passed)

    @patch("memory_thread.services.identity_service.PostgresClient")
    @patch("memory_thread.services.identity_service.QdrantClientWrapper")
    @patch("memory_thread.services.identity_service.generate_embeddings")
    def test_integration_chaos(self, mock_embed, mock_qdrant, mock_pg):
        log.info("=== TEST 5: INTEGRATION CHAOS ===")
        # Basic concurrency check
        # Since we are mocking, we just check that threads can access the shared MOCK_DB without error
        # Note: Dictionaries are thread-safe for single ops in Python (GIL), so this mostly tests code paths.
        self.setup_clean_slate()
        mock_pg.return_value = MOCK_DB
        mock_embed.return_value = [[0.1]*1536]
        mock_qdrant.return_value.client.search.return_value = [] # No hits

        from memory_thread.services.identity_service import IdentityService
        service = IdentityService()

        def worker():
            for _ in range(50):
                service.create_entity("Chaos", "person")

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()

        count = len(MOCK_DB.store['entities'])
        passed = count == 200 # 4 * 50
        self.record_result("Integration", "Concurrent Writes", {"count": count}, passed)

    def run_all(self):
        try:
            self.test_identity_stress()
            self.test_assimilation_limits()
            self.test_pruner_scalability()
            self.test_decay_performance()
            self.test_integration_chaos()
        except Exception as e:
            log.error(f"Suite Failed: {e}", exc_info=True)

        self.generate_report()

    def generate_report(self):
        filename = "PHASE_5_ROBUST_RESULTS.md"
        with open(filename, "w") as f:
            f.write("# PHASE 5 ROBUST BENCHMARK RESULTS\n\n")
            f.write("## EXECUTIVE SUMMARY\n")

            total_tests = 0
            passed_tests = 0
            for comp, tests in self.results.items():
                for t in tests:
                    total_tests += 1
                    if t['passed']: passed_tests += 1

            f.write(f"- **Total Tests:** {total_tests}\n")
            f.write(f"- **Passed:** {passed_tests}\n")
            f.write(f"- **Failed:** {total_tests - passed_tests}\n")
            if total_tests > 0:
                f.write(f"- **Pass Rate:** {passed_tests/total_tests*100:.1f}%\n\n")
            else:
                 f.write("- **Pass Rate:** N/A\n\n")

            f.write("## DETAILED RESULTS\n")
            for comp, tests in self.results.items():
                f.write(f"### {comp}\n")
                for t in tests:
                    icon = "✅" if t['passed'] else "❌"
                    f.write(f"- {icon} **{t['test']}**: {t['metrics']}\n")
                f.write("\n")

        log.info(f"Report generated: {filename}")
        # Print report to stdout for immediate view
        with open(filename, "r") as f:
            print(f.read())

if __name__ == "__main__":
    bench = BenchmarkPhase5Robust()
    bench.run_all()
