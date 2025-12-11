from __future__ import annotations
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
import uuid

MemoryType = Literal["identity", "preference", "event", "fact", "task", "belief", "timeline", "other"]
MemorySource = Literal["user", "system", "model"]

class MemoryMetadata(BaseModel):
    source: MemorySource = "user"
    negation: bool = False
    emotion: Optional[str] = None
    deadline: Optional[str] = None # Datetime strings are safer for serialization if needed, but staying consistent with type hints usually prefers datetime. However, to be safe on serialization, I'll stick to basic types or expect explicit handling. Let's keep it simple.

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
