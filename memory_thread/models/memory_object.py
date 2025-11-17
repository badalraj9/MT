from __future__ import annotations
from typing import Literal, Optional, List, Dict
from pydantic import BaseModel
from datetime import datetime

class MemoryObject(BaseModel):
    """
    Pydantic model representing a single memory object, enforcing the
    data structure specified in the project plan.
    """
    id: str
    content: str
    memory_type: Literal["identity", "preference", "event", "summary", "timeline", "task"]
    extracted: dict
    importance: float
    created_at: datetime
    updated_at: datetime
    pinned: bool
    domain: Optional[str]
    current_value: Optional[str]
    history: Optional[List[Dict]]
    embedding: Optional[List[float]] = None # Embedding is transient, not stored.
