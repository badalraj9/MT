import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum, DeltaPatch, DeltaOp
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TruthVectorService:
    @staticmethod
    def calculate_score(vector: TruthVector, freshness_ts: Optional[datetime] = None) -> float:
        # Placeholder weights - moving to settings later
        W1, W2, W3, W4 = 1.0, 1.0, 1.0, 1.0

        import math
        corr_score = math.log(1 + vector.corroboration)

        # Freshness is derived, not stored
        freshness_val = 1.0
        if freshness_ts:
             # Example decay: 1.0 / (days + 1)
             age = (datetime.now(timezone.utc) - freshness_ts).total_seconds() / 86400
             freshness_val = 1.0 / (age + 1.0)

        score = (W1 * vector.confidence) + \
                (W2 * vector.authority) + \
                (W3 * freshness_val) + \
                (W4 * corr_score)
        return score

class StateDerivationService:
    @staticmethod
    def apply_event(current_state: EntityState, event: Event) -> EntityState:
        """
        Derives S(t+1) from S(t) + Event.
        """
        if event.object_id != current_state.entity_id:
            raise ValueError("Event object_id mismatch")

        # Create new value dictionary (copy)
        new_value = current_state.current_value.copy()

        # Apply Delta Patches
        for patch in event.delta:
            path = patch.path
            val = patch.value
            op = patch.op

            # Simplified path handling (flat dict)
            # In real system: json pointer resolution

            if op == DeltaOp.ADD:
                if path in new_value and isinstance(new_value[path], (int, float)) and isinstance(val, (int, float)):
                    new_value[path] += val
                else:
                    new_value[path] = val
            elif op == DeltaOp.REMOVE:
                 if path in new_value and isinstance(new_value[path], (int, float)) and isinstance(val, (int, float)):
                    new_value[path] -= val
                 elif path in new_value:
                    del new_value[path]
            elif op == DeltaOp.REPLACE:
                 new_value[path] = val

        return EntityState(
            entity_id=current_state.entity_id,
            namespace=current_state.namespace,
            current_value=new_value,
            truth_vector=event.truth_vector,
            version=current_state.version + 1,
            last_event_id=event.id,
            updated_at=datetime.now(timezone.utc)
        )

class TMSService:
    def __init__(self):
        pass

    # Method signature updated to reflect lack of defaults
    def create_event_proposal(self,
                     actor: ActorEnum,
                     action: ActionEnum,
                     object_id: uuid.UUID,
                     delta: List[DeltaPatch],
                     namespace: str = "user") -> Event:

        # This function can't create a valid Event anymore because it can't determine ID or Timestamp deterministically without input
        # It's better to rename it to 'construct_event' or accept external params
        raise NotImplementedError("Events must be created at the Gateway or via factory with deterministic ID")
