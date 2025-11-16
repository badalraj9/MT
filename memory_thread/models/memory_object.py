from __future__ import annotations
from typing import Literal, Optional, List
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
    importance: float  # Constrained to 0.0–1.0 in the database schema
    created_at: datetime
    updated_at: datetime
    pinned: bool
    domain: Optional[str]
    current_value: Optional[str]
    history: Optional[list]
    embedding: List[float]
