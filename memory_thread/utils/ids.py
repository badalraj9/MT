import json
import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict
from memory_thread.config.settings import settings

def canonical_json_for_event(payload: Dict[str, Any]) -> str:
    """
    Produces a canonical JSON string for deterministic hashing.
    Excludes mutable fields (freshness, sequence, etc.) and 'id'.
    """
    # Copy and prune
    p = dict(payload)
    p.pop("id", None)

    prov = p.get("provenance")
    if isinstance(prov, dict):
        # We prune gateway_timestamp?
        # Requirement: "Do not include ... provenance.gateway_ts (or include gateway_ts but ensure it is the one assigned by gateway)"
        # Requirement 2: "include timestamp in the canonical payload (gateway-assigned timestamp)"
        # The 'timestamp' field at root IS the gateway assigned timestamp usually.
        # But provenance might have 'gateway_timestamp'.
        # The instruction says: "remove provenance.gateway_timestamp, provenance.gateway_seq".
        p2 = dict(prov)
        p2.pop("gateway_timestamp", None)
        p2.pop("gateway_seq", None)
        p["provenance"] = p2

    tv = p.get("truth_vector")
    if isinstance(tv, dict):
        tv2 = dict(tv)
        tv2.pop("freshness", None)
        p["truth_vector"] = tv2

    # Ensure timestamp exists and is in ISO format
    # The gateway MUST have assigned 'timestamp' before calling this.
    if "timestamp" in p and isinstance(p["timestamp"], datetime):
        p["timestamp"] = p["timestamp"].isoformat()

    return json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def deterministic_event_id_from_payload(payload: Dict[str, Any]) -> uuid.UUID:
    """
    Generates a deterministic UUID5 based on the canonical event payload.
    """
    canon = canonical_json_for_event(payload)
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    return uuid.uuid5(settings.EVENT_NAMESPACE_UUID, digest)

def compute_dedup_hash(canonical_json_str: str) -> str:
    """
    Computes SHA-1 hash of the canonical JSON for deduplication.
    """
    return hashlib.sha1(canonical_json_str.encode("utf-8")).hexdigest()
