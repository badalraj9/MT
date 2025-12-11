# ingest_service.py (Hardened)
import multiprocessing as mp
import time
import struct
import json
import uuid
from datetime import datetime, timezone
from typing import List, Union, Dict, Any, Optional
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.models.events import Event, EntityState, ActorEnum, ActionEnum, DeltaPatch, TruthVector, Provenance
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.utils.logger import get_logger
from memory_thread.nervous.persistence_engine import PersistenceEngine

log = get_logger(__name__)

# JSON serializer for non-standard types
def _json_serial(obj):
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    # pydantic models often expose .model_dump() or .dict()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Type {type(obj)} not serializable")

def _ensure_utc(dt: Union[str, datetime]) -> datetime:
    if isinstance(dt, str):
        # Accept ISO strings; let fromisoformat raise if invalid
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _coerce_deltas(delta_list: Any) -> List[DeltaPatch]:
    if not delta_list:
        return []
    if isinstance(delta_list, str):
        try:
            delta_list = json.loads(delta_list)
        except Exception:
            return []
    out = []
    for d in delta_list:
        if isinstance(d, DeltaPatch):
            out.append(d)
        elif isinstance(d, dict):
            out.append(DeltaPatch(**d))
        else:
            # unsupported patch entry — skip but log
            log.debug("Unsupported delta patch entry while coercing: %r", d)
    return out

def worker_process(allocator: SlabAllocator,
                   persistence_engine: Optional[PersistenceEngine],
                   ipc_address: str = "ipc://persistence_pipe",
                   stop_event: Optional[mp.Event] = None):
    """
    Worker loop reading slabs, hydrating events, running a safe local derivation check
    and forwarding payloads to the QueueManager/persistence layer.
    """
    from memory_thread.nervous.queue_manager import QueueManager

    qm = QueueManager(address=ipc_address)
    qm.setup_producer()

    log.info("Ingestion worker started (pid=%s)", mp.current_process().pid)
    meta_service = MetaStabilityService()

    backoff = 0.001
    try:
        while True:
            if stop_event and stop_event.is_set():
                log.info("Stop requested for ingestion worker (pid=%s). Exiting loop.", mp.current_process().pid)
                break

            slab = allocator.get_written_slab()
            if slab is None:
                # no work right now — small sleep with backoff
                time.sleep(backoff)
                backoff = min(0.1, backoff * 2)
                continue
            # reset backoff on work
            backoff = 0.001

            try:
                # Read length header safely
                if len(slab.memory) < 4:
                    log.error("Malformed slab (too small header). Releasing slab %s", getattr(slab, "slab_id", "<unknown>"))
                    allocator.release_slab(slab.slab_id)
                    continue

                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]
                if msg_len <= 0 or (4 + msg_len) > len(slab.memory):
                    log.error("Malformed slab length %s for slab %s", msg_len, getattr(slab, "slab_id", "<unknown>"))
                    allocator.release_slab(slab.slab_id)
                    continue

                raw_data = slab.memory[4:4 + msg_len].tobytes()
                try:
                    content_obj = json.loads(raw_data)
                except json.JSONDecodeError:
                    log.error("Ingestion Worker received non-JSON data. Dropping slab %s", getattr(slab, "slab_id", "<unknown>"))
                    allocator.release_slab(slab.slab_id)
                    continue

                # Validate minimal event schema
                if not isinstance(content_obj, dict):
                    log.error("Event payload not an object; dropping.")
                    allocator.release_slab(slab.slab_id)
                    continue

                required = ("id", "namespace", "timestamp", "actor", "action", "object_id")
                missing = [r for r in required if r not in content_obj]
                if missing:
                    log.error("Missing required event fields %s — dropping event", missing)
                    allocator.release_slab(slab.slab_id)
                    continue

                # Robust hydration
                try:
                    evt_id = uuid.UUID(content_obj["id"])
                except Exception as e:
                    log.error("Invalid event id: %s — dropping: %s", content_obj.get("id"), e)
                    allocator.release_slab(slab.slab_id)
                    continue

                try:
                    ts = _ensure_utc(content_obj["timestamp"])
                except Exception as e:
                    log.error("Invalid timestamp on event %s: %s", evt_id, e)
                    allocator.release_slab(slab.slab_id)
                    continue

                try:
                    deltas = _coerce_deltas(content_obj.get("delta"))
                except Exception:
                    deltas = []

                # hydrate optional complex types safely
                tv = content_obj.get("truth_vector") or {}
                prov = content_obj.get("provenance")

                try:
                    evt = Event(
                        id=evt_id,
                        namespace=content_obj["namespace"],
                        timestamp=ts,
                        actor=ActorEnum(content_obj["actor"]),
                        action=ActionEnum(content_obj["action"]),
                        object_id=uuid.UUID(content_obj["object_id"]),
                        delta=deltas,
                        antecedents=[uuid.UUID(u) for u in content_obj.get("antecedents", [])],
                        truth_vector=TruthVector(**tv) if tv else TruthVector(confidence=0, authority=0, corroboration=0),
                        provenance=Provenance(**prov) if prov else None,
                        gateway_seq=content_obj.get("gateway_seq", 0),
                        dedup_hash=content_obj.get("dedup_hash")
                    )
                except Exception as e:
                    # As a final fallback, try Pydantic model_validate if available
                    try:
                        hydrate = getattr(Event, "model_validate", None)
                        if callable(hydrate):
                            evt = hydrate({**content_obj, "timestamp": ts, "id": str(evt_id)})
                        else:
                            raise
                    except Exception as e2:
                        log.exception("Failed to hydrate Event from payload: %s", e2)
                        allocator.release_slab(slab.slab_id)
                        continue

                # Meta-stability check (lightweight)
                try:
                    ok = meta_service.check_integrity(evt)
                    if not ok:
                        log.warning("Meta-stability warning for event %s", evt.id)
                except Exception:
                    log.debug("Meta-stability check crashed (nonfatal)", exc_info=True)

                # Local derivation check (pure & idempotent): do not persist anything here
                try:
                    current_state = EntityState(
                        entity_id=evt.object_id,
                        namespace=evt.namespace,
                        current_value={},
                        truth_vector=evt.truth_vector,
                        last_event_id=uuid.UUID('00000000-0000-0000-0000-000000000000'), # Placeholder safe UUID
                        updated_at=evt.timestamp,
                        version=0
                    )
                    # apply_event must be pure and deterministic — this is only a local check
                    new_state = StateDerivationService.apply_event(current_state, evt)
                except Exception:
                    log.exception("State derivation failed for event %s (nonfatal)", evt.id)
                    allocator.release_slab(slab.slab_id)
                    continue

                # Build canonical output payload (no side-effects here)
                output_payload = {
                    "event": evt.model_dump() if hasattr(evt, "model_dump") else evt.dict(),
                    "state": new_state.model_dump() if hasattr(new_state, "model_dump") else new_state.dict()
                }

                # Send to persistence queue
                try:
                    # Ensure JSON serializable canonical form
                    payload_text = json.dumps(output_payload, default=_json_serial, separators=(",", ":"), sort_keys=True)
                    qm.send(json.loads(payload_text))
                except Exception:
                    log.exception("Failed to send payload for event %s", evt.id)
                    # Do not abort; continue and release slab

                # Release slab after successful processing
                allocator.release_slab(slab.slab_id)

            except Exception:
                log.exception("Unhandled error processing slab %s", getattr(slab, "slab_id", "<unknown>"))
                try:
                    allocator.release_slab(slab.slab_id)
                except Exception:
                    log.exception("Failed to release slab in error handler")
    finally:
        try:
            qm.close()
        except Exception:
            log.debug("QueueManager.close failed (nonfatal)", exc_info=True)
        log.info("Worker process exiting (pid=%s)", mp.current_process().pid)


class IngestionService:
    def __init__(self, num_slabs: int = 128, slab_size: int = 65536, ipc_address: str = "ipc://persistence_pipe"):
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self.workers: List[mp.Process] = []
        self.persistence_engine = PersistenceEngine()
        self.ipc_address = ipc_address
        self._stop_event = mp.Event()

    def start(self):
        self.persistence_engine.start()

        # terminate any existing workers
        for p in self.workers:
            if p.is_alive():
                p.terminate()
        self.workers = []

        num_workers = max(1, mp.cpu_count() - 2)
        for _ in range(num_workers):
            p = mp.Process(target=worker_process, args=(self.allocator, self.persistence_engine, self.ipc_address, self._stop_event))
            p.daemon = True
            p.start()
            self.workers.append(p)
        log.info("Started %d worker processes.", len(self.workers))

    def ingest_event_dict(self, event_dict: Dict[str, Any]):
        """
        Accepts a pre-validated Event dictionary (from Gateway). This method performs
        minimal validation and writes the message to a shared-slab using a prefixed length header.
        """
        if not isinstance(event_dict, dict):
            log.error("ingest_event_dict requires a dict")
            return False

        # ensure timestamp normalized to UTC ISO string
        ts = event_dict.get("timestamp")
        if ts:
            try:
                event_dict["timestamp"] = _ensure_utc(ts).isoformat()
            except Exception:
                log.error("ingest_event_dict: invalid timestamp")
                return False
        else:
            # set server-received timestamp (deterministic to system clock) — prefer gateway-provided
            event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()

        # ensure id exists
        if "id" not in event_dict:
            log.error("Event missing 'id' field")
            return False

        try:
            encoded_data = json.dumps(event_dict, default=_json_serial).encode("utf-8")
        except Exception:
            log.exception("Failed to encode event dict")
            return False

        msg_len = len(encoded_data)
        if msg_len + 4 > self.allocator.slab_size:
            log.error("Event too large for slab (size=%d, limit=%d)", msg_len + 4, self.allocator.slab_size)
            return False

        slab = self.allocator.reserve_slab()
        try:
            slab.memory[:4] = struct.pack("!I", msg_len)
            slab.memory[4:4 + msg_len] = encoded_data
            self.allocator.mark_as_written(slab.slab_id)
            return True
        except Exception:
            log.exception("Failed to write to slab")
            try:
                self.allocator.release_slab(slab.slab_id)
            except Exception:
                log.exception("Failed to release slab after write failure")
            return False

    def shutdown(self):
        # request workers to stop gracefully
        try:
            self._stop_event.set()
            for p in self.workers:
                if p.is_alive():
                    p.join(timeout=1)
                    if p.is_alive():
                        p.terminate()
                        p.join(timeout=1)
        except Exception:
            log.exception("Error shutting down workers")

        try:
            self.persistence_engine.stop()
        except Exception:
            log.exception("Error stopping persistence engine")

        try:
            self.allocator.unlink()
        except Exception:
            log.exception("Error unlinking allocator")

# global instance for convenience (tests may override)
ingestion_service = IngestionService()
