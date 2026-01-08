"""
Memory Thread: Decay Service
=============================
Manages temporal decay of memory importance.

Memory types decay at different rates:
- identity: Very slow (core traits persist)
- preference: Slow (tastes change gradually)
- event: Medium (events fade over time)
- episodic: Fast (specific details forgotten)
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from memory_thread.db.postgres_client import PostgresClient

log = logging.getLogger(__name__)

# Decay rates per day (higher = faster decay)
DECAY_RATES = {
    'identity': 0.0005,     # ~50% after 4 years
    'preference': 0.005,    # ~50% after 139 days
    'event': 0.02,          # ~50% after 35 days
    'episodic': 0.05,       # ~50% after 14 days
    'default': 0.02
}


def apply_decay(importance: float, memory_type: str, days: float) -> float:
    """
    Apply exponential decay to importance score.
    
    Args:
        importance: Current importance (0.0 to 1.0)
        memory_type: Type of memory (identity, preference, event, episodic)
        days: Number of days since last access/update
        
    Returns:
        Decayed importance (minimum 0.01 to prevent complete loss)
    """
    rate = DECAY_RATES.get(memory_type, DECAY_RATES['default'])
    decayed = importance * math.exp(-rate * days)
    return max(0.01, min(1.0, decayed))


def calculate_decay_factor(memory_type: str, days: float) -> float:
    """Calculate the decay factor (multiplier) for a given period"""
    rate = DECAY_RATES.get(memory_type, DECAY_RATES['default'])
    return math.exp(-rate * days)


def run_batch_decay(batch_size: int = 1000) -> Dict[str, int]:
    """
    Apply decay to all stale entity states in database.
    
    Returns:
        Statistics about the decay operation
    """
    pg = PostgresClient()
    stats = {'processed': 0, 'updated': 0, 'errors': 0}
    
    try:
        with pg.get_cursor() as cur:
            # Find stale entities (not updated in last 24 hours)
            cur.execute("""
                SELECT es.entity_id, es.importance, es.updated_at, e.entity_type
                FROM entity_state es
                LEFT JOIN entities e ON es.entity_id = e.id
                WHERE es.updated_at < NOW() - INTERVAL '1 day'
                LIMIT %s
            """, (batch_size,))
            
            rows = cur.fetchall()
            now = datetime.utcnow()
            
            for row in rows:
                try:
                    entity_id = row['entity_id'] if isinstance(row, dict) else row[0]
                    importance = row['importance'] if isinstance(row, dict) else row[1]
                    updated_at = row['updated_at'] if isinstance(row, dict) else row[2]
                    entity_type = row['entity_type'] if isinstance(row, dict) else row[3]
                    
                    if importance is None:
                        importance = 0.5
                    
                    if updated_at:
                        days_old = (now - updated_at).days
                        memory_type = _entity_type_to_memory_type(entity_type)
                        new_importance = apply_decay(importance, memory_type, days_old)
                        
                        # Update if changed significantly
                        if abs(new_importance - importance) > 0.001:
                            cur.execute("""
                                UPDATE entity_state 
                                SET importance = %s
                                WHERE entity_id = %s
                            """, (new_importance, str(entity_id)))
                            stats['updated'] += 1
                    
                    stats['processed'] += 1
                    
                except Exception as e:
                    log.warning(f"Decay error for entity: {e}")
                    stats['errors'] += 1
        
        log.info(f"Batch decay complete: {stats}")
        return stats
        
    except Exception as e:
        log.error(f"Batch decay failed: {e}")
        return stats


def _entity_type_to_memory_type(entity_type: Optional[str]) -> str:
    """Map entity type to memory type for decay calculation"""
    mapping = {
        'person': 'identity',
        'organization': 'identity',
        'preference': 'preference',
        'event': 'event',
        'memory': 'episodic'
    }
    return mapping.get(entity_type or '', 'default')


def get_half_life(memory_type: str) -> float:
    """Get half-life in days for a memory type"""
    rate = DECAY_RATES.get(memory_type, DECAY_RATES['default'])
    if rate == 0:
        return float('inf')
    return math.log(2) / rate

