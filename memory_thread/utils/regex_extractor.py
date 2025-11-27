import re
from typing import Dict, List

# Pre-compiled regex patterns for efficiency
REGEX_PATTERNS = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "url": re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'),
    # A simple date pattern (e.g., YYYY-MM-DD, MM/DD/YYYY) - can be expanded
    "date": re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b'),
    # A simple numeric pattern for values
    "numeric_value": re.compile(r'\b\d+\.?\d*\b')
}

def extract_patterns(text: str) -> Dict[str, List[str]]:
    """
    Extracts entities from a text string using pre-defined regex patterns.

    Args:
        text: The input text.

    Returns:
        A dictionary where keys are entity types (e.g., 'email', 'date')
        and values are lists of the extracted strings.
    """
    extractions = {}
    for entity_type, pattern in REGEX_PATTERNS.items():
        found = pattern.findall(text)
        if found:
            extractions[entity_type] = found

    return extractions
