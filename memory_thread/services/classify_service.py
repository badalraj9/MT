import re
from typing import Tuple

# More specific classification rules to differentiate identity and preference.
IDENTITY_TRIGGERS = r"\b(i am|i'm|i live in|my name is)\b"
PREFERENCE_TRIGGERS = r"\b(i prefer|my favorite|i like|i always|i usually)\b"
TEMPORAL_TRIGGERS = r"\b(today|yesterday|tonight|this morning|right now|i'm feeling)\b"
NEGATION_TRIGGERS = r"\b(not|don't|no longer|stopped|quit|isn't|aren't)\b"

def classify_memory(text: str) -> Tuple[str, bool]:
    """
    Classifies the memory type based on predefined regex triggers.
    Differentiates between identity, preference, and event types.

    Args:
        text: The input text to classify.

    Returns:
        A tuple containing:
        - The classified memory type ('identity', 'preference', 'event', 'timeline_update').
        - A boolean indicating if negation was detected.
    """
    text_lower = text.lower()

    has_identity_trigger = re.search(IDENTITY_TRIGGERS, text_lower) is not None
    has_preference_trigger = re.search(PREFERENCE_TRIGGERS, text_lower) is not None
    has_temporal_trigger = re.search(TEMPORAL_TRIGGERS, text_lower) is not None
    has_negation_trigger = re.search(NEGATION_TRIGGERS, text_lower) is not None

    memory_type = "event" # Default type

    is_stable = has_identity_trigger or has_preference_trigger

    if is_stable and has_negation_trigger:
        memory_type = "timeline_update"
    elif has_identity_trigger:
        memory_type = "identity"
    elif has_preference_trigger:
        memory_type = "preference"
    elif has_temporal_trigger:
        memory_type = "event"

    return memory_type, has_negation_trigger
