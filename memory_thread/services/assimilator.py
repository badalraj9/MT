import uuid
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from uuid import NAMESPACE_DNS, uuid5

from memory_thread.models.events import Event, ActionEnum, ActorEnum, DeltaPatch, DeltaOp, TruthVector, Provenance
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class AssimilatorService:
    def __init__(self):
        self.pg = PostgresClient()

    def detect_patterns(self, entity_id: uuid.UUID, window_days: int = 30) -> List[List[Event]]:
        """
        Finds groups of events that are candidates for consolidation.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Note: Event model has changed. Fetch logic needs update to match DB schema and Model
        # DB schema probably still matches model, but we need to rehydrate correctly.
        # This service connects to DB directly, so it needs to handle the row->model conversion manually or via helper.

        # NOTE: self.pg.get_cursor() needs to be updated if PostgresClient changed?
        # PostgresClient now has `get_cursor` context manager.

        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance
                FROM events
                WHERE object_id = %s
                  AND timestamp > %s
                  AND consolidated_into IS NULL
                ORDER BY timestamp ASC
            """, (str(entity_id), cutoff_date))

            rows = cur.fetchall()

        events = []
        for row in rows:
            # Rehydrate logic (duplicated from EventStore temporarily or could use EventStore)
            # Row index access is unsafe with RealDictCursor?
            # User provided code uses indices: row[0], row[1]...
            # But PostgresClient uses RealDictCursor by default.
            # Assuming RealDictCursor:

            delta_raw = row['delta'] if isinstance(row['delta'], list) else json.loads(row['delta'])
            deltas = [DeltaPatch(**d) for d in delta_raw]

            antecedents_raw = row['antecedents'] if isinstance(row['antecedents'], list) else json.loads(row['antecedents'])
            antecedents = [uuid.UUID(u) for u in antecedents_raw]

            tv_raw = row['truth_vector'] if isinstance(row['truth_vector'], dict) else json.loads(row['truth_vector'])

            prov = None
            if row['provenance']:
                p_raw = row['provenance'] if isinstance(row['provenance'], dict) else json.loads(row['provenance'])
                prov = Provenance(**p_raw)

            events.append(Event(
                id=uuid.UUID(row['id']),
                namespace=row['namespace'],
                timestamp=row['timestamp'],
                actor=ActorEnum(row['actor']),
                action=ActionEnum(row['action']),
                object_id=uuid.UUID(row['object_id']),
                delta=deltas,
                antecedents=antecedents,
                truth_vector=TruthVector(**tv_raw),
                provenance=prov
            ))

        # Grouping logic
        groups = []
        if not events:
            return groups

        current_group = [events[0]]

        for i in range(1, len(events)):
            prev = current_group[-1]
            curr = events[i]

            # Compare Deltas Structurally
            # Set of (path, op) tuples
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
        # We need to look at specific paths.
        # Group deltas by path.
        path_deltas = defaultdict(list)
        for e in events:
            for d in e.delta:
                path_deltas[d.path].append(d)

        consolidated_deltas = []

        for path, deltas in path_deltas.items():
            first_delta = deltas[0]
            # Heuristic aggregation based on Op
            # If ADD + Number -> Sum
            # If REPLACE -> Last

            if first_delta.op == DeltaOp.ADD:
                try:
                    total = sum(d.value for d in deltas)
                    consolidated_deltas.append(DeltaPatch(op=DeltaOp.ADD, path=path, value=total))
                except TypeError:
                    # Non-summable, fallback to last? Or list?
                    # "Add Item X", "Add Item Y" -> List of items?
                    # For simplicty/strictness, if we can't sum, we might not consolidate or just take last state.
                    consolidated_deltas.append(deltas[-1])
            elif first_delta.op == DeltaOp.REMOVE:
                 try:
                    total = sum(d.value for d in deltas)
                    consolidated_deltas.append(DeltaPatch(op=DeltaOp.REMOVE, path=path, value=total))
                 except TypeError:
                    consolidated_deltas.append(deltas[-1])
            else:
                # REPLACE / UPDATE -> Last One Wins
                consolidated_deltas.append(deltas[-1])

        # 2. Create Summary Event
        source_ids = [e.id for e in events]

        # Deterministic ID for summary?
        # Hash of (first_id, last_id, count)
        summary_id = uuid5(NAMESPACE_DNS, f"SUMMARY-{events[0].id}-{events[-1].id}-{len(events)}")

        summary_event = Event(
            id=summary_id,
            namespace=first.namespace,
            timestamp=datetime.now(timezone.utc),
            actor=ActorEnum.SYSTEM,
            action=first.action,
            object_id=first.object_id,
            delta=consolidated_deltas,
            antecedents=source_ids,
            truth_vector=first.truth_vector # Inherit from first for now
        )

        return summary_event

    def execute_consolidation(self, summary_event: Event, source_events: List[Event]):
        """
        Writes the summary event and marks source events as consolidated.
        """
        # Need to serialize carefully for DB
        delta_json = json.dumps([d.dict() for d in summary_event.delta])
        truth_json = summary_event.truth_vector.json()
        antecedents_json = json.dumps([str(u) for u in summary_event.antecedents])
        provenance_json = summary_event.provenance.json() if summary_event.provenance else None

        with self.pg.get_cursor() as cur:
            # 1. Insert Summary Event
            cur.execute("""
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(summary_event.id), summary_event.namespace, summary_event.timestamp,
                summary_event.actor.value, summary_event.action.value, str(summary_event.object_id),
                delta_json,
                antecedents_json,
                truth_json,
                provenance_json
            ))

            # 2. Update Source Events
            source_ids = [str(e.id) for e in source_events]
            cur.execute("""
                UPDATE events
                SET consolidated_into = %s
                WHERE id = ANY(%s)
            """, (str(summary_event.id), source_ids))

        log.info(f"Consolidated {len(source_events)} events into {summary_event.id}")
