
import sys
import os
import hashlib
import json
import uuid
import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory_thread.services.tms_service import TMSService
from memory_thread.models.events import ActorEnum, ActionEnum

def verify_determinism():
    print("Verifying Determinism...")
    
    tms = TMSService()
    
    # Input Data
    text = "The sky is blue."
    action = ActionEnum.UPDATE
    delta = {"content": text}
    
    # Explicit Time Injection
    fixed_ts = datetime.datetime(2025, 1, 1, 12, 0, 0)
    
    # Construct Content Hash (Logic from IngestService)
    def json_serial(obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return str(obj)

    content_hash = hashlib.sha256(json.dumps({
        "text": text, 
        "action": action.value, 
        "delta": json.dumps(delta, default=json_serial)
    }).encode()).hexdigest()
    
    NAMESPACE_MT = uuid.uuid5(uuid.NAMESPACE_DNS, "memory_thread.ai")
    
    # Generate IDs twice
    event_id_1 = uuid.uuid5(NAMESPACE_MT, content_hash)
    object_id_1 = uuid.uuid5(NAMESPACE_MT, content_hash)
    
    event_1 = tms.create_event(
        actor=ActorEnum.USER,
        action=action,
        object_id=object_id_1,
        delta=delta,
        namespace="user",
        event_id=event_id_1,
        timestamp=fixed_ts
    )
    
    print(f"Run 1: Event ID = {event_1.id}, TS = {event_1.timestamp}")
    
    # Run 2
    event_id_2 = uuid.uuid5(NAMESPACE_MT, content_hash)
    object_id_2 = uuid.uuid5(NAMESPACE_MT, content_hash)
    
    event_2 = tms.create_event(
        actor=ActorEnum.USER,
        action=action,
        object_id=object_id_2,
        delta=delta,
        namespace="user",
        event_id=event_id_2,
        timestamp=fixed_ts
    )
    
    print(f"Run 2: Event ID = {event_2.id}, TS = {event_2.timestamp}")
    
    if event_1.id != event_2.id:
        print("FAILURE: Event IDs do not match!")
        sys.exit(1)

    if event_1.object_id != event_2.object_id:
        print("FAILURE: Object IDs do not match!")
        sys.exit(1)
        
    if event_1.timestamp != event_2.timestamp:
        print("FAILURE: Timestamps do not match!")
        sys.exit(1)
        
    # Serialize and check exact JSON match
    json_1 = json.dumps(event_1.dict(), default=json_serial, sort_keys=True)
    json_2 = json.dumps(event_2.dict(), default=json_serial, sort_keys=True)
    
    if json_1 != json_2:
         print("FAILURE: Event JSON representations differ!")
         print(f"JSON 1: {json_1}")
         print(f"JSON 2: {json_2}")
         sys.exit(1)

    print("SUCCESS: Determinism Verified (ID, Object, Time, Payload).")

if __name__ == "__main__":
    verify_determinism()
