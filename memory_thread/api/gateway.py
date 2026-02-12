from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any
import asyncio
import time
import uuid
import json
import os
from datetime import datetime, timezone
from memory_thread.nervous.fabric import FabricRouter
from memory_thread.utils.logger import get_logger
from memory_thread.models.events import Event, DeltaPatch, TruthVector, ActorEnum, ActionEnum, Provenance
from memory_thread.utils.ids import canonical_json_for_event, deterministic_event_id_from_payload, compute_dedup_hash
from memory_thread.db.postgres_client import EventStore

log = get_logger(__name__)

router = APIRouter()

# Global State
fabric_router = FabricRouter(address="ipc://ingest_gateway", mode="ROUTER")
pressure_score = 0.0
producer_registry = {}
# Note: In a real app, EventStore should be a dependency injection or singleton
event_store = EventStore()
WAL_PATH = "gateway_wal.jsonl" # In production, configurable path

class BatchIngestRequest(BaseModel):
    producer_id: str
    events: List[Dict[str, Any]]

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
    # 0. Throttle Check
    if pressure_score > 0.9:
        raise HTTPException(status_code=503, detail="System Overloaded")

    # 1. Producer Check
    if req.producer_id not in producer_registry:
        raise HTTPException(status_code=403, detail="Producer not registered")

    validated_events = []
    gateway_ts = datetime.now(timezone.utc)

    # 2. Strict Validation & Canonicalization Loop (In-Memory)
    try:
        # Validate all first - Fail Fast
        for raw in req.events:
            # Strict Field Check (No defaults allowed for criticals)
            required = ("namespace", "actor", "action", "object_id", "delta", "truth_vector")
            if not all(k in raw for k in required):
                 raise ValueError(f"Missing required fields in event: {raw.keys()}")

            # Construct DeltaPatch objects safely
            deltas = []
            if isinstance(raw['delta'], list):
                 deltas = [DeltaPatch(**d) for d in raw['delta']]
            else:
                 raise ValueError("Delta must be a list of patches")

            # 3. Allocation placeholders (ID generation depends on seq? No, ID is content-based usually)
            # The Requirement: "include timestamp in the canonical payload (gateway-assigned timestamp) ... include gateway_seq if you want id to vary by order"
            # Recommendation 1 says: "Do not include ... provenance.gateway_seq ... in canonical payload"
            # So ID is independent of Sequence. Good.

            # Prepare payload for ID generation
            # We must inject the Gateway Timestamp first
            payload_for_id = raw.copy()
            payload_for_id['timestamp'] = gateway_ts

            # Canonicalize & ID
            # Note: We haven't built the full Event object yet, using dict for canonical tools
            canon = canonical_json_for_event(payload_for_id)
            event_id = deterministic_event_id_from_payload(payload_for_id)
            d_hash = compute_dedup_hash(canon)

            # Store tuple for next step
            validated_events.append({
                "raw": raw,
                "canon": canon,
                "id": event_id,
                "dedup_hash": d_hash,
                "deltas": deltas
            })

    except Exception as e:
        log.error(f"Batch Validation Failed: {e}")
        raise HTTPException(status_code=400, detail=f"Validation Error: {str(e)}")

    # 4. Allocate Sequence (Batch)
    try:
        seq_values = event_store.fetch_next_gateway_seq(batch_size=len(validated_events))
    except Exception as e:
        log.error(f"DB Sequence Fetch Failed: {e}")
        raise HTTPException(status_code=500, detail="Internal Error")

    # 5. Assign Sequence, Build Objects, Write WAL
    final_events = []

    try:
        with open(WAL_PATH, "ab") as wal_file:
            for i, item in enumerate(validated_events):
                seq = seq_values[i]

                # Construct Provenance
                prov = Provenance(
                    producer_id=req.producer_id,
                    gateway_timestamp=gateway_ts,
                    gateway_seq=seq,
                    source_system=producer_registry[req.producer_id]['type']
                )

                # Build Event Object
                raw = item['raw']
                evt = Event(
                    id=item['id'],
                    namespace=raw['namespace'],
                    timestamp=gateway_ts,
                    actor=ActorEnum(raw['actor']),
                    action=ActionEnum(raw['action']),
                    object_id=uuid.UUID(raw['object_id']),
                    delta=item['deltas'],
                    antecedents=[uuid.UUID(u) for u in raw.get('antecedents', [])],
                    truth_vector=TruthVector(**raw['truth_vector']),
                    provenance=prov,
                    gateway_seq=seq,
                    dedup_hash=item['dedup_hash']
                )

                final_events.append(evt)

                # WAL Write
                # We write the canonical JSON + Metadata (Sequence, ID)
                # Or just the full serialized Event?
                # Requirement: "Write each canonicalized event JSON ... with metadata headers"
                # Simplest: Write the `evt.json()` which is full and strictly typed.
                wal_line = evt.json() + "\n"
                wal_file.write(wal_line.encode("utf-8"))

            # Atomic Flush
            wal_file.flush()
            os.fsync(wal_file.fileno())

    except Exception as e:
        log.error(f"WAL Write Failed: {e}")
        raise HTTPException(status_code=500, detail="Persistence Error")

    # 6. DB Insert & Fabric Push
    # We do this after WAL is secure.
    success_count = 0
    for evt in final_events:
        try:
            # DB Insert (Idempotent)
            event_store.append_event(evt)

            # Fabric Push
            await fabric_router.send(evt.json())
            success_count += 1
        except Exception as e:
            log.error(f"Downstream Dispatch Failed for {evt.id}: {e}")
            # If DB fails but WAL succeeded, we have inconsistency (Split brain of sorts)
            # But WAL is the source of truth for recovery.
            # For now, log error.

    return {"status": "accepted", "count": success_count}

@router.get("/control/throttle")
async def get_throttle():
    return {"pressure": pressure_score}

async def pressure_monitor_loop():
    global pressure_score
    while True:
        await asyncio.sleep(1.0)
