import uuid
from typing import Dict, Any, List
from datetime import datetime, timezone

from memory_thread.models.events import (
    Event, EntityState, ActionEnum, DeltaPatch, DeltaOp, TruthVector, Provenance
)
from memory_thread.services.tms_service import StateDerivationService
from memory_thread.utils.logger import get_logger
from memory_thread.config.settings import settings

log = get_logger(__name__)


class TransactionManager:
    """
    Deterministic, replay-safe multi-entity transaction processor.
    Converts a root event (e.g., transfer) into a set of deterministic
    child events with proper provenance, delta patches, and gateway_seq.
    """

    def __init__(self):
        pass

    def _make_child_event(
        self,
        root: Event,
        object_id: uuid.UUID,
        gateway_seq: int,
        deltas: List[DeltaPatch]
    ) -> Event:
        """
        Create a deterministic child event derived from the root.
        """

        return Event(
            id=uuid.uuid5(settings.EVENT_NAMESPACE_UUID, f"{root.id}-{object_id}-{gateway_seq}"),
            namespace=root.namespace,
            object_id=object_id,
            timestamp=root.timestamp,  # deterministic
            actor=root.actor,
            action=root.action,
            delta=deltas,
            truth_vector=root.truth_vector,
            antecedents=[root.id],
            provenance=Provenance(
                producer_id=root.provenance.producer_id, # Inherit producer context or "transaction_manager"?
                # Actually, derived events should likely preserve producer context or indicate TM logic.
                # But strict model requires producer_id. Let's use root's producer for lineage continuity
                # OR override with "transaction_manager" if that's the semantic.
                # Given provenance.derived_from="transaction", let's keep root producer for auditing.
                gateway_timestamp=root.provenance.gateway_timestamp,
                gateway_seq=gateway_seq,
                source_system="transaction_manager",
                root_event=root.id,
                derived_from="transaction"
            ),
            gateway_seq=gateway_seq
        )

    def process_transaction(
        self,
        root_event: Event,
        context_states: Dict[uuid.UUID, EntityState]
    ) -> Dict[uuid.UUID, EntityState]:

        updated_states = {}
        # Base sequence for derived events starts after root
        # Note: These derived events are NOT persisted to the global log in current Phase 6/7 logic,
        # so reusing the seq space locally for derivation is acceptable as per instructions.
        gateway_seq_base = getattr(root_event, "gateway_seq", 0) + 1

        # Parse transfer info from delta patches
        transfer_to = None
        qty = None
        for patch in root_event.delta:
            if patch.path == "transfer_to":
                # Assuming value is UUID string or UUID
                try:
                    transfer_to = uuid.UUID(str(patch.value))
                except ValueError:
                    pass
            if patch.path == "qty":
                qty = patch.value

        # If not a transfer root event → direct apply
        # Logic: Only ActionEnum.UPDATE + transfer_to + qty triggers split transaction
        if not (root_event.action == ActionEnum.UPDATE and transfer_to and qty is not None):
            if root_event.object_id in context_states:
                updated_states[root_event.object_id] = StateDerivationService.apply_event(
                    context_states[root_event.object_id],
                    root_event
                )
            return updated_states

        source_id = root_event.object_id
        target_id = transfer_to

        # ----------------------------
        # 1. SOURCE ENTITY (DEBIT)
        # ----------------------------
        if source_id in context_states:
            debit_event = self._make_child_event(
                root_event,
                object_id=source_id,
                gateway_seq=gateway_seq_base,
                deltas=[DeltaPatch(path="inventory", op=DeltaOp.REMOVE, value=qty)]
            )
            updated_states[source_id] = StateDerivationService.apply_event(
                context_states[source_id],
                debit_event
            )

        # ----------------------------
        # 2. TARGET ENTITY (CREDIT)
        # ----------------------------
        if target_id in context_states:
            credit_event = self._make_child_event(
                root_event,
                object_id=target_id,
                gateway_seq=gateway_seq_base + 1,
                deltas=[DeltaPatch(path="inventory", op=DeltaOp.ADD, value=qty)]
            )
            updated_states[target_id] = StateDerivationService.apply_event(
                context_states[target_id],
                credit_event
            )

        return updated_states
