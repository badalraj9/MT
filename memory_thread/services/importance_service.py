"""
Memory Thread: Importance Service
==================================
Calculates importance scores for memories and entities.

Factors considered:
- Recency (newer = more important)
- Access frequency (frequently accessed = more important)
- Entity references (more connections = more important)
- Explicit user signals
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from memory_thread.db.postgres_client import PostgresClient

log = logging.getLogger(__name__)

# Default importance weights
WEIGHTS = {
    'base': 0.5,
    'recency': 0.2,
    'access_frequency': 0.15,
    'entity_connections': 0.1,
    'user_signal': 0.05
}


def calculate_importance(mem: Dict[str, Any]) -> float:
    """
    Calculate importance score for a memory/entity.
    
    Args:
        mem: Dictionary with memory data (id, created_at, access_count, etc.)
        
    Returns:
        Float between 0.0 and 1.0
    """
    try:
        # Base importance (from field or default)
        base = mem.get('importance', WEIGHTS['base'])
        
        # Recency factor (decay over days)
        recency = 0.5
        created_at = mem.get('created_at')
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except:
                    created_at = None
            
            if created_at:
                days_old = (datetime.utcnow() - created_at.replace(tzinfo=None)).days
                recency = math.exp(-0.05 * days_old)  # Decay factor
        
        # Access frequency (normalized)
        access_count = mem.get('access_count', 0)
        access_factor = min(1.0, math.log(1 + access_count) / 5)
        
        # Entity connections (if available)
        connections = mem.get('connection_count', 0)
        connection_factor = min(1.0, connections / 10)
        
        # User signal (explicit boost/demote)
        user_signal = mem.get('user_importance', 0.5)
        
        # Weighted combination
        importance = (
            WEIGHTS['base'] * base +
            WEIGHTS['recency'] * recency +
            WEIGHTS['access_frequency'] * access_factor +
            WEIGHTS['entity_connections'] * connection_factor +
            WEIGHTS['user_signal'] * user_signal
        )
        
        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, importance))
        
    except Exception as e:
        log.warning(f"Importance calculation failed for {mem.get('id')}: {e}")
        return WEIGHTS['base']


def update_importance(entity_id: str, delta: float = 0.0) -> Optional[float]:
    """
    Update importance score in database.
    
    Args:
        entity_id: Entity UUID
        delta: Amount to adjust importance by
        
    Returns:
        New importance score or None on failure
    """
    pg = PostgresClient()
    
    try:
        with pg.get_cursor() as cur:
            cur.execute("""
                UPDATE entity_state 
                SET importance = LEAST(1.0, GREATEST(0.0, COALESCE(importance, 0.5) + %s))
                WHERE entity_id = %s
                RETURNING importance
            """, (delta, entity_id))
            
            row = cur.fetchone()
            if row:
                return row['importance'] if isinstance(row, dict) else row[0]
            return None
            
    except Exception as e:
        log.error(f"Failed to update importance for {entity_id}: {e}")
        return None


def boost_importance(entity_id: str, amount: float = 0.1) -> Optional[float]:
    """Increase importance score"""
    return update_importance(entity_id, abs(amount))


def decay_importance(entity_id: str, amount: float = 0.05) -> Optional[float]:
    """Decrease importance score"""
    return update_importance(entity_id, -abs(amount))

