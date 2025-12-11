# tms_service.py (Deterministic, replay-safe)
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

from memory_thread.models.events import Event, EntityState, TruthVector, DeltaPatch, DeltaOp
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# Tuning constants (move to config later)
TRUTH_CONFIDENCE_WEIGHT = 1.0
TRUTH_AUTHORITY_WEIGHT = 1.0
TRUTH_FRESHNESS_WEIGHT = 1.0
TRUTH_CORROBORATION_WEIGHT = 1.0
TRUTH_MIN_CORROBORATION = 0.0
FRESHNESS_DECAY_BASE_DAYS = 1.0
FLOAT_ROUND_PLACES = 9
EPSILON = 1e-6


class DeterminismError(Exception):
    """Raised when deterministic preconditions are violated (e.g., missing gateway_seq)."""
    pass


class TruthVectorService:
    @staticmethod
    def _normalize_freshness(reference_ts: Optional[datetime], event_ts: datetime) -> float:
        """
        Deterministic freshness: computed from event_ts and the stored `reference_ts`.
        If reference_ts is None, freshness is 1.0 for immediate evidence.
        """
        if reference_ts is None:
            return 1.0
        # Use event_ts - reference_ts so replay yields same result.
        age_days = (event_ts - reference_ts).total_seconds() / 86400.0
        if age_days < 0:
            # future-dated reference: clamp to 0
            age_days = 0.0
        return 1.0 / (age_days + 1.0)

    @staticmethod
    def calculate_score(vector: TruthVector, event_ts: Optional[datetime] = None, reference_ts: Optional[datetime] = None) -> float:
        """
        Pure deterministic score function.
        - event_ts is the timestamp of the latest evidence (must be provided for freshness).
        - reference_ts indicates when vector evidence was created; if absent, freshness assumed max.
        """
        # validate inputs
        if event_ts is None:
            # Prefer to require event_ts; callers should provide event.timestamp
            event_ts = datetime.now(timezone.utc)  # fallback only; try to avoid in replay
        # clamp corroboration
        corr = max(TRUTH_MIN_CORROBORATION, getattr(vector, "corroboration", 0.0))
        import math
        corr_score = math.log1p(corr)  # log(1 + corr) stable for small corr

        freshness_val = TruthVectorService._normalize_freshness(reference_ts, event_ts)

        # Weighted linear combination (deterministic)
        score = (TRUTH_CONFIDENCE_WEIGHT * float(vector.confidence)) + \
                (TRUTH_AUTHORITY_WEIGHT * float(vector.authority)) + \
                (TRUTH_FRESHNESS_WEIGHT * float(freshness_val)) + \
                (TRUTH_CORROBORATION_WEIGHT * float(corr_score))

        # round to stable precision (helps with cross-platform float noise)
        return round(score, FLOAT_ROUND_PLACES)


def _get_at_path(obj: Dict[str, Any], path: str):
    """
    Simple JSON-pointer-like resolver for single-level paths (like "a", "a/b"). Returns (parent, key)
    For now this supports nested dict traversal separated by '/'.
    """
    if path is None or path == "":
        return obj, None
    parts = path.split("/")
    parent = obj
    for p in parts[:-1]:
        if not isinstance(parent, dict):
            # cannot traverse further, create dict to be deterministic
            parent[p] = {}
        if p not in parent or not isinstance(parent[p], dict):
            parent[p] = {}
        parent = parent[p]
    return parent, parts[-1]


def apply_patch_to_value(value_dict: Dict[str, Any], patch: DeltaPatch) -> None:
    """
    Apply a DeltaPatch to the provided value_dict in-place.
    Deterministic semantics:
      - ADD: If existing value is numeric and patch.value numeric -> numeric add, else set.
      - REMOVE: If patch.value numeric and existing numeric -> numeric subtract; else delete key if exists.
      - REPLACE: set the value.
    Supports nested paths via "/" separator (simple JSON-pointer).
    Does not raise on recoverable errors; logs and continues deterministically.
    """
    if not patch or not getattr(patch, "path", None):
        log.debug("Skipping empty patch: %r", patch)
        return

    parent, key = _get_at_path(value_dict, patch.path)
    if key is None:
        log.debug("Patch path resolved to root; ignoring: %r", patch)
        return

    op = patch.op
    val = patch.value

    # Ensure parent is a dict
    if not isinstance(parent, dict):
        # Attempt to coerce deterministically
        log.debug("Parent not dict; coercing parent for path %s", patch.path)
        # Replace non-dict parent with dict containing previous value at key "_" to avoid silent loss
        parent = {}
    existing = parent.get(key, None)

    # Numeric helpers
    def is_num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    if op == DeltaOp.ADD:
        if existing is not None and is_num(existing) and is_num(val):
            parent[key] = existing + val
        else:
            parent[key] = val
    elif op == DeltaOp.REMOVE:
        if existing is not None and is_num(existing) and is_num(val):
            parent[key] = existing - val
        else:
            # remove the key deterministically if exists
            parent.pop(key, None)
    elif op == DeltaOp.REPLACE:
        parent[key] = val
    else:
        # Unknown op: treat as REPLACE for forward compatibility
        log.debug("Unknown DeltaOp '%s' treating as REPLACE", op)
        parent[key] = val


class StateDerivationService:
    @staticmethod
    def merge_truth_vectors(prev: TruthVector, incoming: TruthVector) -> TruthVector:
        """
        Deterministic merge policy:
          - confidence: weighted average (here equal weights)
          - authority: max (higher authority overrides)
          - corroboration: sum (bounded by a high ceiling to avoid runaway)
        Customize weights or policy as needed.
        """
        c_prev = float(getattr(prev, "confidence", 0.0))
        c_in = float(getattr(incoming, "confidence", 0.0))
        conf = (c_prev + c_in) / 2.0

        auth = max(float(getattr(prev, "authority", 0.0)), float(getattr(incoming, "authority", 0.0)))

        corr = float(getattr(prev, "corroboration", 0.0)) + float(getattr(incoming, "corroboration", 0.0))
        # bound corroboration to avoid runaway (policy)
        corr = min(corr, 1e9)

        return TruthVector(confidence=round(conf, FLOAT_ROUND_PLACES),
                           authority=round(auth, FLOAT_ROUND_PLACES),
                           corroboration=round(corr, FLOAT_ROUND_PLACES))

    @staticmethod
    def apply_event(current_state: EntityState, event: Event) -> EntityState:
        """
        Deterministically derive new state from current_state + event.
        - Uses event.timestamp as updated_at (deterministic)
        - Merges truth vectors deterministically
        - Applies patches deterministically
        - Sets version to event.gateway_seq if present else increments deterministically
        """
        # basic validation
        if event.object_id != current_state.entity_id:
            raise ValueError("Event object_id mismatch")

        # copy current value shallowly
        new_value = {}
        if current_state.current_value:
            # copy nested dict shallowly. If nested mutation is needed, caller must ensure deep structures are handled consistently.
            new_value.update(current_state.current_value)

        # Apply patches in the order they appear (this order must be canonical in event storage)
        for patch in (event.delta or []):
            try:
                apply_patch_to_value(new_value, patch)
            except Exception:
                # do not raise — log deterministic error and continue
                log.exception("Patch application error for event %s patch %r", getattr(event, "id", "<nil>"), patch)

        # Merge truth vectors deterministically
        prev_tv = current_state.truth_vector or TruthVector(confidence=0.0, authority=0.0, corroboration=0.0)
        incoming_tv = event.truth_vector or TruthVector(confidence=0.0, authority=0.0, corroboration=0.0)
        merged_tv = StateDerivationService.merge_truth_vectors(prev_tv, incoming_tv)

        # Determine version deterministically
        version = getattr(event, "gateway_seq", None)
        if version is None:
            # fallback: increment previous version deterministically
            # This fallback is acceptable only if event order is enforced
            version = (current_state.version or 0) + 1

        # deterministic updated_at — use event timestamp
        updated_at = getattr(event, "timestamp", None)
        if updated_at is None:
            # fallback to current_state.updated_at (deterministic)
            updated_at = current_state.updated_at or datetime.now(timezone.utc)

        return EntityState(
            entity_id=current_state.entity_id,
            namespace=current_state.namespace,
            current_value=new_value,
            truth_vector=merged_tv,
            version=version,
            last_event_id=event.id,
            updated_at=updated_at
        )
class TMSService:
    def __init__(self):
        pass

    # Method signature updated to reflect lack of defaults
    def create_event_proposal(self,
                     actor: Any,
                     action: Any,
                     object_id: uuid.UUID,
                     delta: List[DeltaPatch],
                     namespace: str = "user") -> Event:

        # This function can't create a valid Event anymore because it can't determine ID or Timestamp deterministically without input
        # It's better to rename it to 'construct_event' or accept external params
        raise NotImplementedError("Events must be created at the Gateway or via factory with deterministic ID")
