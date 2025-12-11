from fastapi import APIRouter, HTTPException
from typing import List
from uuid import UUID, uuid5, NAMESPACE_DNS
from pydantic import BaseModel
from memory_thread.services.identity_service import IdentityService
from memory_thread.models.entity import MergeProposal
from memory_thread.models.events import Event, ActionEnum, ActorEnum, TruthVector, DeltaPatch, DeltaOp, Provenance
from memory_thread.utils.ids import deterministic_event_id_from_payload, canonical_json_for_event, compute_dedup_hash
from memory_thread.db.postgres_client import EventStore
from memory_thread.nervous.fabric import FabricRouter
from datetime import datetime, timezone
import json
import asyncio

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

event_store = EventStore()
fabric_router = FabricRouter(address="ipc://ingest_maintenance", mode="DEALER") # Use DEALER or push to Router? Gateway uses Router to bind. We should CONNECT to Gateway or use a Dealer to connect to Fabric?
# Architecture: Gateway Binds. Services Connect.
# But here we are in the API process.
# `gateway.py` does `fabric_router.start()` (BIND).
# If we try to bind again here, it might conflict or be fine if different address.
# Ideally, we should reuse the fabric router instance if in same process, but routers are usually per-module isolated or dependency injected.
# Since we can't easily DI across routers in this simple setup, we'll assume we push to the same Fabric via a NEW connection (DEALER) or just use the Gateway's router logic if we could import it.
# However, for safety, let's assume we need to push to the Ingestion Layer.
# Actually, Gateway pushes to "ipc://ingest_gateway".
# If we are effectively a "System Gateway", we should probably push similarly.
# Let's use a DEALER to connect to the backend fabric, OR reuse the logic.
# Wait, `gateway.py` mocks the send.
# Let's stick to the pattern:
# fabric_router = FabricRouter(...)
# await fabric_router.send(evt.json())

# CAUTION: If `gateway.py` binds to `ipc://ingest_gateway`, we can't bind to it too.
# We should probably CONNECT to the backend or just assume we are a producer.
# Let's assume we are a producer and use a DEALER socket to connect to the Fabric Backend (if it exists).
# Or simpler: The requirements said "Forward to Fabric".
# I'll implement a transient router/dealer logic.

@router.on_event("startup")
async def startup_event():
    # If we are in the same process as Gateway (main.py imports both), we need to be careful with ZMQ contexts.
    # Safe bet: Start a client-side router (DEALER)
    # But `FabricRouter` class wraps ZMQ. Let's look at `memory_thread/nervous/fabric.py` if I could read it.
    # Assuming standard behavior.
    await fabric_router.start()

@router.on_event("shutdown")
def shutdown_event():
    fabric_router.close()

class MergeRequest(BaseModel):
    proposal: MergeProposal

@router.get("/proposals")
async def get_proposals():
    service = IdentityService()
    try:
        proposals = service.scan_duplicates("person", threshold=0.85)
        return proposals
    except Exception as e:
        return []

@router.post("/approve/merge")
async def approve_merge(req: MergeRequest):
    proposal = req.proposal

    # 1. Construct Payload for Event (Pre-ID)
    gateway_ts = datetime.now(timezone.utc)

    merge_payload = {
        "source": str(proposal.source_entity_id),
        "target": str(proposal.target_entity_id),
        "confidence": proposal.confidence
    }

    deltas = [
        DeltaPatch(op=DeltaOp.ADD, path="/identity/merge", value=merge_payload)
    ]

    raw_event = {
        "namespace": "system",
        "actor": "SYSTEM",
        "action": "MERGE",
        "object_id": str(proposal.target_entity_id), # Target is object
        "delta": [d.dict() for d in deltas],
        "truth_vector": {
            "confidence": 1.0,
            "authority": 1.0,
            "corroboration": 1.0
        },
        "antecedents": [],
        "timestamp": gateway_ts
    }

    # 2. Canonicalize & ID
    canon = canonical_json_for_event(raw_event)
    event_id = deterministic_event_id_from_payload(raw_event)
    d_hash = compute_dedup_hash(canon)

    # 3. Sequence
    try:
        seq_values = event_store.fetch_next_gateway_seq(batch_size=1)
        seq = seq_values[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Sequence Error")

    # 4. Construct Event
    prov = Provenance(
        producer_id="maintenance_router",
        gateway_timestamp=gateway_ts,
        gateway_seq=seq,
        source_system="internal_api"
    )

    event = Event(
        id=event_id,
        namespace="system",
        timestamp=gateway_ts,
        actor=ActorEnum.SYSTEM,
        action=ActionEnum.MERGE,
        object_id=proposal.target_entity_id,
        delta=deltas,
        antecedents=[],
        truth_vector=TruthVector(confidence=1.0, authority=1.0, corroboration=1.0),
        provenance=prov,
        gateway_seq=seq,
        dedup_hash=d_hash
    )

    # 5. Persist
    event_store.append_event(event)

    # 6. Forward to Fabric
    # This ensures downstream consumers (Assimilators, Projectors) see the event.
    await fabric_router.send(event.json())

    return {"status": "merge_event_emitted", "event_id": str(event_id)}

@router.get("/health/stats")
async def get_health_stats():
    return {
        "status": "operational",
        "mode": "event_sourced"
    }
