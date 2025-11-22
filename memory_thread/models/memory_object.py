from __future__ import annotations
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

MemoryType = Literal[
    "identity",
    "preference",
    "event",
    "summary",
    "timeline"
]

class MemoryObject(BaseModel):
    """
    Represents one memory entry in the system.
    Fully aligned with the Memory Thread specification.
    """

    # Core fields
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    content: str
    memory_type: MemoryType
    extracted: Optional[Dict] = None
    importance: float = 0.5

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: Optional[datetime] = None

    # Timeline history
    history: Optional[List[Dict]] = None

    # Transient field — not stored in Postgres
    embedding: Optional[List[float]] = None