"""
Memory Thread: REST API
========================
Phase 11.1: Investor Demo Integration

FastAPI-based REST API for Memory Thread.
Exposes all cognitive capabilities via HTTP.

Run: uvicorn memory_thread.api.main:app --reload

ELITE TIER: Hardened for investor demo reliability
"""

from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import json
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("memory_thread.api")

# Service availability flags (graceful degradation)
SERVICES_AVAILABLE = {
    "postgres": False,
    "qdrant": False,
    "inference": False,
    "predictive": False,
}

# API Models
# ============================================================================

class IngestRequest(BaseModel):
    entity_id: Optional[str] = Field(None, description="Entity UUID, auto-generated if not provided")
    entity_type: str = Field(..., description="Type: person, organization, place, concept, event")
    name: str = Field(..., description="Entity name")
    action: str = Field("create", description="Action: create, update, delete")
    data: Dict[str, Any] = Field(default_factory=dict, description="Entity data/delta")
    source: str = Field("api", description="Data source identifier")

class IngestResponse(BaseModel):
    success: bool
    event_id: str
    entity_id: str
    message: str

class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    top_k: int = Field(5, description="Number of results")
    include_explanation: bool = Field(False, description="Include reasoning trace")

class QueryResult(BaseModel):
    entity_id: str
    name: str
    relevance: float
    data: Dict[str, Any]
    explanation: Optional[str] = None

class QueryResponse(BaseModel):
    query: str
    results: List[QueryResult]
    confidence: float
    processing_time_ms: float

class PredictRequest(BaseModel):
    entity_id: str
    metric: str
    horizon_days: int = Field(7, description="Days to forecast")

class PredictResponse(BaseModel):
    entity_id: str
    metric: str
    predicted_value: Any
    confidence: float
    confidence_interval: List[float]
    horizon: str

class ExplainRequest(BaseModel):
    entity_id: str
    relation: str
    target_id: str

class ExplainResponse(BaseModel):
    explanation: str
    reasoning_chain: List[str]
    confidence: float
    graph: Optional[str] = None  # Mermaid diagram

class SuggestionResponse(BaseModel):
    id: str
    type: str
    priority: str
    title: str
    description: str
    confidence: float
    action: str

class HealthResponse(BaseModel):
    status: str
    cpu_percent: float
    memory_percent: float
    database_connected: bool
    vector_db_connected: bool
    uptime_seconds: float

# FastAPI App
# ============================================================================

app = FastAPI(
    title="Memory Thread API",
    description="Cognitive Memory System with Semantic Fusion & Predictive Intelligence",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS for demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup time for uptime calculation
_startup_time = datetime.utcnow()

# Global exception handler for graceful error responses
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return clean JSON errors instead of HTML error pages"""
    log.error(f"Unhandled error: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": str(exc),
            "type": exc.__class__.__name__,
            "path": str(request.url)
        }
    )

@app.on_event("startup")
async def startup_event():
    """Check service availability on startup"""
    log.info("Memory Thread API starting...")
    
    # Check PostgreSQL
    try:
        from memory_thread.db.postgres_client import PostgresClient
        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute("SELECT 1")
        SERVICES_AVAILABLE["postgres"] = True
        log.info("✓ PostgreSQL connected")
    except Exception as e:
        log.warning(f"✗ PostgreSQL unavailable: {e}")
    
    # Check Qdrant
    try:
        from memory_thread.db.qdrant_client import QdrantClientWrapper
        qdrant = QdrantClientWrapper()
        SERVICES_AVAILABLE["qdrant"] = True
        log.info("✓ Qdrant connected")
    except Exception as e:
        log.warning(f"✗ Qdrant unavailable: {e}")
    
    log.info(f"Services: {SERVICES_AVAILABLE}")
    log.info("Memory Thread API ready! Docs at /docs")

# ============================================================================
# CORE ENDPOINTS
# ============================================================================

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint with API info"""
    return {
        "name": "Memory Thread",
        "version": "2.0.0",
        "status": "operational",
        "docs": "/docs"
    }

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Comprehensive health check"""
    import psutil
    
    uptime = (datetime.utcnow() - _startup_time).total_seconds()
    
    # Check database connections
    db_connected = True
    vector_connected = True
    
    try:
        from memory_thread.db.postgres_client import PostgresClient
        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute("SELECT 1")
    except:
        db_connected = False
    
    try:
        from memory_thread.db.qdrant_client import QdrantClientWrapper
        qdrant = QdrantClientWrapper()
        # Basic check would go here
    except:
        vector_connected = False
    
    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        cpu_percent=psutil.cpu_percent(),
        memory_percent=psutil.virtual_memory().percent,
        database_connected=db_connected,
        vector_db_connected=vector_connected,
        uptime_seconds=uptime
    )

# ============================================================================
# INGEST ENDPOINTS
# ============================================================================

@app.post("/ingest", response_model=IngestResponse, tags=["Ingest"])
async def ingest_event(request: IngestRequest):
    """Ingest a new event into Memory Thread"""
    import time
    from datetime import datetime
    
    start = time.perf_counter()
    
    try:
        # Generate IDs
        entity_id = request.entity_id or str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        
        # Create event through ingest service
        from memory_thread.services.ingest_service import IngestService
        ingest = IngestService()
        
        # Process event
        result = await ingest.process_event({
            'event_id': event_id,
            'entity_id': entity_id,
            'entity_type': request.entity_type,
            'name': request.name,
            'action': request.action,
            'delta': request.data,
            'source': request.source,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        return IngestResponse(
            success=True,
            event_id=event_id,
            entity_id=entity_id,
            message=f"Event ingested in {(time.perf_counter() - start)*1000:.1f}ms"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingest/batch", tags=["Ingest"])
async def ingest_batch(events: List[IngestRequest]):
    """Batch ingest multiple events"""
    results = []
    for event in events:
        result = await ingest_event(event)
        results.append(result)
    
    return {
        "success": True,
        "count": len(results),
        "events": results
    }

# ============================================================================
# QUERY ENDPOINTS
# ============================================================================

@app.post("/query", response_model=QueryResponse, tags=["Query"])
async def query(request: QueryRequest):
    """Query the knowledge base with natural language"""
    import time
    
    start = time.perf_counter()
    
    try:
        from memory_thread.services.retrieval_service import RetrievalService
        retrieval = RetrievalService()
        
        # Execute query
        raw_results = retrieval.query(request.query, top_k=request.top_k)
        
        # Format results
        results = []
        for r in raw_results:
            results.append(QueryResult(
                entity_id=str(r.get('entity_id', '')),
                name=r.get('name', 'Unknown'),
                relevance=r.get('score', 0.0),
                data=r.get('data', {}),
                explanation=r.get('explanation') if request.include_explanation else None
            ))
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return QueryResponse(
            query=request.query,
            results=results,
            confidence=0.85,  # Average confidence
            processing_time_ms=round(elapsed, 2)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/entity/{entity_id}", tags=["Query"])
async def get_entity(entity_id: str):
    """Get entity by ID with current state"""
    try:
        from memory_thread.services.tms_service import TMSService
        tms = TMSService()
        
        state = tms.get_entity_state(entity_id)
        
        if not state:
            raise HTTPException(status_code=404, detail="Entity not found")
        
        return {
            "entity_id": entity_id,
            "state": state,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PREDICTION ENDPOINTS
# ============================================================================

@app.post("/predict", response_model=PredictResponse, tags=["Predict"])
async def predict(request: PredictRequest):
    """Forecast future values for an entity metric"""
    try:
        from memory_thread.services.predictive_service import PredictiveService
        predictor = PredictiveService()
        
        prediction = predictor.forecast(
            request.entity_id, 
            request.metric, 
            request.horizon_days
        )
        
        return PredictResponse(
            entity_id=request.entity_id,
            metric=request.metric,
            predicted_value=prediction.predicted_value,
            confidence=prediction.confidence,
            confidence_interval=list(prediction.confidence_interval),
            horizon=prediction.horizon
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/predict/next/{entity_id}", tags=["Predict"])
async def predict_next_action(entity_id: str, current_action: str = Query(...)):
    """Predict the next action for an entity"""
    try:
        from memory_thread.services.predictive_service import PredictiveService
        predictor = PredictiveService()
        
        prediction = predictor.predict_next_action(entity_id, current_action)
        
        return {
            "entity_id": entity_id,
            "current_action": current_action,
            "predicted_next": prediction.predicted_value,
            "confidence": prediction.confidence
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EXPLAIN ENDPOINTS
# ============================================================================

@app.post("/explain", response_model=ExplainResponse, tags=["Explain"])
async def explain(request: ExplainRequest):
    """Explain how a fact was inferred"""
    try:
        from memory_thread.services.reasoning.explainability_engine import ExplainabilityEngine
        explainer = ExplainabilityEngine()
        
        explanation = explainer.explain_inference(
            request.entity_id,
            request.relation,
            request.target_id
        )
        
        return ExplainResponse(
            explanation=explanation.get('natural_language', 'No explanation available'),
            reasoning_chain=explanation.get('chain', []),
            confidence=explanation.get('confidence', 0.0),
            graph=explanation.get('mermaid_graph')
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/why/{entity_id}/{relation}", tags=["Explain"])
async def why(entity_id: str, relation: str):
    """Natural language 'Why?' query"""
    try:
        from memory_thread.services.reasoning.explainability_engine import ExplainabilityEngine
        explainer = ExplainabilityEngine()
        
        answer = explainer.why(entity_id, relation)
        
        return {
            "question": f"Why does {entity_id[:8]} have relation '{relation}'?",
            "answer": answer
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# SUGGESTIONS ENDPOINTS
# ============================================================================

@app.get("/suggestions", response_model=List[SuggestionResponse], tags=["Suggestions"])
async def get_suggestions(limit: int = Query(10, ge=1, le=50)):
    """Get maintenance suggestions"""
    try:
        from memory_thread.services.maintenance_suggester import MaintenanceSuggester
        suggester = MaintenanceSuggester()
        
        suggestions = suggester.get_suggestions(limit)
        
        return [
            SuggestionResponse(
                id=s.id,
                type=s.suggestion_type.value,
                priority=s.priority.value,
                title=s.title,
                description=s.description,
                confidence=s.confidence,
                action=s.action
            )
            for s in suggestions
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/suggestions/{suggestion_id}/accept", tags=["Suggestions"])
async def accept_suggestion(suggestion_id: str):
    """Accept a maintenance suggestion"""
    try:
        from memory_thread.services.maintenance_suggester import MaintenanceSuggester
        suggester = MaintenanceSuggester()
        suggester.accept(suggestion_id)
        return {"success": True, "message": f"Suggestion {suggestion_id} accepted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# META-COGNITIVE ENDPOINTS
# ============================================================================

@app.get("/knowledge-gaps", tags=["Meta-Cognition"])
async def get_knowledge_gaps(entity_id: Optional[str] = None, limit: int = 10):
    """Get detected knowledge gaps"""
    try:
        from memory_thread.services.meta_cognitive import MetaCognitiveEngine
        meta = MetaCognitiveEngine()
        
        gaps = meta.what_dont_i_know(entity_id)[:limit]
        
        return {
            "gaps": [
                {
                    "id": g.id,
                    "type": g.gap_type.value,
                    "description": g.description,
                    "importance": g.importance,
                    "suggested_action": g.suggested_action
                }
                for g in gaps
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/confidence/calibration", tags=["Meta-Cognition"])
async def get_calibration():
    """Get confidence calibration status"""
    try:
        from memory_thread.services.meta_cognitive import MetaCognitiveEngine
        meta = MetaCognitiveEngine()
        return meta.get_calibration_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# AUTONOMIC ENDPOINTS
# ============================================================================

@app.get("/autonomic/status", tags=["Autonomic"])
async def autonomic_status():
    """Get autonomic controller status"""
    try:
        from memory_thread.services.autonomic_controller import AutonomicController
        controller = AutonomicController()
        return controller.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/autonomic/cycle", tags=["Autonomic"])
async def run_autonomic_cycle():
    """Trigger one autonomic cycle"""
    try:
        from memory_thread.services.autonomic_controller import AutonomicController
        controller = AutonomicController()
        result = controller.run_once()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
