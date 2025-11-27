import logging
from datetime import datetime, timedelta
import math

log = logging.getLogger(__name__)

# Type-based decay rates from the original specification
DECAY_RATES = {
    'identity': 0.0005,
    'preference': 0.005,
    'summary': 0.01,
    'event': 0.02,
    'fact': 0.001, # Added from manifest
    'task': 0.01,  # Added from manifest
    'belief': 0.005, # Added from manifest
    'other': 0.02, # Added from manifest
    'timeline': 0.001 # Timelines should decay very slowly
}

def apply_decay_to_importance(initial_importance: float, memory_type: str, days_since_last_accessed: int) -> float:
    """
    Applies an exponential decay to a memory's importance score.
    Formula: w_new = w_old * exp(-decay_rate * days)
    """
    decay_rate = DECAY_RATES.get(memory_type, 0.02) # Default to a higher decay rate

    decayed_importance = initial_importance * math.exp(-decay_rate * days_since_last_accessed)

    # Ensure importance doesn't fall below a minimum threshold (e.g., 0.01)
    return max(0.01, decayed_importance)

def run_decay_process():
    """
    This function will be called by a background worker.
    It will fetch all memories, calculate their decayed importance, and update them in the DB.
    """
    # This is a placeholder for the full worker logic.
    log.info("Placeholder: Running the full memory decay process.")

    # Example for a single memory:
    # 1. Fetch a memory from Postgres.
    # 2. Get its `last_accessed` timestamp.
    # 3. Calculate `days_since_last_accessed`.
    # 4. Get its `importance` and `memory_type`.
    # 5. Call `apply_decay_to_importance`.
    # 6. Update the memory in Postgres with the new importance score.
    pass
