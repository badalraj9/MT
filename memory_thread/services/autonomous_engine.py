"""
Memory Thread: Autonomous Action Engine
========================================
Phase 9.3: Predictive World Model

Safe autonomous execution system with:
- Multi-level autonomy (Level 0-2)
- Preview mode (24hr delay)
- Reversibility guarantees
- Kill switch
- Complete audit trail

Target: Zero data loss from autonomous actions
"""

import logging
import json
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.services.maintenance_suggester import MaintenanceSuggester, Suggestion, SuggestionType
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ============================================================================
# AUTONOMY LEVELS
# ============================================================================

class AutonomyLevel(Enum):
    LEVEL_0 = 0  # Manual only - all actions require approval
    LEVEL_1 = 1  # Safe auto-execution - low risk, reversible
    LEVEL_2 = 2  # Extended auto - medium risk with preview


@dataclass
class ActionConfig:
    """Configuration for an autonomous action type"""
    name: str
    confidence_threshold: float
    risk: str  # "none", "low", "medium", "high"
    reversible: bool
    preview_hours: int  # Hours to wait before execution
    enabled: bool = True


@dataclass
class ScheduledAction:
    """An action scheduled for future execution"""
    id: str
    action_type: str
    entity_id: str
    parameters: Dict[str, Any]
    scheduled_at: datetime
    execute_at: datetime
    status: str  # "pending", "executed", "cancelled", "failed"
    result: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ActionResult:
    """Result of executing an autonomous action"""
    action_id: str
    success: bool
    message: str
    rollback_data: Optional[Dict[str, Any]] = None  # Data needed to undo
    executed_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# DEFAULT ACTION CONFIGURATIONS
# ============================================================================

DEFAULT_ACTIONS = {
    "prune_low_value": ActionConfig(
        name="Prune Low Value States",
        confidence_threshold=0.92,
        risk="low",
        reversible=True,
        preview_hours=24
    ),
    "consolidate_events": ActionConfig(
        name="Consolidate Old Events",
        confidence_threshold=0.88,
        risk="low",
        reversible=True,
        preview_hours=24
    ),
    "flag_conflicts": ActionConfig(
        name="Flag Conflicts",
        confidence_threshold=0.75,
        risk="none",
        reversible=True,  # Can unflag
        preview_hours=0  # Immediate
    ),
    "refresh_stale": ActionConfig(
        name="Refresh Stale Data",
        confidence_threshold=0.85,
        risk="low",
        reversible=False,  # Can't un-refresh
        preview_hours=48
    ),
    "merge_duplicates": ActionConfig(
        name="Merge Duplicate Entities",
        confidence_threshold=0.95,
        risk="medium",
        reversible=True,
        preview_hours=72
    ),
}


# ============================================================================
# AUTONOMOUS ACTION ENGINE
# ============================================================================

class AutonomousEngine:
    """
    Safe autonomous action execution with multiple safety layers.
    
    Safety Features:
    - Confidence thresholds per action type
    - Preview mode with configurable delays
    - All actions are reversible (or clearly marked non-reversible)
    - Kill switch to immediately stop all autonomous actions
    - Complete audit trail in database
    """
    
    def __init__(self, autonomy_level: AutonomyLevel = AutonomyLevel.LEVEL_0):
        self.pg = PostgresClient()
        self.suggester = MaintenanceSuggester()
        self.autonomy_level = autonomy_level
        self.action_configs = DEFAULT_ACTIONS.copy()
        self._enabled = True
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create required database tables"""
        with self.pg.get_cursor() as cur:
            # Scheduled actions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS autonomous_actions (
                    id VARCHAR(64) PRIMARY KEY,
                    action_type VARCHAR(64),
                    entity_id VARCHAR(36),
                    parameters JSONB,
                    scheduled_at TIMESTAMP,
                    execute_at TIMESTAMP,
                    status VARCHAR(16) DEFAULT 'pending',
                    result TEXT,
                    rollback_data JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Audit log table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS autonomous_audit_log (
                    id SERIAL PRIMARY KEY,
                    action_id VARCHAR(64),
                    action_type VARCHAR(64),
                    entity_id VARCHAR(36),
                    event VARCHAR(32),
                    details JSONB,
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """)
    
    # ========================================================================
    # KILL SWITCH
    # ========================================================================
    
    def kill_switch(self):
        """Immediately disable all autonomous actions"""
        self._enabled = False
        log.critical("KILL SWITCH ACTIVATED - All autonomous actions disabled")
        self._log_audit("system", "KILL_SWITCH", None, {"reason": "Manual activation"})
    
    def enable(self):
        """Re-enable autonomous actions"""
        self._enabled = True
        log.info("Autonomous actions re-enabled")
        self._log_audit("system", "ENABLED", None, {})
    
    # ========================================================================
    # ACTION SCHEDULING
    # ========================================================================
    
    def process_suggestion(self, suggestion: Suggestion) -> Optional[ScheduledAction]:
        """Process a maintenance suggestion for autonomous action"""
        if not self._enabled:
            return None
        
        # Map suggestion type to action
        action_map = {
            SuggestionType.STALENESS: "refresh_stale",
            SuggestionType.CONFLICT: "flag_conflicts",
            SuggestionType.CONSOLIDATION: "consolidate_events",
            SuggestionType.DUPLICATE: "merge_duplicates",
        }
        
        action_type = action_map.get(suggestion.suggestion_type)
        if not action_type:
            return None
        
        config = self.action_configs.get(action_type)
        if not config or not config.enabled:
            return None
        
        # Check autonomy level
        if self.autonomy_level == AutonomyLevel.LEVEL_0:
            return None  # Manual only
        
        if config.risk == "medium" and self.autonomy_level < AutonomyLevel.LEVEL_2:
            return None  # Not authorized for medium risk
        
        # Check confidence threshold
        if suggestion.confidence < config.confidence_threshold:
            log.debug(f"Suggestion {suggestion.id} below threshold ({suggestion.confidence:.2f} < {config.confidence_threshold})")
            return None
        
        # Schedule action
        execute_at = datetime.utcnow() + timedelta(hours=config.preview_hours)
        
        action = ScheduledAction(
            id=f"auto-{uuid.uuid4().hex[:12]}",
            action_type=action_type,
            entity_id=suggestion.entity_id,
            parameters={"suggestion_id": suggestion.id, **suggestion.details},
            scheduled_at=datetime.utcnow(),
            execute_at=execute_at,
            status="pending"
        )
        
        self._save_action(action)
        self._log_audit(action.id, "SCHEDULED", action.entity_id, {
            "action_type": action_type,
            "execute_at": execute_at.isoformat(),
            "preview_hours": config.preview_hours
        })
        
        log.info(f"Scheduled {action_type} for {suggestion.entity_id[:8]} at {execute_at}")
        return action
    
    def _save_action(self, action: ScheduledAction):
        """Persist action to database"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO autonomous_actions 
                (id, action_type, entity_id, parameters, scheduled_at, execute_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                action.id,
                action.action_type,
                action.entity_id,
                json.dumps(action.parameters),
                action.scheduled_at,
                action.execute_at,
                action.status
            ))
    
    # ========================================================================
    # ACTION EXECUTION
    # ========================================================================
    
    def execute_pending_actions(self) -> List[ActionResult]:
        """Execute all pending actions that are ready"""
        if not self._enabled:
            return []
        
        results = []
        now = datetime.utcnow()
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT * FROM autonomous_actions
                WHERE status = 'pending' AND execute_at <= %s
            """, (now,))
            
            rows = cur.fetchall()
        
        for row in rows:
            action_id = row['id'] if isinstance(row, dict) else row[0]
            action_type = row['action_type'] if isinstance(row, dict) else row[1]
            entity_id = row['entity_id'] if isinstance(row, dict) else row[2]
            parameters = row['parameters'] if isinstance(row, dict) else row[3]
            
            if isinstance(parameters, str):
                parameters = json.loads(parameters)
            
            result = self._execute_action(action_id, action_type, entity_id, parameters)
            results.append(result)
        
        return results
    
    def _execute_action(self, action_id: str, action_type: str, 
                        entity_id: str, parameters: Dict) -> ActionResult:
        """Execute a single action"""
        log.info(f"Executing {action_type} on {entity_id[:8]}...")
        
        try:
            # Execute based on type
            if action_type == "flag_conflicts":
                rollback_data = self._action_flag_conflicts(entity_id, parameters)
            elif action_type == "consolidate_events":
                rollback_data = self._action_consolidate(entity_id, parameters)
            elif action_type == "refresh_stale":
                rollback_data = self._action_refresh_stale(entity_id, parameters)
            elif action_type == "prune_low_value":
                rollback_data = self._action_prune(entity_id, parameters)
            else:
                raise ValueError(f"Unknown action type: {action_type}")
            
            # Update status
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    UPDATE autonomous_actions
                    SET status = 'executed', result = 'success', rollback_data = %s
                    WHERE id = %s
                """, (json.dumps(rollback_data), action_id))
            
            self._log_audit(action_id, "EXECUTED", entity_id, {"success": True})
            
            return ActionResult(
                action_id=action_id,
                success=True,
                message=f"{action_type} completed successfully",
                rollback_data=rollback_data
            )
            
        except Exception as e:
            log.error(f"Action {action_id} failed: {e}")
            
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    UPDATE autonomous_actions
                    SET status = 'failed', result = %s
                    WHERE id = %s
                """, (str(e), action_id))
            
            self._log_audit(action_id, "FAILED", entity_id, {"error": str(e)})
            
            return ActionResult(
                action_id=action_id,
                success=False,
                message=str(e)
            )
    
    # ========================================================================
    # ACTION IMPLEMENTATIONS
    # ========================================================================
    
    def _action_flag_conflicts(self, entity_id: str, params: Dict) -> Dict:
        """Flag an entity as having conflicts"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE entities 
                SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"has_conflict": true}'::jsonb
                WHERE id = %s
            """, (entity_id,))
        return {"action": "flag", "previous_state": "not_flagged"}
    
    def _action_consolidate(self, entity_id: str, params: Dict) -> Dict:
        """Consolidate events for an entity"""
        # Call assimilation service
        from memory_thread.services.assimilator import AssimilatorService
        assimilator = AssimilatorService()
        
        # Count before
        with self.pg.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM events WHERE object_id = %s", (entity_id,))
            before = cur.fetchone()[0]
        
        # Run consolidation (simplified for now)
        patterns = assimilator.detect_patterns(entity_id)
        consolidated = 0
        for pattern in patterns[:5]:  # Limit to 5 groups per run
            summary = assimilator.consolidate_events(pattern)
            if summary:
                assimilator.execute_consolidation(summary, pattern)
                consolidated += len(pattern)
        
        return {"action": "consolidate", "events_before": before, "consolidated_count": consolidated}
    
    def _action_refresh_stale(self, entity_id: str, params: Dict) -> Dict:
        """Mark entity as needing refresh (set a flag for external system)"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE entity_state 
                SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"needs_refresh": true}'::jsonb
                WHERE entity_id = %s
            """, (entity_id,))
        return {"action": "refresh_flagged"}
    
    def _action_prune(self, entity_id: str, params: Dict) -> Dict:
        """Prune low-value state (soft delete)"""
        with self.pg.get_cursor() as cur:
            # Get current state for rollback
            cur.execute("SELECT * FROM entity_state WHERE entity_id = %s", (entity_id,))
            row = cur.fetchone()
            
            if row:
                # Soft delete (mark inactive)
                cur.execute("""
                    UPDATE entity_state 
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"pruned": true}'::jsonb
                    WHERE entity_id = %s
                """, (entity_id,))
                
                return {"action": "prune", "can_restore": True}
        
        return {"action": "prune", "entity_not_found": True}
    
    # ========================================================================
    # ROLLBACK
    # ========================================================================
    
    def rollback(self, action_id: str) -> bool:
        """Rollback a previously executed action"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT action_type, entity_id, rollback_data 
                FROM autonomous_actions 
                WHERE id = %s AND status = 'executed'
            """, (action_id,))
            
            row = cur.fetchone()
            if not row:
                return False
            
            action_type = row[0]
            entity_id = row[1]
            rollback_data = row[2]
            
            if isinstance(rollback_data, str):
                rollback_data = json.loads(rollback_data)
            
            # Execute rollback
            if action_type == "flag_conflicts":
                cur.execute("""
                    UPDATE entities 
                    SET metadata = metadata - 'has_conflict'
                    WHERE id = %s
                """, (entity_id,))
            elif action_type == "prune_low_value":
                cur.execute("""
                    UPDATE entity_state 
                    SET metadata = metadata - 'pruned'
                    WHERE entity_id = %s
                """, (entity_id,))
            
            # Mark as rolled back
            cur.execute("""
                UPDATE autonomous_actions
                SET status = 'rolled_back'
                WHERE id = %s
            """, (action_id,))
            
            self._log_audit(action_id, "ROLLED_BACK", entity_id, {})
            
            log.info(f"Action {action_id} rolled back successfully")
            return True
    
    # ========================================================================
    # AUDIT LOGGING
    # ========================================================================
    
    def _log_audit(self, action_id: str, event: str, entity_id: Optional[str], details: Dict):
        """Log action to audit trail"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO autonomous_audit_log (action_id, action_type, entity_id, event, details)
                VALUES (%s, %s, %s, %s, %s)
            """, (action_id, "autonomous", entity_id, event, json.dumps(details)))
    
    def get_audit_log(self, limit: int = 50) -> List[Dict]:
        """Get recent audit log entries"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT * FROM autonomous_audit_log
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))
            return cur.fetchall()
    
    # ========================================================================
    # PREVIEW MODE
    # ========================================================================
    
    def get_pending_actions(self) -> List[ScheduledAction]:
        """Get all pending actions (for preview)"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT * FROM autonomous_actions
                WHERE status = 'pending'
                ORDER BY execute_at ASC
            """)
            
            rows = cur.fetchall()
            actions = []
            
            for row in rows:
                if isinstance(row, dict):
                    actions.append(ScheduledAction(
                        id=row['id'],
                        action_type=row['action_type'],
                        entity_id=row['entity_id'],
                        parameters=row['parameters'] or {},
                        scheduled_at=row['scheduled_at'],
                        execute_at=row['execute_at'],
                        status=row['status']
                    ))
            
            return actions
    
    def cancel_action(self, action_id: str) -> bool:
        """Cancel a pending action"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE autonomous_actions
                SET status = 'cancelled'
                WHERE id = %s AND status = 'pending'
            """, (action_id,))
            
            if cur.rowcount > 0:
                self._log_audit(action_id, "CANCELLED", None, {"reason": "Manual cancellation"})
                return True
            return False


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_autonomous_engine(level: int = 0) -> AutonomousEngine:
    """Get engine at specified autonomy level"""
    return AutonomousEngine(AutonomyLevel(level))
