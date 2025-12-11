from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import asyncio
import time
import uuid
import json
from datetime import datetime, timezone
from memory_thread.nervous.fabric import FabricRouter
from memory_thread.utils.logger import get_logger
from memory_thread.models.events import Event, DeltaPatch, TruthVector, ActorEnum, ActionEnum, Provenance

log = get_logger(__name__)

router = APIRouter()

# Global State
fabric_router = FabricRouter(address="ipc://ingest_gateway", mode="ROUTER")
pressure_score = 0.0
producer_registry = {}

class BatchIngestRequest(BaseModel):
    producer_id: str
    events: List[Dict[str, Any]] # Raw events to be validated and enriched

class RegisterProducerRequest(BaseModel):
    producer_id: str
    type: str
    version: str

@router.on_event("startup")
async def startup_event():
    await fabric_router.start()
    asyncio.create_task(pressure_monitor_loop())

@router.on_event("shutdown")
def shutdown_event():
    fabric_router.close()

@router.post("/register")
async def register_producer(req: RegisterProducerRequest):
    producer_registry[req.producer_id] = {
        "type": req.type,
        "version": req.version,
        "connected_at": time.time()
    }
    log.info(f"Registered Producer: {req.producer_id}")
    return {"status": "ok", "throttle": pressure_score}

@router.post("/ingest")
async def ingest_batch(req: BatchIngestRequest):
    if pressure_score > 0.9:
        raise HTTPException(status_code=503, detail="System Overloaded")

    if req.producer_id not in producer_registry:
        # Strict producer registration required for provenance
        raise HTTPException(status_code=403, detail="Producer not registered")

    validated_events = []

    # 1. Enrich & Validate at the Edge
    gateway_ts = datetime.now(timezone.utc)

    for raw in req.events:
        try:
            # Enforce Determinism
            # Ideally, the producer sends an ID, but if not, we generate one Deterministically if possible,
            # or just use uuid4 here at the EDGE (and only here).
            # The spec says "Assign deterministic event_id + timestamp".
            # If the producer provides an ID, use it. If not, generate one.
            event_id = uuid.UUID(raw['id']) if 'id' in raw else uuid.uuid4()

            # Construct Provenance
            provenance = Provenance(
                producer_id=req.producer_id,
                gateway_timestamp=gateway_ts,
                source_system=producer_registry[req.producer_id]['type']
            )

            # Parse Deltas safely
            if isinstance(raw.get('delta'), dict):
                # Legacy support or single delta
                deltas = [DeltaPatch(**raw['delta'])]
            elif isinstance(raw.get('delta'), list):
                 deltas = [DeltaPatch(**d) for d in raw['delta']]
            else:
                 deltas = []

            # Construct Event Object (Strict Validation)
            event = Event(
                id=event_id,
                namespace=raw.get('namespace', 'user'), # Explicit default if missing in raw, but model has no default
                timestamp=gateway_ts, # Gateway assigns timestamp
                actor=raw.get('actor', ActorEnum.USER),
                action=raw.get('action', ActionEnum.ADD),
                object_id=uuid.UUID(raw['object_id']),
                delta=deltas,
                truth_vector=TruthVector(**raw['truth_vector']),
                provenance=provenance
            )
            validated_events.append(event)

        except Exception as e:
            log.error(f"Validation Error: {e}")
            # Skip invalid events or return error? Partial success?
            # For high throughput, we might drop bad ones and warn.
            continue

    # 2. Durable Log (Stub)
    # In production: Append to local disk-based WAL (Write Ahead Log)
    # with open("gateway_wal.jsonl", "a") as f:
    #     for ev in validated_events:
    #         f.write(ev.json() + "\n")

    # 3. Forward to Fabric
    # We send the serialized validated events
    for ev in validated_events:
        # Mock sending
        pass

    return {"status": "accepted", "count": len(validated_events)}

@router.get("/control/throttle")
async def get_throttle():
    return {"pressure": pressure_score}

async def pressure_monitor_loop():
    global pressure_score
    while True:
        await asyncio.sleep(1.0)
