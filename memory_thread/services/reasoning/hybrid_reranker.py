"""
Memory Thread: Hybrid Reranker
==============================
Phase 8.3: Semantic + Symbolic Fusion

Production-grade retrieval pipeline combining:
1. Vector Search (semantic similarity)
2. Graph Filtering (structural relevance)
3. Rule Boosting (symbolic inference)
4. Truth Scoring (confidence ranking)

Target: 20-30% precision improvement vs vector-only
Performance: <100ms P95 latency
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ============================================================================
# QUERY TYPES FOR STRATEGY SELECTION
# ============================================================================

class QueryType(Enum):
    FACTUAL = "factual"        # "What is X?" - Direct lookup
    RELATIONAL = "relational"  # "How is X related to Y?" - Graph query
    TEMPORAL = "temporal"      # "When did X happen?" - Time-based
    INFERENTIAL = "inferential"  # "Why is X?" - Reasoning required
    EXPLORATORY = "exploratory"  # "Tell me about X" - Broad search


@dataclass
class RerankerConfig:
    """Configuration for reranker weights"""
    vector_weight: float = 0.4
    graph_weight: float = 0.25
    rule_weight: float = 0.2
    truth_weight: float = 0.15
    
    # Stage parameters
    vector_candidates: int = 100
    graph_filter_size: int = 30
    final_results: int = 10


@dataclass
class ScoredResult:
    """A result with component scores"""
    entity_id: str
    entity_name: str
    content: str
    
    # Component scores
    vector_score: float = 0.0
    graph_score: float = 0.0
    rule_score: float = 0.0
    truth_score: float = 0.0
    
    # Final score
    final_score: float = 0.0
    
    # Provenance
    matched_via: List[str] = field(default_factory=list)
    inferred_relations: int = 0
    truth_vector: Dict[str, float] = field(default_factory=dict)


@dataclass
class RerankerResult:
    """Complete result from the reranker pipeline"""
    query: str
    query_type: QueryType
    results: List[ScoredResult]
    stage_timings: Dict[str, float]
    total_time_ms: float
    strategy_used: str


# ============================================================================
# QUERY PLANNER
# ============================================================================

class QueryPlanner:
    """
    Determines optimal retrieval strategy based on query characteristics.
    """
    
    def classify_query(self, query: str) -> QueryType:
        """Classify query type for strategy selection"""
        query_lower = query.lower()
        
        # Temporal keywords
        if any(kw in query_lower for kw in ['when', 'date', 'time', 'before', 'after', 'during']):
            return QueryType.TEMPORAL
        
        # Relational keywords
        if any(kw in query_lower for kw in ['related to', 'connected', 'between', 'path', 'link']):
            return QueryType.RELATIONAL
        
        # Inferential keywords
        if any(kw in query_lower for kw in ['why', 'because', 'reason', 'cause', 'infer']):
            return QueryType.INFERENTIAL
        
        # Factual keywords
        if any(kw in query_lower for kw in ['what is', 'who is', 'where is', 'define']):
            return QueryType.FACTUAL
        
        # Default to exploratory
        return QueryType.EXPLORATORY
    
    def get_strategy(self, query_type: QueryType) -> Dict[str, Any]:
        """Get optimal strategy for query type"""
        strategies = {
            QueryType.FACTUAL: {
                'name': 'direct_lookup',
                'vector_weight': 0.6,
                'graph_weight': 0.1,
                'rule_weight': 0.1,
                'truth_weight': 0.2,
                'max_depth': 1
            },
            QueryType.RELATIONAL: {
                'name': 'graph_first',
                'vector_weight': 0.2,
                'graph_weight': 0.5,
                'rule_weight': 0.15,
                'truth_weight': 0.15,
                'max_depth': 3
            },
            QueryType.TEMPORAL: {
                'name': 'temporal_search',
                'vector_weight': 0.3,
                'graph_weight': 0.2,
                'rule_weight': 0.2,
                'truth_weight': 0.3,
                'max_depth': 2,
                'use_temporal_filter': True
            },
            QueryType.INFERENTIAL: {
                'name': 'reasoning_heavy',
                'vector_weight': 0.2,
                'graph_weight': 0.25,
                'rule_weight': 0.4,
                'truth_weight': 0.15,
                'max_depth': 4,
                'run_inference': True
            },
            QueryType.EXPLORATORY: {
                'name': 'balanced',
                'vector_weight': 0.4,
                'graph_weight': 0.25,
                'rule_weight': 0.2,
                'truth_weight': 0.15,
                'max_depth': 2
            }
        }
        return strategies.get(query_type, strategies[QueryType.EXPLORATORY])


# ============================================================================
# HYBRID RERANKER
# ============================================================================

class HybridReranker:
    """
    Production hybrid retrieval pipeline.
    
    Pipeline Stages:
    1. Vector Search: Get initial candidates by semantic similarity
    2. Graph Filter: Filter by structural relevance to query entities
    3. Rule Boost: Apply inference rules for symbolic boosting
    4. Truth Score: Apply truth vector ranking
    5. Combine: Weighted combination of all scores
    """
    
    def __init__(self, config: Optional[RerankerConfig] = None):
        self.config = config or RerankerConfig()
        self.pg = PostgresClient()
        self.graph = GraphService()
        self.planner = QueryPlanner()
    
    def rerank(self, query: str, vector_results: List[Dict], 
               target_entity: Optional[str] = None) -> RerankerResult:
        """
        Full reranking pipeline.
        
        Args:
            query: The search query
            vector_results: Initial results from vector search
            target_entity: Optional entity ID to focus graph search on
        """
        start_time = time.perf_counter()
        timings = {}
        
        # 1. Classify query
        query_type = self.planner.classify_query(query)
        strategy = self.planner.get_strategy(query_type)
        
        # 2. Stage 1: Process vector results
        t0 = time.perf_counter()
        candidates = self._process_vector_results(vector_results)
        timings['vector_processing'] = (time.perf_counter() - t0) * 1000
        
        # 3. Stage 2: Graph filtering
        t0 = time.perf_counter()
        candidates = self._apply_graph_scoring(candidates, target_entity, strategy)
        timings['graph_scoring'] = (time.perf_counter() - t0) * 1000
        
        # 4. Stage 3: Rule boosting
        t0 = time.perf_counter()
        candidates = self._apply_rule_boosting(candidates, strategy)
        timings['rule_boosting'] = (time.perf_counter() - t0) * 1000
        
        # 5. Stage 4: Truth scoring
        t0 = time.perf_counter()
        candidates = self._apply_truth_scoring(candidates)
        timings['truth_scoring'] = (time.perf_counter() - t0) * 1000
        
        # 6. Stage 5: Final combination
        t0 = time.perf_counter()
        results = self._combine_scores(candidates, strategy)
        timings['score_combination'] = (time.perf_counter() - t0) * 1000
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        return RerankerResult(
            query=query,
            query_type=query_type,
            results=results[:self.config.final_results],
            stage_timings=timings,
            total_time_ms=round(total_time, 2),
            strategy_used=strategy['name']
        )
    
    # ========================================================================
    # PIPELINE STAGES
    # ========================================================================
    
    def _process_vector_results(self, vector_results: List[Dict]) -> List[ScoredResult]:
        """Convert vector search results to ScoredResult objects"""
        candidates = []
        
        for i, result in enumerate(vector_results[:self.config.vector_candidates]):
            # Normalize vector score (assuming 0-1 range from Qdrant)
            vec_score = result.get('score', 0.0)
            if vec_score > 1.0:
                vec_score = vec_score / 100.0  # Handle percentage scores
            
            candidates.append(ScoredResult(
                entity_id=result.get('id', ''),
                entity_name=result.get('content', '')[:50],
                content=result.get('content', ''),
                vector_score=vec_score,
                matched_via=['vector_search']
            ))
        
        return candidates
    
    def _apply_graph_scoring(self, candidates: List[ScoredResult],
                             target_entity: Optional[str],
                             strategy: Dict) -> List[ScoredResult]:
        """Score candidates based on graph connectivity"""
        if not target_entity:
            return candidates
        
        max_depth = strategy.get('max_depth', 2)
        
        for candidate in candidates:
            # Check if candidate is connected to target
            path = self.graph.find_path(
                uuid.UUID(target_entity) if target_entity else None,
                uuid.UUID(candidate.entity_id) if candidate.entity_id else None,
                max_depth=max_depth
            )
            
            if path is not None:
                # Score based on path length and confidence
                path_len = len(path)
                if path_len == 0:
                    candidate.graph_score = 1.0  # Same entity
                else:
                    # Decay score with distance
                    path_confidence = 1.0
                    for step in path:
                        path_confidence *= step.get('confidence', 0.8)
                    candidate.graph_score = path_confidence * (0.9 ** path_len)
                
                candidate.matched_via.append('graph_path')
            
            # Check for inferred relations
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM relations
                    WHERE is_inferred = TRUE
                      AND (source_entity_id = %s OR target_entity_id = %s)
                """, (candidate.entity_id, candidate.entity_id))
                row = cur.fetchone()
                count = row[0] if isinstance(row, tuple) else row['count']
                candidate.inferred_relations = count
        
        return candidates
    
    def _apply_rule_boosting(self, candidates: List[ScoredResult],
                             strategy: Dict) -> List[ScoredResult]:
        """Apply rule-based boosting to candidates"""
        run_inference = strategy.get('run_inference', False)
        
        for candidate in candidates:
            # Base rule score from inferred relations
            if candidate.inferred_relations > 0:
                # More inferred relations = higher confidence in this entity
                candidate.rule_score = min(1.0, 0.5 + (candidate.inferred_relations * 0.1))
                candidate.matched_via.append('rule_inferred')
            
            # If strategy calls for inference, check for applicable rules
            if run_inference:
                # Check if entity has high-confidence inferred knowledge
                with self.pg.get_cursor() as cur:
                    cur.execute("""
                        SELECT AVG(confidence) FROM relations
                        WHERE is_inferred = TRUE
                          AND (source_entity_id = %s OR target_entity_id = %s)
                          AND confidence > 0.7
                    """, (candidate.entity_id, candidate.entity_id))
                    row = cur.fetchone()
                    avg_conf = row[0] if row and row[0] else 0.0
                    if avg_conf > 0:
                        candidate.rule_score = max(candidate.rule_score, avg_conf)
        
        return candidates
    
    def _apply_truth_scoring(self, candidates: List[ScoredResult]) -> List[ScoredResult]:
        """Apply truth vector scoring"""
        for candidate in candidates:
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    SELECT truth_vector FROM entity_state
                    WHERE entity_id = %s
                """, (candidate.entity_id,))
                row = cur.fetchone()
                
                if row:
                    tv = row['truth_vector'] if isinstance(row, dict) else row[0]
                    if isinstance(tv, str):
                        import json
                        tv = json.loads(tv)
                    
                    if tv:
                        # Calculate truth score: C × A × F × log(1 + R)
                        import math
                        confidence = tv.get('confidence', 0.5)
                        authority = tv.get('authority', 0.5)
                        freshness = tv.get('freshness', 0.5)
                        corroboration = tv.get('corroboration', 0)
                        
                        truth_score = confidence * authority * freshness * math.log(1 + corroboration + 1)
                        truth_score = min(1.0, truth_score)  # Normalize
                        
                        candidate.truth_score = truth_score
                        candidate.truth_vector = tv
                        candidate.matched_via.append('truth_vector')
        
        return candidates
    
    def _combine_scores(self, candidates: List[ScoredResult],
                        strategy: Dict) -> List[ScoredResult]:
        """Combine all scores using strategy weights"""
        w_vec = strategy.get('vector_weight', self.config.vector_weight)
        w_graph = strategy.get('graph_weight', self.config.graph_weight)
        w_rule = strategy.get('rule_weight', self.config.rule_weight)
        w_truth = strategy.get('truth_weight', self.config.truth_weight)
        
        for candidate in candidates:
            candidate.final_score = (
                w_vec * candidate.vector_score +
                w_graph * candidate.graph_score +
                w_rule * candidate.rule_score +
                w_truth * candidate.truth_score
            )
        
        # Sort by final score
        candidates.sort(key=lambda x: x.final_score, reverse=True)
        
        return candidates


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def hybrid_search(query: str, vector_results: List[Dict], 
                  target_entity: Optional[str] = None) -> RerankerResult:
    """Convenience function for hybrid search"""
    reranker = HybridReranker()
    return reranker.rerank(query, vector_results, target_entity)


# Missing import (need to add at top level)
import uuid
