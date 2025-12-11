from __future__ import annotations
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

MemoryType = Literal["identity", "preference", "event", "fact", "task", "belief", "timeline", "other"]
MemorySource = Literal["user", "system", "model"]

class MemoryMetadata(BaseModel):
    source: MemorySource = "user"
    negation: bool = False
    emotion: Optional[str] = None
    deadline: Optional[datetime] = None

    class Config:
        frozen = True

class MemoryObject(BaseModel):
    id: uuid.UUID # Deterministic ID required
    content: str
    memory_type: MemoryType
    importance: float = 0.5
    entities: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    domain: Optional[str] = None

    class Config:
        frozen = True
