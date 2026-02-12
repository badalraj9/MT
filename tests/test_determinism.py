import unittest
import uuid
import json
from datetime import datetime
from memory_thread.utils.ids import canonical_json_for_event, deterministic_event_id_from_payload, compute_dedup_hash

class TestDeterminism(unittest.TestCase):
    def test_canonical_json_stability(self):
        # Two dicts with different key order but same content
        payload1 = {
            "namespace": "user",
            "actor": "USER",
            "action": "ADD",
            "timestamp": "2023-10-27T10:00:00+00:00",
            "delta": [{"op": "add", "path": "/foo", "value": 1}],
            "provenance": {"gateway_seq": 100} # Should be ignored
        }
        payload2 = {
            "delta": [{"op": "add", "path": "/foo", "value": 1}],
            "timestamp": "2023-10-27T10:00:00+00:00",
            "action": "ADD",
            "namespace": "user",
            "actor": "USER",
            "provenance": {"gateway_seq": 999} # Different seq should be ignored
        }

        canon1 = canonical_json_for_event(payload1)
        canon2 = canonical_json_for_event(payload2)

        self.assertEqual(canon1, canon2)
        self.assertNotIn("gateway_seq", canon1)

    def test_deterministic_id(self):
        payload = {
            "namespace": "user",
            "timestamp": "2023-10-27T10:00:00+00:00",
            "data": "test"
        }

        id1 = deterministic_event_id_from_payload(payload)
        id2 = deterministic_event_id_from_payload(payload)

        self.assertEqual(id1, id2)
        self.assertIsInstance(id1, uuid.UUID)

    def test_dedup_hash(self):
        payload = {
            "namespace": "user",
            "timestamp": "2023-10-27T10:00:00+00:00",
            "data": "test"
        }
        canon = canonical_json_for_event(payload)
        h1 = compute_dedup_hash(canon)
        h2 = compute_dedup_hash(canon)

        self.assertEqual(h1, h2)

if __name__ == '__main__':
    unittest.main()
