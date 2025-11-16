import re
from typing import Tuple

# Classification rules as defined in the specification.
STABLE_TRIGGERS = r"\b(i am|i'm|i always|i usually|i prefer|my favorite|i live|i like)\b"
TEMPORAL_TRIGGERS = r"\b(today|yesterday|tonight|this morning|right now|i'm feeling)\b"
NEGATION_TRIGGERS = r"\b(not|don't|no longer|stopped|quit|isn't|aren't)\b"

def classify_memory(text: str) -> Tuple[str, bool]:
    """
    Classifies the memory type based on predefined regex triggers.

    Args:
        text: The input text to classify.

    Returns:
        A tuple containing:
        - The classified memory type ('event', 'timeline_update', or 'stable_memory').
        - A boolean indicating if negation was detected.
    """
    text_lower = text.lower()

    has_stable_trigger = re.search(STABLE_TRIGGERS, text_lower) is not None
    has_temporal_trigger = re.search(TEMPORAL_TRIGGERS, text_lower) is not None
    has_negation_trigger = re.search(NEGATION_TRIGGERS, text_lower) is not None

    memory_type = "event" # Default type

    if has_stable_trigger and has_negation_trigger:
        memory_type = "timeline_update"
    elif has_stable_trigger and not has_negation_trigger:
        memory_type = "stable_memory"
    elif has_temporal_trigger:
        memory_type = "event"

    return memory_type, has_negation_trigger
