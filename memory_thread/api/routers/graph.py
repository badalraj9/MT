from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict
from uuid import UUID
from pydantic import BaseModel

from memory_thread.services.graph_service import GraphService
from memory_thread.services.reasoning.query_engine import QueryEngine
from memory_thread.services.reasoning.inference_engine import InferenceEngine

router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])

class Relation(BaseModel):
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str
    confidence: float
    is_inferred: bool
    metadata: Dict

class PathRequest(BaseModel):
    start_id: UUID
    end_id: UUID
    max_hops: int = 5

@router.get("/relations/{entity_id}", response_model=List[Relation])
async def get_relations(entity_id: UUID, direction: str = "out"):
    """
    Get relations for an entity.
    """
    graph = GraphService()
    rels = graph.get_relations(entity_id, direction)
    return rels

@router.post("/path", response_model=List[Relation])
async def find_path(request: PathRequest):
    """
    Find shortest path between two entities.
    """
    engine = QueryEngine()
    path = engine.find_path(request.start_id, request.end_id, request.max_hops)
    if path is None:
        raise HTTPException(status_code=404, detail="No path found")
    return path

@router.post("/infer/{entity_id}")
async def run_inference(entity_id: UUID):
    """
    Run inference rules on an entity and check for contradictions.
    """
    engine = InferenceEngine()
    engine.infer_transitive_relations(entity_id)
    engine.infer_symmetry(entity_id)
    engine.infer_inverse(entity_id)
    conflicts = engine.infer_contradictions(entity_id)

    return {"status": "completed", "conflicts": conflicts}
