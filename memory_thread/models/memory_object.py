from __future__ import annotations
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

# Expanded memory types from the manifest
MemoryType = Literal[
    "identity",
    "preference",
    "event",
    "fact",
    "task",
    "belief",
    "timeline",
    "other"
]

# Source of the memory
MemorySource = Literal["user", "system", "model"]

class MemoryMetadata(BaseModel):
    """
    Structured metadata object, as defined in the plugin manifest.
    """
    source: MemorySource = "user"
    negation: bool = False
    emotion: Optional[str] = None
    deadline: Optional[datetime] = None


class MemoryObject(BaseModel):
    """
    Represents one memory entry, aligned with the new plugin manifest schema.
    """
    # Core fields
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    content: str
    memory_type: MemoryType
    importance: float = 0.5

    # Extracted, top-level fields
    entities: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)

    # Graph-related fields
    relations: List[uuid.UUID] = Field(default_factory=list)

    # Structured metadata
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)

    # Timeline-specific fields (required by timeline_service)
    domain: Optional[str] = None
    current_value: Optional[str] = None
    history: Optional[List[Dict]] = None

    # Transient field — not stored in Postgres
    embedding: Optional[List[float]] = None
