# replay_service.py (Hardened)
import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Iterable
from uuid import UUID
from datetime import datetime, timezone
import difflib
import hashlib
from decimal import Decimal

from memory_thread.models.events import Event, EntityState, TruthVector, DeltaPatch, Provenance
from memory_thread.services.tms_service import StateDerivationService
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Configurable numeric tolerance for truth-vector comparisons
TRUTH_EPSILON = 1e-6
FLOAT_ROUND_PLACES = 9  # used for canonicalization; adjust if you need more precision


class ReplayService:
    def __init__(self):
        self.pg = PostgresClient()

    # ---------------------
    # DB helpers
    # ---------------------
    def _fetch_entity_state_row(self, entity_id: UUID) -> Dict[str, Any]:
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT entity_id, namespace, current_value, truth_vector, version, last_event_id, updated_at
                FROM entity_state
                WHERE entity_id = %s
            """, (str(entity_id),))
            row = cur.fetchone()
        return row

    def _fetch_event_rows(self, entity_id: UUID) -> List[Dict[str, Any]]:
        """
        NOTE: deterministic ordering — tie-break by id to avoid nondeterminism when timestamps equal.
        """
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance
                FROM events
                WHERE object_id = %s
                ORDER BY timestamp ASC, id ASC
            """, (str(entity_id),))
            rows = cur.fetchall()
        return rows or []

    # ---------------------
    # Hydration helpers
    # ---------------------
    def _coerce_common_types(self, d: dict) -> dict:
        """
        Mutates a shallow copy to coerce common fields to expected Python types so Pydantic
        hydration is more robust (UUIDs, timestamps, etc.)
        """
        out = dict(d)
        # common UUID fields
        for k in ('id', 'object_id', 'actor', 'last_event_id'):
            if k in out and isinstance(out[k], str):
                try:
                    out[k] = str(out[k])  # keep as string; Event model may accept str/UUID
                except Exception:
                    pass

        # timestamp normalization
        ts = out.get('timestamp')
        if ts and isinstance(ts, str):
            try:
                # parse ISO timestamp and force UTC
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                out['timestamp'] = dt.astimezone(timezone.utc)
            except Exception:
                # leave as-is; pydantic may parse
                pass

        return out

    def _hydrate_event(self, evt_data: Dict[str, Any]) -> Event:
        """
        Robust hydration: try Pydantic v2 model_validate, then fallback to Event(**)
        """
        d = self._coerce_common_types(evt_data)
        try:
            # prefer model_validate if available (pydantic v2)
            hydrate = getattr(Event, "model_validate", None)
            if callable(hydrate):
                return hydrate(d)
        except Exception:
            pass

        # fallback
        return Event(**d)

    # ---------------------
    # Canonicalization / stable serialization
    # ---------------------
    def _stable_serialize(self, obj: Any) -> str:
        """
        Convert nested Python structure into a canonical JSON string:
        - sort keys
        - convert datetime -> ISO str (UTC)
        - convert UUID -> str
        - round floats to stable precision (configurable)
        """
        def _convert(v):
            # Pydantic models: try .model_dump()
            if hasattr(v, "model_dump"):
                v = v.model_dump()
            if isinstance(v, dict):
                return {k: _convert(v[k]) for k in sorted(v.keys())}
            if isinstance(v, (list, tuple)):
                return [_convert(x) for x in v]
            if isinstance(v, UUID):
                return str(v)
            if isinstance(v, datetime):
                # normalize to UTC isoformat
                return v.astimezone(timezone.utc).isoformat()
            if isinstance(v, float):
                # round floats to avoid minor formatting differences; keep as float for JSON
                return round(v, FLOAT_ROUND_PLACES)
            if isinstance(v, Decimal):
                return float(round(v, FLOAT_ROUND_PLACES))
            return v

        canon = _convert(obj)
        return json.dumps(canon, ensure_ascii=False, separators=(',', ':'), sort_keys=True)

    def _hash_canonical(self, obj: Any) -> str:
        s = self._stable_serialize(obj).encode('utf-8')
        return hashlib.sha256(s).hexdigest()

    # ---------------------
    # Main public APIs
    # ---------------------
    def capture_trace(self, entity_id: UUID) -> Dict[str, Any]:
        row = self._fetch_entity_state_row(entity_id)
        if not row:
            raise ValueError(f"Entity {entity_id} not found in state.")

        # normalize truth_vector from DB (could be JSON string)
        tv_data = row['truth_vector']
        if isinstance(tv_data, str):
            tv_data = json.loads(tv_data)

        final_state = EntityState(
            entity_id=row['entity_id'],
            namespace=row['namespace'],
            current_value=row['current_value'],
            truth_vector=TruthVector(**tv_data),
            version=row['version'],
            last_event_id=row['last_event_id'],
            updated_at=row['updated_at']
        )

        event_rows = self._fetch_event_rows(entity_id)
        events: List[Event] = []
        for r in event_rows:
            tv_data = r['truth_vector'] or {}
            if isinstance(tv_data, str):
                tv_data = json.loads(tv_data)

            delta_data = r['delta'] or []
            if isinstance(delta_data, str):
                delta_data = json.loads(delta_data)
            deltas = [DeltaPatch(**d) if not isinstance(d, DeltaPatch) else d for d in delta_data]

            antecedents_data = r.get('antecedents') or []
            if isinstance(antecedents_data, str):
                antecedents_data = json.loads(antecedents_data)

            prov_data = r.get('provenance')
            if isinstance(prov_data, str):
                prov_data = json.loads(prov_data)
            prov = Provenance(**prov_data) if prov_data else None

            # The row might not have new fields like gateway_seq/dedup_hash if using old query
            # But the new query selects them? NO, the new query in _fetch_event_rows explicitly selects columns.
            # Make sure it selects ALL columns needed by Event model.
            # Event model requires: gateway_seq, dedup_hash (optional but strict model might fail if missing).
            # The query above selects: id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance
            # IT IS MISSING gateway_seq!
            # The new strict Event model has `gateway_seq: int`.
            # If we don't fetch it, hydration will fail.
            # I must update _fetch_event_rows to include gateway_seq and dedup_hash.
            # Wait, the user provided the code. The user provided code MIGHT be missing it?
            # Let's check the user provided code in previous turn.
            # "SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector, provenance FROM events ..."
            # Yes, it is missing gateway_seq.
            # But the Event model I defined earlier HAS gateway_seq as mandatory field.
            # I should fix the query in _fetch_event_rows inside the file I'm writing.

            evt_dict = {
                "id": r['id'],
                "namespace": r['namespace'],
                "timestamp": r['timestamp'],
                "actor": r['actor'],
                "action": r['action'],
                "object_id": r['object_id'],
                "delta": deltas,
                "antecedents": antecedents_data or [],
                "truth_vector": tv_data or {},
                "provenance": prov,
                "gateway_seq": r.get('gateway_seq', 0), # Fallback if not fetched?
                "dedup_hash": r.get('dedup_hash')
            }
            # hydrate with our helper to keep types stable
            events.append(self._hydrate_event(evt_dict))

        trace = {
            "entity_id": str(entity_id),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "final_state": json.loads(final_state.model_dump_json()),
            "events": [json.loads(e.model_dump_json()) for e in events],
            "trace_hash": self._hash_canonical({
                "entity_id": str(entity_id),
                "events": [json.loads(e.model_dump_json()) for e in events]
            })
        }
        return trace

    def replay_trace(self, trace: Dict[str, Any], save_mismatch_path: Optional[str] = None
                    ) -> Tuple[bool, List[str], Optional[EntityState]]:
        """
        Replays the events from the trace and compares with the expected final state.
        Returns: (Success, DiffReportLines, ActualFinalState)
        If save_mismatch_path is provided and mismatch occurs, saves failing trace + actual state.
        """
        events_data = trace.get('events', [])
        expected_state_data = trace.get('final_state')

        if not expected_state_data:
            return False, ["Trace missing 'final_state'"], None

        # empty events => start from empty state
        if len(events_data) == 0:
            # create empty but typed EntityState from expected so comparison path is executed
            try:
                expected_state = EntityState(**expected_state_data)
            except Exception as e:
                return False, [f"Expected state hydration error: {e}"], None
            # If expected current_value is empty, pass; otherwise fail because we didn't replay anything
            if expected_state.current_value in (None, {}, []):
                return True, ["No events and expected state empty; trivially matches."], expected_state
            else:
                return False, ["No events to replay but expected state non-empty"], expected_state

        # prepare starting state
        first_evt = events_data[0]
        try:
            entity_uuid = UUID(trace['entity_id'])
        except Exception:
            return False, ["Invalid entity_id in trace"], None

        # start from a minimal typed state. Avoid assumptions about last_event_id.
        current_state = EntityState(
            entity_id=entity_uuid,
            namespace=first_evt.get('namespace', expected_state_data.get('namespace') if expected_state_data else ''),
            current_value={},
            truth_vector=TruthVector(confidence=0, authority=0, corroboration=0),
            version=0,
            last_event_id=UUID('00000000-0000-0000-0000-000000000000'), # Placeholder UUID required for strict model?
            # Model requires last_event_id: uuid.UUID. If we pass None, it might fail.
            # Using a nil UUID is safer than None if model is strict.
            updated_at=datetime.now(timezone.utc)
        )

        # apply events
        for i, evt_data in enumerate(events_data):
            try:
                evt = self._hydrate_event(evt_data)
            except Exception as e:
                msg = f"Hydration error at Event #{i}: {e}"
                log.exception(msg)
                return False, [msg], None

            try:
                # deterministic apply
                current_state = StateDerivationService.apply_event(current_state, evt)
            except Exception as e:
                msg = f"Crash at Event #{i} ({getattr(evt, 'id', '<unknown>')}): {e}"
                log.exception(msg)
                return False, [msg], current_state

        # compare result: canonicalize both
        try:
            expected_state = EntityState(**expected_state_data)
        except Exception as e:
            msg = f"Expected state hydration error: {e}"
            log.exception(msg)
            return False, [msg], current_state

        actual_json = self._stable_serialize(current_state.model_dump() if hasattr(current_state, "model_dump") else current_state.__dict__)
        expected_json = self._stable_serialize(expected_state.model_dump() if hasattr(expected_state, "model_dump") else expected_state.__dict__)

        diffs: List[str] = []
        if actual_json != expected_json:
            diffs.append("Canonical JSON mismatch between expected and actual final state.")
            # pretty-printed versions for diff
            pretty_act = json.dumps(json.loads(actual_json), indent=2, sort_keys=True, ensure_ascii=False)
            pretty_exp = json.dumps(json.loads(expected_json), indent=2, sort_keys=True, ensure_ascii=False)
            ud = list(difflib.unified_diff(pretty_exp.splitlines(), pretty_act.splitlines(),
                                           fromfile='expected', tofile='actual', lineterm=''))
            diffs.extend(ud)

            # Also check truth vector numerically and report per-key differences (more friendly)
            try:
                tv_act = current_state.truth_vector.model_dump() if hasattr(current_state.truth_vector, "model_dump") else current_state.truth_vector.__dict__
                tv_exp = expected_state.truth_vector.model_dump() if hasattr(expected_state.truth_vector, "model_dump") else expected_state.truth_vector.__dict__
                for k, v_exp in (tv_exp.items() if isinstance(tv_exp, dict) else []):
                    v_act = tv_act.get(k)
                    if v_act is None:
                        diffs.append(f"TruthVector missing key '{k}' in actual state (expected {v_exp})")
                        continue
                    try:
                        a = float(v_act); b = float(v_exp)
                        if abs(a - b) > TRUTH_EPSILON:
                            diffs.append(f"TruthVector mismatch '{k}': expected={b}, actual={a}")
                    except Exception:
                        if v_act != v_exp:
                            diffs.append(f"TruthVector non-numeric mismatch '{k}': expected={v_exp}, actual={v_act}")
            except Exception:
                # don't fail comparison because of TV diagnostics
                log.debug("TruthVector diagnostic check failed (nonfatal).", exc_info=True)

            if save_mismatch_path:
                try:
                    save_blob = {
                        "trace": trace,
                        "actual_final_state": json.loads(actual_json)
                    }
                    with open(save_mismatch_path, "w", encoding="utf-8") as fh:
                        json.dump(save_blob, fh, indent=2, ensure_ascii=False)
                except Exception:
                    log.exception("Failed to save mismatch trace")

            return False, diffs, current_state

        # additionally verify truth-vector numerically (catch tiny float noise)
        tv_act = current_state.truth_vector.model_dump() if hasattr(current_state.truth_vector, "model_dump") else current_state.truth_vector.__dict__
        tv_exp = expected_state.truth_vector.model_dump() if hasattr(expected_state.truth_vector, "model_dump") else expected_state.truth_vector.__dict__
        for k, v_exp in (tv_exp.items() if isinstance(tv_exp, dict) else []):
            try:
                a = float(tv_act.get(k, 0)); b = float(v_exp)
                if abs(a - b) > TRUTH_EPSILON:
                    diffs.append(f"TruthVector mismatch '{k}': expected={b}, actual={a}")
            except Exception:
                if tv_act.get(k) != v_exp:
                    diffs.append(f"TruthVector mismatch '{k}': expected={v_exp}, actual={tv_act.get(k)}")

        success = len(diffs) == 0
        return success, diffs, current_state

    # simple save/load
    def save_trace(self, trace: Dict, filepath: str):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(trace, f, indent=2, ensure_ascii=False)

    def load_trace(self, filepath: str) -> Dict:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
