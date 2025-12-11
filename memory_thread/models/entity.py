from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class Entity(BaseModel):
    id: UUID
    namespace: str
    entity_type: str
    name: str
    merged_into: Optional[UUID] = None

    class Config:
        frozen = True

class MergeProposal(BaseModel):
    source_entity_id: UUID
    target_entity_id: UUID
    confidence: float
    reason: str
    # timestamp removed from model default, handle in event/log

    class Config:
        frozen = True

class EntityMergeLog(BaseModel):
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    confidence: float
    reason: str
    timestamp: str # ISO format string or datetime passed in explicitly

    class Config:
        frozen = True
