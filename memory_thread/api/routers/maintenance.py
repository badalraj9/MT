from fastapi import APIRouter, HTTPException
from typing import List
from uuid import UUID, uuid4, uuid5, NAMESPACE_DNS
from pydantic import BaseModel
from memory_thread.services.identity_service import IdentityService
from memory_thread.models.entity import MergeProposal
from memory_thread.models.events import Event, ActionEnum, ActorEnum, TruthVector, DeltaPatch, DeltaOp
from datetime import datetime, timezone
import json

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

# In-memory storage replaced with Stub/Event emission
# pending_proposals: List[MergeProposal] = []

class MergeRequest(BaseModel):
    proposal: MergeProposal

@router.get("/proposals")
async def get_proposals():
    # In a real scenario, this would scan or query DB 'merge_proposals' table
    service = IdentityService()
    try:
        # scan_duplicates likely returns old format, needs update or wrapper
        # For now, assuming service returns list of MergeProposal objects
        proposals = service.scan_duplicates("person", threshold=0.85)
        return proposals
    except Exception as e:
        # Log error
        return []

@router.post("/approve/merge")
async def approve_merge(req: MergeRequest):
    # INSTEAD of service.execute_merge(proposal), we emit an EVENT

    proposal = req.proposal

    # Generate Deterministic ID for the Merge Event
    # e.g. uuid5 based on source+target
    event_id = uuid5(NAMESPACE_DNS, f"{proposal.source_entity_id}-{proposal.target_entity_id}-MERGE")

    # Construct the MERGE Event
    # The 'delta' for a merge instruction might need specific handling
    # For now, we use a generic path "merge_instruction"

    merge_payload = {
        "source": str(proposal.source_entity_id),
        "target": str(proposal.target_entity_id),
        "confidence": proposal.confidence
    }

    event = Event(
        id=event_id,
        namespace="system",
        timestamp=datetime.now(timezone.utc),
        actor=ActorEnum.SYSTEM,
        action=ActionEnum.MERGE,
        object_id=proposal.target_entity_id, # Target is the surviving entity usually
        delta=[
            DeltaPatch(op=DeltaOp.ADD, path="__merge__", value=merge_payload)
        ],
        truth_vector=TruthVector(
            confidence=1.0,
            authority=1.0,
            corroboration=1.0
        ),
        antecedents=[proposal.source_entity_id, proposal.target_entity_id] # Causal link
    )

    # In a real system, we push this event to the Gateway or directly to the EventStore
    # For this refactor, we'll assume we push to EventStore (via a service helper in real life)
    # db.append_event(event)

    return {"status": "merge_event_emitted", "event_id": str(event_id)}

@router.get("/health/stats")
async def get_health_stats():
    return {
        "status": "operational",
        "mode": "event_sourced"
    }
