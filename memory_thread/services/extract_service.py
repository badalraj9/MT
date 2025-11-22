from memory_thread.utils.ner import extract_entities
from memory_thread.utils.llm_provider import LLMProvider

llm_provider = LLMProvider()

CRITICAL_FIELDS = {
    "deadline", "emotion", "location", "time",
    "person", "topic", "value"
}


def extract_structured_data(text: str) -> dict | None:
    """
    Three-step extraction:
      1. NER extraction
      2. LLM structured extraction
      3. Merge & filter critical fields
    """

    # Step 1 — NER
    ner_data = extract_entities(text) or {}

    # Step 2 — LLM structured extraction
    llm_data = llm_provider.extract(text) or {}

    # Step 3 — Filter & merge
    final = {}

    # First: NER fields
    for k, v in ner_data.items():
        if k in CRITICAL_FIELDS:
            final[k] = v

    # Second: LLM fields override
    for k, v in llm_data.items():
        if k in CRITICAL_FIELDS:
            final[k] = v

    # Return None if nothing meaningful extracted
    return final if final else None