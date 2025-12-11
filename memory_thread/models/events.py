from pydantic import BaseModel, Field, field_validator
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

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not (v.startswith("/") or "." in v):
            raise ValueError("Invalid delta path: must be JSON pointer (/) or dot-path (.)")
        return v

    class Config:
        frozen = True

class TruthVector(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    authority: float = Field(..., ge=0.0, le=1.0)
    # freshness removed
    corroboration: float = Field(..., ge=0.0)

    class Config:
        frozen = True

class Provenance(BaseModel):
    producer_id: str
    gateway_timestamp: datetime
    gateway_seq: int
    source_system: Optional[str] = None

    class Config:
        frozen = True

class Event(BaseModel):
    id: uuid.UUID
    namespace: str
    timestamp: datetime
    actor: ActorEnum
    action: ActionEnum
    object_id: uuid.UUID
    delta: List[DeltaPatch]
    antecedents: List[uuid.UUID] = Field(default_factory=list)
    truth_vector: TruthVector
    provenance: Provenance # Mandatory

    # New deterministic fields
    gateway_seq: int
    dedup_hash: Optional[str] = None

    class Config:
        frozen = True

class EntityState(BaseModel):
    entity_id: uuid.UUID
    namespace: str
    current_value: Dict[str, Any]
    truth_vector: TruthVector
    version: int = 0
    last_event_id: uuid.UUID
    updated_at: datetime

    class Config:
        frozen = True
