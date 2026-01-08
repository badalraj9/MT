"""
Memory Thread: Maintenance Suggester
=====================================
Phase 9.2: Predictive World Model

Automated detection and suggestion system for:
- Data quality issues (conflicts, inconsistencies)
- Staleness (outdated information)
- Missing relationships
- Consolidation opportunities

Target: >75% suggestion acceptance rate
"""

import logging
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from uuid import UUID

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ============================================================================
# DATA CLASSES
# ============================================================================

class SuggestionType(Enum):
    CONFLICT = "conflict"
    STALENESS = "staleness"
    MISSING_LINK = "missing_link"
    CONSOLIDATION = "consolidation"
    DUPLICATE = "duplicate"
    ANOMALY = "anomaly"


class Priority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Suggestion:
    """A maintenance suggestion"""
    id: str
    suggestion_type: SuggestionType
    priority: Priority
    entity_id: str
    title: str
    description: str
    confidence: float
    action: str  # Recommended action
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, accepted, rejected, deferred


# ============================================================================
# ISSUE DETECTORS
# ============================================================================

class ConflictDetector:
    """Detects conflicting facts in the knowledge graph"""
    
    def __init__(self):
        self.pg = PostgresClient()
    
    def detect(self) -> List[Suggestion]:
        """Find conflicting relations"""
        suggestions = []
        
        with self.pg.get_cursor() as cur:
            # Find entities with multiple conflicting locations
            cur.execute("""
                SELECT r1.source_entity_id, r1.target_entity_id as loc1, r2.target_entity_id as loc2
                FROM relations r1
                JOIN relations r2 ON r1.source_entity_id = r2.source_entity_id
                WHERE r1.relation_type = 'located_in'
                  AND r2.relation_type = 'located_in'
                  AND r1.target_entity_id != r2.target_entity_id
                  AND r1.id < r2.id
                LIMIT 10
            """)
            
            for row in cur.fetchall():
                entity_id = str(row[0])
                loc1 = str(row[1])
                loc2 = str(row[2])
                
                suggestions.append(Suggestion(
                    id=f"conflict-{entity_id[:8]}",
                    suggestion_type=SuggestionType.CONFLICT,
                    priority=Priority.HIGH,
                    entity_id=entity_id,
                    title="Location Conflict Detected",
                    description=f"Entity has conflicting locations: {loc1[:8]} vs {loc2[:8]}",
                    confidence=0.95,
                    action="Resolve by keeping most recent or authoritative location",
                    details={"location_1": loc1, "location_2": loc2}
                ))
        
        return suggestions


class StalenessDetector:
    """Detects outdated information that needs verification"""
    
    def __init__(self, stale_days: int = 90):
        self.pg = PostgresClient()
        self.stale_days = stale_days
    
    def detect(self) -> List[Suggestion]:
        """Find stale entity states"""
        suggestions = []
        cutoff = datetime.utcnow() - timedelta(days=self.stale_days)
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT entity_id, updated_at, current_value
                FROM entity_state
                WHERE updated_at < %s
                ORDER BY updated_at ASC
                LIMIT 20
            """, (cutoff,))
            
            for row in cur.fetchall():
                entity_id = str(row['entity_id'] if isinstance(row, dict) else row[0])
                updated = row['updated_at'] if isinstance(row, dict) else row[1]
                days_old = (datetime.utcnow() - updated).days if updated else self.stale_days
                
                # Priority based on age
                if days_old > 180:
                    priority = Priority.HIGH
                elif days_old > 120:
                    priority = Priority.MEDIUM
                else:
                    priority = Priority.LOW
                
                suggestions.append(Suggestion(
                    id=f"stale-{entity_id[:8]}",
                    suggestion_type=SuggestionType.STALENESS,
                    priority=priority,
                    entity_id=entity_id,
                    title="Stale Entity State",
                    description=f"Entity not updated in {days_old} days. Verification recommended.",
                    confidence=0.8,
                    action="Verify current state and update if needed",
                    details={"last_updated": updated.isoformat() if updated else None, "days_old": days_old}
                ))
        
        return suggestions


class MissingLinkDetector:
    """Detects potential missing relationships"""
    
    def __init__(self):
        self.pg = PostgresClient()
        self.graph = GraphService()
    
    def detect(self) -> List[Suggestion]:
        """Find potential missing relationships (A→B, B→C but no A→C for transitive relations)"""
        suggestions = []
        
        with self.pg.get_cursor() as cur:
            # Find friend-of-friend without direct link
            cur.execute("""
                SELECT DISTINCT r1.source_entity_id as a, r2.target_entity_id as c
                FROM relations r1
                JOIN relations r2 ON r1.target_entity_id = r2.source_entity_id
                WHERE r1.relation_type = 'is_friend_of'
                  AND r2.relation_type = 'is_friend_of'
                  AND r1.source_entity_id != r2.target_entity_id
                  AND NOT EXISTS (
                      SELECT 1 FROM relations r3
                      WHERE r3.source_entity_id = r1.source_entity_id
                        AND r3.target_entity_id = r2.target_entity_id
                  )
                LIMIT 10
            """)
            
            for row in cur.fetchall():
                a_id = str(row[0])
                c_id = str(row[1])
                
                suggestions.append(Suggestion(
                    id=f"missing-{a_id[:4]}-{c_id[:4]}",
                    suggestion_type=SuggestionType.MISSING_LINK,
                    priority=Priority.LOW,
                    entity_id=a_id,
                    title="Potential Missing Relationship",
                    description=f"Verify: Does {a_id[:8]} know {c_id[:8]}?",
                    confidence=0.65,
                    action="Verify relationship and add if confirmed",
                    details={"entity_a": a_id, "entity_c": c_id, "via": "friend_of_friend"}
                ))
        
        return suggestions


class ConsolidationDetector:
    """Detects opportunities to consolidate events"""
    
    def __init__(self, min_events: int = 50):
        self.pg = PostgresClient()
        self.min_events = min_events
    
    def detect(self) -> List[Suggestion]:
        """Find entities with many unconsolidated events"""
        suggestions = []
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT object_id, COUNT(*) as event_count
                FROM events
                GROUP BY object_id
                HAVING COUNT(*) > %s
                ORDER BY event_count DESC
                LIMIT 10
            """, (self.min_events,))
            
            for row in cur.fetchall():
                entity_id = str(row['object_id'] if isinstance(row, dict) else row[0])
                count = row['event_count'] if isinstance(row, dict) else row[1]
                
                # Estimate compression ratio
                estimated_reduction = int(count * 0.6)  # ~60% reduction typical
                
                suggestions.append(Suggestion(
                    id=f"consolidate-{entity_id[:8]}",
                    suggestion_type=SuggestionType.CONSOLIDATION,
                    priority=Priority.MEDIUM,
                    entity_id=entity_id,
                    title="Consolidation Opportunity",
                    description=f"Entity has {count} events. Consolidation could save ~{estimated_reduction} events.",
                    confidence=0.85,
                    action=f"Run assimilation on entity (estimated {estimated_reduction} events merged)",
                    details={"event_count": count, "estimated_reduction": estimated_reduction}
                ))
        
        return suggestions


# ============================================================================
# SUGGESTION QUEUE
# ============================================================================

class SuggestionQueue:
    """Priority queue for maintenance suggestions"""
    
    def __init__(self):
        self.pg = PostgresClient()
        self._ensure_table()
    
    def _ensure_table(self):
        """Create suggestions table if not exists"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_suggestions (
                    id VARCHAR(64) PRIMARY KEY,
                    suggestion_type VARCHAR(32),
                    priority VARCHAR(16),
                    entity_id VARCHAR(36),
                    title TEXT,
                    description TEXT,
                    confidence FLOAT,
                    action TEXT,
                    details JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    status VARCHAR(16) DEFAULT 'pending'
                )
            """)
    
    def add(self, suggestion: Suggestion):
        """Add suggestion to queue"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO maintenance_suggestions 
                (id, suggestion_type, priority, entity_id, title, description, confidence, action, details, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = 'pending',
                    created_at = NOW()
            """, (
                suggestion.id,
                suggestion.suggestion_type.value,
                suggestion.priority.value,
                suggestion.entity_id,
                suggestion.title,
                suggestion.description,
                suggestion.confidence,
                suggestion.action,
                json.dumps(suggestion.details),
                suggestion.status
            ))
    
    def get_pending(self, limit: int = 20) -> List[Suggestion]:
        """Get pending suggestions ordered by priority"""
        priority_order = "CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
        
        with self.pg.get_cursor() as cur:
            cur.execute(f"""
                SELECT * FROM maintenance_suggestions
                WHERE status = 'pending'
                ORDER BY {priority_order}, created_at DESC
                LIMIT %s
            """, (limit,))
            
            rows = cur.fetchall()
            
            suggestions = []
            for row in rows:
                if isinstance(row, dict):
                    suggestions.append(Suggestion(
                        id=row['id'],
                        suggestion_type=SuggestionType(row['suggestion_type']),
                        priority=Priority(row['priority']),
                        entity_id=row['entity_id'],
                        title=row['title'],
                        description=row['description'],
                        confidence=row['confidence'],
                        action=row['action'],
                        details=row['details'] or {},
                        created_at=row['created_at'],
                        status=row['status']
                    ))
            
            return suggestions
    
    def update_status(self, suggestion_id: str, status: str):
        """Update suggestion status"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE maintenance_suggestions
                SET status = %s
                WHERE id = %s
            """, (status, suggestion_id))


# ============================================================================
# MAINTENANCE SUGGESTER
# ============================================================================

class MaintenanceSuggester:
    """
    Unified maintenance suggestion system.
    Runs all detectors and manages suggestion queue.
    """
    
    def __init__(self):
        self.detectors = [
            ConflictDetector(),
            StalenessDetector(),
            MissingLinkDetector(),
            ConsolidationDetector(),
        ]
        self.queue = SuggestionQueue()
    
    def scan(self) -> Dict[str, int]:
        """Run all detectors and populate queue"""
        log.info("Starting maintenance scan...")
        
        counts = {}
        total = 0
        
        for detector in self.detectors:
            detector_name = detector.__class__.__name__
            try:
                suggestions = detector.detect()
                for s in suggestions:
                    self.queue.add(s)
                counts[detector_name] = len(suggestions)
                total += len(suggestions)
                log.info(f"  {detector_name}: {len(suggestions)} suggestions")
            except Exception as e:
                log.error(f"  {detector_name} failed: {e}")
                counts[detector_name] = 0
        
        log.info(f"Scan complete: {total} total suggestions")
        return counts
    
    def get_suggestions(self, limit: int = 20) -> List[Suggestion]:
        """Get prioritized suggestions"""
        return self.queue.get_pending(limit)
    
    def accept(self, suggestion_id: str):
        """Mark suggestion as accepted"""
        self.queue.update_status(suggestion_id, "accepted")
        log.info(f"Suggestion {suggestion_id} accepted")
    
    def reject(self, suggestion_id: str):
        """Mark suggestion as rejected"""
        self.queue.update_status(suggestion_id, "rejected")
        log.info(f"Suggestion {suggestion_id} rejected")
    
    def defer(self, suggestion_id: str):
        """Defer suggestion for later"""
        self.queue.update_status(suggestion_id, "deferred")
        log.info(f"Suggestion {suggestion_id} deferred")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def scan_for_issues() -> Dict[str, int]:
    """Quick scan for maintenance issues"""
    suggester = MaintenanceSuggester()
    return suggester.scan()


def get_suggestions(limit: int = 20) -> List[Suggestion]:
    """Get pending suggestions"""
    suggester = MaintenanceSuggester()
    return suggester.get_suggestions(limit)
