"""
Memory Thread: Meta-Cognitive Layer
====================================
Phase 10.3: Autonomic Cognition

Self-aware cognition that:
1. Knows what it knows (confidence calibration)
2. Knows what it doesn't know (knowledge gap detection)
3. Can explain its uncertainty (confidence decomposition)
4. Requests information proactively (knowledge acquisition)

Target: 85% calibrated confidence (when says 80% confident, is right 80% of time)
"""

import logging
import json
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ============================================================================
# DATA CLASSES
# ============================================================================

class ConfidenceLevel(Enum):
    CERTAIN = "certain"       # 95%+
    CONFIDENT = "confident"   # 80-95%
    PROBABLE = "probable"     # 60-80%
    UNCERTAIN = "uncertain"   # 40-60%
    SPECULATIVE = "speculative"  # <40%


class GapType(Enum):
    MISSING_ENTITY = "missing_entity"
    MISSING_RELATION = "missing_relation"
    STALE_INFORMATION = "stale_information"
    CONFLICTING_INFORMATION = "conflicting_information"
    LOW_CONFIDENCE = "low_confidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass
class ConfidenceAssessment:
    """Detailed confidence breakdown for a belief or query result"""
    value: Any
    overall_confidence: float
    confidence_level: ConfidenceLevel
    factors: Dict[str, float]  # Contributing factors
    explanation: str
    calibration_adjustment: float = 0.0  # Historical calibration offset


@dataclass
class KnowledgeGap:
    """An identified gap in knowledge"""
    id: str
    gap_type: GapType
    description: str
    importance: float  # How important to fill this gap
    context: Dict[str, Any]
    suggested_action: str
    discovered_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QueryResponse:
    """A query response with meta-cognitive annotations"""
    answer: Any
    confidence: ConfidenceAssessment
    knowledge_gaps: List[KnowledgeGap]
    hedging: str  # Natural language uncertainty expression
    sources: List[str]


# ============================================================================
# CONFIDENCE CALIBRATOR
# ============================================================================

class ConfidenceCalibrator:
    """
    Calibrates confidence scores based on historical accuracy.
    Ensures stated confidence matches actual accuracy.
    """
    
    def __init__(self):
        self.pg = PostgresClient()
        self._calibration_curve: Dict[int, float] = {}  # bucket -> adjustment
        self._load_calibration()
    
    def _load_calibration(self):
        """Load calibration curve from historical data"""
        # Default calibration (assume slight overconfidence)
        self._calibration_curve = {
            95: -0.05,  # 95% claims are actually ~90% accurate
            85: -0.03,
            75: 0.0,
            65: 0.0,
            55: 0.02,  # Low confidence is slightly underconfident
            45: 0.05,
        }
    
    def calibrate(self, raw_confidence: float) -> float:
        """Apply calibration to raw confidence score"""
        bucket = int(raw_confidence * 100 // 10) * 10 + 5  # e.g., 0.87 -> 85
        adjustment = self._calibration_curve.get(bucket, 0.0)
        
        calibrated = raw_confidence + adjustment
        return max(0.0, min(1.0, calibrated))
    
    def record_outcome(self, stated_confidence: float, was_correct: bool):
        """Record outcome for calibration improvement"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS calibration_log (
                    id SERIAL PRIMARY KEY,
                    stated_confidence FLOAT,
                    was_correct BOOLEAN,
                    recorded_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                INSERT INTO calibration_log (stated_confidence, was_correct)
                VALUES (%s, %s)
            """, (stated_confidence, was_correct))
    
    def update_calibration(self):
        """Update calibration curve from recent outcomes"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT 
                    FLOOR(stated_confidence * 10) * 10 as bucket,
                    AVG(CASE WHEN was_correct THEN 1.0 ELSE 0.0 END) as actual_accuracy,
                    COUNT(*) as samples
                FROM calibration_log
                WHERE recorded_at > NOW() - INTERVAL '30 days'
                GROUP BY bucket
                HAVING COUNT(*) >= 10
            """)
            
            for row in cur.fetchall():
                bucket = int(row[0])
                actual = row[1]
                stated = (bucket + 5) / 100  # Midpoint of bucket
                
                # Adjustment = actual - stated (positive means underconfident)
                self._calibration_curve[bucket + 5] = actual - stated


# ============================================================================
# KNOWLEDGE GAP DETECTOR
# ============================================================================

class KnowledgeGapDetector:
    """
    Identifies what the system doesn't know.
    Proactively discovers missing information.
    """
    
    def __init__(self):
        self.pg = PostgresClient()
        self.graph = GraphService()
    
    def detect_gaps(self, entity_id: str = None) -> List[KnowledgeGap]:
        """Detect knowledge gaps for an entity or system-wide"""
        gaps = []
        
        if entity_id:
            gaps.extend(self._detect_entity_gaps(entity_id))
        else:
            gaps.extend(self._detect_global_gaps())
        
        # Sort by importance
        gaps.sort(key=lambda g: g.importance, reverse=True)
        return gaps
    
    def _detect_entity_gaps(self, entity_id: str) -> List[KnowledgeGap]:
        """Detect gaps for a specific entity"""
        gaps = []
        
        with self.pg.get_cursor() as cur:
            # Check for missing expected relations
            cur.execute("""
                SELECT e.entity_type 
                FROM entities e 
                WHERE e.id = %s
            """, (entity_id,))
            row = cur.fetchone()
            entity_type = row[0] if row else 'unknown'
            
            # Get existing relations
            cur.execute("""
                SELECT relation_type FROM relations 
                WHERE source_entity_id = %s
            """, (entity_id,))
            existing_relations = set(r[0] for r in cur.fetchall())
            
            # Expected relations by type
            expected = {
                'person': ['works_at', 'lives_in', 'knows'],
                'organization': ['has_member', 'located_in'],
                'place': ['contains', 'near'],
            }
            
            expected_rels = expected.get(entity_type, [])
            for rel in expected_rels:
                if rel not in existing_relations:
                    gaps.append(KnowledgeGap(
                        id=f"gap-{entity_id[:8]}-{rel}",
                        gap_type=GapType.MISSING_RELATION,
                        description=f"No '{rel}' relation for {entity_type}",
                        importance=0.6,
                        context={'entity_id': entity_id, 'relation': rel},
                        suggested_action=f"Ask: What is the {rel} for this entity?"
                    ))
            
            # Check for stale state
            cur.execute("""
                SELECT updated_at FROM entity_state 
                WHERE entity_id = %s
            """, (entity_id,))
            state_row = cur.fetchone()
            if state_row and state_row[0]:
                age = (datetime.utcnow() - state_row[0]).days
                if age > 90:
                    gaps.append(KnowledgeGap(
                        id=f"gap-stale-{entity_id[:8]}",
                        gap_type=GapType.STALE_INFORMATION,
                        description=f"State not updated in {age} days",
                        importance=0.5,
                        context={'entity_id': entity_id, 'days_old': age},
                        suggested_action="Verify current state"
                    ))
            
            # Check for low-confidence facts
            cur.execute("""
                SELECT relation_type, confidence 
                FROM relations 
                WHERE source_entity_id = %s AND confidence < 0.5
            """, (entity_id,))
            for row in cur.fetchall():
                gaps.append(KnowledgeGap(
                    id=f"gap-conf-{entity_id[:8]}-{row[0]}",
                    gap_type=GapType.LOW_CONFIDENCE,
                    description=f"Low confidence ({row[1]:.0%}) on '{row[0]}'",
                    importance=0.7,
                    context={'entity_id': entity_id, 'relation': row[0], 'confidence': row[1]},
                    suggested_action="Seek corroborating evidence"
                ))
        
        return gaps
    
    def _detect_global_gaps(self) -> List[KnowledgeGap]:
        """Detect system-wide knowledge gaps"""
        gaps = []
        
        with self.pg.get_cursor() as cur:
            # Find entities with no relations
            cur.execute("""
                SELECT e.id, e.name 
                FROM entities e
                LEFT JOIN relations r ON e.id = r.source_entity_id
                WHERE r.id IS NULL
                LIMIT 10
            """)
            for row in cur.fetchall():
                gaps.append(KnowledgeGap(
                    id=f"gap-orphan-{row[0][:8]}",
                    gap_type=GapType.MISSING_RELATION,
                    description=f"Entity '{row[1]}' has no outgoing relations",
                    importance=0.4,
                    context={'entity_id': str(row[0])},
                    suggested_action="Determine relationships for this entity"
                ))
            
            # Find conflicting information
            cur.execute("""
                SELECT r1.source_entity_id, r1.target_entity_id, r2.target_entity_id
                FROM relations r1
                JOIN relations r2 ON r1.source_entity_id = r2.source_entity_id
                WHERE r1.relation_type = 'located_in' 
                  AND r2.relation_type = 'located_in'
                  AND r1.target_entity_id != r2.target_entity_id
                LIMIT 5
            """)
            for row in cur.fetchall():
                gaps.append(KnowledgeGap(
                    id=f"gap-conflict-{row[0][:8]}",
                    gap_type=GapType.CONFLICTING_INFORMATION,
                    description="Entity has conflicting locations",
                    importance=0.9,
                    context={'entity_id': str(row[0]), 'loc1': str(row[1]), 'loc2': str(row[2])},
                    suggested_action="Resolve location conflict"
                ))
        
        return gaps


# ============================================================================
# UNCERTAINTY EXPRESSER
# ============================================================================

class UncertaintyExpresser:
    """
    Generates natural language uncertainty expressions.
    Helps the system communicate what it knows and doesn't know.
    """
    
    CERTAINTY_PHRASES = {
        ConfidenceLevel.CERTAIN: [
            "I'm confident that",
            "Based on strong evidence,",
            "It's well established that"
        ],
        ConfidenceLevel.CONFIDENT: [
            "I believe that",
            "Evidence suggests that",
            "It's likely that"
        ],
        ConfidenceLevel.PROBABLE: [
            "It appears that",
            "There's reasonable evidence that",
            "It's probable that"
        ],
        ConfidenceLevel.UNCERTAIN: [
            "I'm uncertain, but",
            "The evidence is mixed, however",
            "It's possible that"
        ],
        ConfidenceLevel.SPECULATIVE: [
            "This is speculative, but",
            "I'm guessing that",
            "Without enough data, I suspect"
        ]
    }
    
    def express(self, confidence: float, statement: str) -> str:
        """Generate natural uncertainty expression"""
        level = self._confidence_to_level(confidence)
        phrases = self.CERTAINTY_PHRASES.get(level, [""])
        
        import random
        hedge = random.choice(phrases)
        
        return f"{hedge} {statement}"
    
    def _confidence_to_level(self, confidence: float) -> ConfidenceLevel:
        """Map confidence score to level"""
        if confidence >= 0.95:
            return ConfidenceLevel.CERTAIN
        elif confidence >= 0.80:
            return ConfidenceLevel.CONFIDENT
        elif confidence >= 0.60:
            return ConfidenceLevel.PROBABLE
        elif confidence >= 0.40:
            return ConfidenceLevel.UNCERTAIN
        else:
            return ConfidenceLevel.SPECULATIVE
    
    def explain_uncertainty(self, assessment: ConfidenceAssessment) -> str:
        """Generate detailed uncertainty explanation"""
        factors = assessment.factors
        
        explanations = []
        
        for factor, impact in sorted(factors.items(), key=lambda x: abs(x[1]), reverse=True):
            if impact > 0.1:
                explanations.append(f"Strong {factor} (+{impact:.0%})")
            elif impact < -0.1:
                explanations.append(f"Weak {factor} ({impact:.0%})")
        
        if not explanations:
            return "Confidence based on average evidence quality."
        
        return "Confidence factors: " + ", ".join(explanations[:3])


# ============================================================================
# META-COGNITIVE ENGINE
# ============================================================================

class MetaCognitiveEngine:
    """
    Main meta-cognitive interface.
    Provides self-aware responses with confidence and gap awareness.
    """
    
    def __init__(self):
        self.calibrator = ConfidenceCalibrator()
        self.gap_detector = KnowledgeGapDetector()
        self.expresser = UncertaintyExpresser()
    
    def assess_confidence(self, value: Any, 
                          raw_confidence: float,
                          factors: Dict[str, float] = None) -> ConfidenceAssessment:
        """Build a full confidence assessment"""
        if factors is None:
            factors = {'base': raw_confidence}
        
        # Calibrate
        calibrated = self.calibrator.calibrate(raw_confidence)
        level = self.expresser._confidence_to_level(calibrated)
        
        # Generate explanation
        explanation = self.expresser.explain_uncertainty(ConfidenceAssessment(
            value=value,
            overall_confidence=calibrated,
            confidence_level=level,
            factors=factors,
            explanation=""
        ))
        
        return ConfidenceAssessment(
            value=value,
            overall_confidence=calibrated,
            confidence_level=level,
            factors=factors,
            explanation=explanation,
            calibration_adjustment=calibrated - raw_confidence
        )
    
    def answer_with_metacognition(self, query: str, 
                                   answer: Any,
                                   confidence: float,
                                   entity_id: str = None) -> QueryResponse:
        """Wrap an answer with meta-cognitive context"""
        # Assess confidence
        assessment = self.assess_confidence(answer, confidence)
        
        # Detect knowledge gaps
        gaps = self.gap_detector.detect_gaps(entity_id) if entity_id else []
        
        # Generate hedging
        hedging = self.expresser.express(assessment.overall_confidence, str(answer))
        
        return QueryResponse(
            answer=answer,
            confidence=assessment,
            knowledge_gaps=gaps[:3],  # Top 3 gaps
            hedging=hedging,
            sources=[]  # Would be populated by retrieval
        )
    
    def what_dont_i_know(self, entity_id: str = None) -> List[KnowledgeGap]:
        """Explicitly ask what information is missing"""
        return self.gap_detector.detect_gaps(entity_id)
    
    def record_calibration(self, confidence: float, was_correct: bool):
        """Record outcome for calibration"""
        self.calibrator.record_outcome(confidence, was_correct)
    
    def get_calibration_status(self) -> Dict[str, Any]:
        """Get current calibration status"""
        return {
            'calibration_curve': self.calibrator._calibration_curve,
            'last_updated': 'dynamic'
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def assess(value: Any, confidence: float) -> ConfidenceAssessment:
    """Quick confidence assessment"""
    return MetaCognitiveEngine().assess_confidence(value, confidence)


def find_gaps(entity_id: str = None) -> List[KnowledgeGap]:
    """Quick gap detection"""
    return KnowledgeGapDetector().detect_gaps(entity_id)


def calibrate_confidence(raw: float) -> float:
    """Quick calibration"""
    return ConfidenceCalibrator().calibrate(raw)
