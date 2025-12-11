from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
from enum import Enum
from datetime import datetime
import uuid

class ActorEnum(str, Enum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"

class ActionEnum(str, Enum):
    PLANT = "PLANT"
    ADD = "ADD"
    REMOVE = "REMOVE"
    UPDATE = "UPDATE"
    OBSERVE = "OBSERVE"
    INFER = "INFER"
    MERGE = "MERGE"

class DeltaOp(str, Enum):
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"

class DeltaPatch(BaseModel):
    op: DeltaOp
    path: str
    value: Any

class TruthVector(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    authority: float = Field(..., ge=0.0, le=1.0)
    # freshness removed - derived property
    corroboration: float = Field(..., ge=0.0)

    class Config:
        frozen = True

class Provenance(BaseModel):
    producer_id: str
    gateway_timestamp: datetime
    source_system: Optional[str] = None

    class Config:
        frozen = True

class Event(BaseModel):
    id: uuid.UUID # No default factory - must be deterministic
    namespace: str # No default "user" - must be explicit
    timestamp: datetime # No default factory
    actor: ActorEnum
    action: ActionEnum
    object_id: uuid.UUID
    delta: List[DeltaPatch] # Typed delta
    antecedents: List[uuid.UUID] = Field(default_factory=list)
    truth_vector: TruthVector
    provenance: Optional[Provenance] = None

    class Config:
        frozen = True

class EntityState(BaseModel):
    entity_id: uuid.UUID
    namespace: str
    current_value: Dict[str, Any]
    truth_vector: TruthVector
    version: int = 0
    last_event_id: uuid.UUID
    updated_at: datetime # No default factory

    class Config:
        frozen = True
