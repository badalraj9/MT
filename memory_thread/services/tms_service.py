import uuid
import datetime
from typing import Dict, Any, List
from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TruthVectorService:
    @staticmethod
    def calculate_score(vector: TruthVector) -> float:
        # Placeholder weights - moving to settings later
        W1, W2, W3, W4 = 1.0, 1.0, 1.0, 1.0

        # Simple heuristic for now
        # log(1 + corroboration)
        import math
        corr_score = math.log(1 + vector.corroboration)

        score = (W1 * vector.confidence) + \
                (W2 * vector.authority) + \
                (W3 * vector.freshness) + \
                (W4 * corr_score)
        return score

    @staticmethod
    def decay_freshness(vector: TruthVector, event_time: datetime.datetime) -> float:
        # Placeholder decay logic
        # For now, just return current freshness
        return vector.freshness

class StateDerivationService:
    @staticmethod
    def apply_event(current_state: EntityState, event: Event, updated_at: datetime.datetime) -> EntityState:
        """
        Derives S(t+1) from S(t) + Event.
        """
        if event.object_id != current_state.entity_id:
            raise ValueError("Event object_id mismatch")
        
        # Causal Linkage Check
        # If not genesis, last_event_id must match? 
        # For now, we just enforce the logic.

        # Create new value dictionary (copy)
        new_value = current_state.current_value.copy()

        # Apply Delta (Pure Logic)
        for k, v in event.delta.items():
            if isinstance(v, (int, float)) and k in new_value and isinstance(new_value[k], (int, float)):
                if event.action in [ActionEnum.ADD, ActionEnum.PLANT]:
                     new_value[k] += v
                elif event.action == ActionEnum.REMOVE:
                     new_value[k] -= v
                elif event.action == ActionEnum.UPDATE:
                     new_value[k] = v
            else:
                new_value[k] = v

        return EntityState(
            entity_id=current_state.entity_id,
            namespace=current_state.namespace,
            current_value=new_value,
            truth_vector=event.truth_vector,
            version=current_state.version + 1,
            last_event_id=event.id,
            updated_at=updated_at # Explicit injection
        )

class TMSService:
    def __init__(self):
        pass

    def create_event(self,
                     actor: ActorEnum,
                     action: ActionEnum,
                     object_id: uuid.UUID,
                     delta: Dict[str, Any],
                     namespace: str,
                     event_id: uuid.UUID,
                     timestamp: datetime.datetime) -> Event:

        if event_id is None:
             raise ValueError("event_id must be provided for deterministic MT mode")
        
        if timestamp is None:
             raise ValueError("timestamp must be provided for deterministic MT mode")

        # Default Truth Vector (can be enhanced later, but must be frozen/pure)
        tv = TruthVector(
            confidence=1.0,
            authority=1.0,
            freshness=1.0,
            corroboration=0.0
        )

        event = Event(
            id=event_id,
            timestamp=timestamp, # Explicit injection
            actor=actor,
            action=action,
            object_id=object_id,
            delta=delta,
            namespace=namespace,
            truth_vector=tv
        )

        # In a real app, we would write to DB here
        log.info(f"Created Event: {event.id} ({action} {object_id})")
        return event

    def get_entity_state(self, entity_id: uuid.UUID) -> EntityState:
        """
        Fetch current entity state from database.
        Returns None if entity not found.
        """
        from memory_thread.db.postgres_client import PostgresClient
        
        pg = PostgresClient()
        
        with pg.get_cursor() as cur:
            cur.execute("""
                SELECT entity_id, namespace, current_value, truth_vector, 
                       version, last_event_id, updated_at
                FROM entity_state
                WHERE entity_id = %s
            """, (str(entity_id),))
            
            row = cur.fetchone()
            
            if not row:
                return None
            
            # Handle both dict and tuple access
            if isinstance(row, dict):
                cv = row['current_value']
                tv = row['truth_vector']
                if isinstance(cv, str):
                    import json
                    cv = json.loads(cv)
                if isinstance(tv, str):
                    import json
                    tv = json.loads(tv)
                
                return EntityState(
                    entity_id=uuid.UUID(str(row['entity_id'])),
                    namespace=row['namespace'],
                    current_value=cv,
                    truth_vector=TruthVector(**tv) if tv else TruthVector(),
                    version=row['version'] or 1,
                    last_event_id=uuid.UUID(str(row['last_event_id'])) if row['last_event_id'] else None,
                    updated_at=row['updated_at']
                )
            
            return None
    
    def get_current_state(self, entity_id: uuid.UUID) -> EntityState:
        """Alias for get_entity_state for backward compatibility"""
        return self.get_entity_state(entity_id)

