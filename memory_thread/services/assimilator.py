import uuid
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from uuid import NAMESPACE_DNS, uuid5

from memory_thread.models.events import Event, ActionEnum, ActorEnum, DeltaPatch, DeltaOp, TruthVector, Provenance
from memory_thread.db.postgres_client import EventStore
from memory_thread.utils.logger import get_logger
from memory_thread.utils.ids import canonical_json_for_event, deterministic_event_id_from_payload, compute_dedup_hash

log = get_logger(__name__)

class AssimilatorService:
    def __init__(self):
        self.store = EventStore()

    def detect_patterns(self, entity_id: uuid.UUID, window_days: int = 30) -> List[List[Event]]:
        """
        Finds groups of events that are candidates for consolidation.
        """
        # EventStore.list_events_by_object could be used if it supports filtering by time
        # Or we add a method to EventStore
        # For now, using direct query via store cursor for custom filter

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=window_days)

        with self.store.get_cursor() as cur:
            cur.execute("""
                SELECT *
                FROM events
                WHERE object_id = %s
                  AND timestamp > %s
                  AND consolidated_into IS NULL
                ORDER BY gateway_seq ASC
            """, (str(entity_id), cutoff_date))
            rows = cur.fetchall()

        events = [self.store._row_to_event(r) for r in rows]

        # Grouping logic
        groups = []
        if not events:
            return groups

        current_group = [events[0]]

        for i in range(1, len(events)):
            prev = current_group[-1]
            curr = events[i]

            prev_structure = set((d.path, d.op) for d in prev.delta)
            curr_structure = set((d.path, d.op) for d in curr.delta)

            is_same_structure = (
                prev.actor == curr.actor and
                prev.action == curr.action and
                prev_structure == curr_structure
            )

            if is_same_structure:
                current_group.append(curr)
            else:
                if len(current_group) > 1:
                    groups.append(current_group)
                current_group = [curr]

        if len(current_group) > 1:
            groups.append(current_group)

        return groups

    def consolidate_events(self, events: List[Event]) -> Optional[Event]:
        """
        Merges a list of events into a single summary event.
        """
        if not events:
            return None

        first = events[0]

        # 1. Aggregate Delta
        path_deltas = defaultdict(list)
        for e in events:
            for d in e.delta:
                path_deltas[d.path].append(d)

        consolidated_deltas = []

        for path, deltas in path_deltas.items():
            first_delta = deltas[0]
            if first_delta.op == DeltaOp.ADD:
                try:
                    total = sum(d.value for d in deltas)
                    consolidated_deltas.append(DeltaPatch(op=DeltaOp.ADD, path=path, value=total))
                except TypeError:
                    consolidated_deltas.append(deltas[-1])
            elif first_delta.op == DeltaOp.REMOVE:
                 try:
                    total = sum(d.value for d in deltas)
                    consolidated_deltas.append(DeltaPatch(op=DeltaOp.REMOVE, path=path, value=total))
                 except TypeError:
                    consolidated_deltas.append(deltas[-1])
            else:
                consolidated_deltas.append(deltas[-1])

        # 2. Allocate ID & Sequence (Need System Access)
        # Summary events are SYSTEM events. They should go through Gateway ideally.
        # But we are in a background service.
        # We must follow the rules: Deterministic ID, Sequence from DB.

        gateway_ts = datetime.now(timezone.utc)

        # Payload for ID
        # Summary ID logic: usually derived from content or source IDs
        # Here we use content-based ID logic (canonical json of summary)
        # But wait, to be deterministic we need inputs.

        raw_summary = {
            "namespace": first.namespace,
            "actor": "SYSTEM",
            "action": first.action,
            "object_id": str(first.object_id),
            "delta": [d.dict() for d in consolidated_deltas],
            "truth_vector": first.truth_vector.dict(),
            "timestamp": gateway_ts
        }

        canon = canonical_json_for_event(raw_summary)
        event_id = deterministic_event_id_from_payload(raw_summary)
        d_hash = compute_dedup_hash(canon)

        # Fetch Sequence
        seq_values = self.store.fetch_next_gateway_seq(1)
        seq = seq_values[0]

        # Provenance
        prov = Provenance(
            producer_id="assimilator_service",
            gateway_timestamp=gateway_ts,
            gateway_seq=seq,
            source_system="internal_maintenance"
        )

        summary_event = Event(
            id=event_id,
            namespace=first.namespace,
            timestamp=gateway_ts,
            actor=ActorEnum.SYSTEM,
            action=first.action,
            object_id=first.object_id,
            delta=consolidated_deltas,
            antecedents=[e.id for e in events], # Link sources
            truth_vector=first.truth_vector,
            provenance=prov,
            gateway_seq=seq,
            dedup_hash=d_hash
        )

        return summary_event

    def execute_consolidation(self, summary_event: Event, source_events: List[Event]):
        """
        Writes the summary event and marks source events as consolidated.
        Atomic transaction.
        """
        # Serialize fields using EventStore logic helper or manually
        delta_json = json.dumps([d.dict() for d in summary_event.delta])
        truth_json = summary_event.truth_vector.json()
        antecedents_json = json.dumps([str(u) for u in summary_event.antecedents])
        provenance_json = summary_event.provenance.json()

        with self.store.get_cursor() as cur:
            # 1. Insert Summary Event
            cur.execute("""
                INSERT INTO events (
                    id, namespace, timestamp, actor, action, object_id,
                    delta, antecedents, truth_vector, provenance,
                    gateway_seq, dedup_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (namespace, object_id, dedup_hash) DO NOTHING
            """, (
                str(summary_event.id), summary_event.namespace, summary_event.timestamp,
                summary_event.actor.value, summary_event.action.value, str(summary_event.object_id),
                delta_json, antecedents_json, truth_json, provenance_json,
                summary_event.gateway_seq, summary_event.dedup_hash
            ))

            # 2. Update Source Events
            source_ids = [str(e.id) for e in source_events]
            cur.execute("""
                UPDATE events
                SET consolidated_into = %s
                WHERE id = ANY(%s)
            """, (str(summary_event.id), source_ids))

        log.info(f"Consolidated {len(source_events)} events into {summary_event.id}")
