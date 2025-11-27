from memory_thread.utils.ner import extract_entities
from memory_thread.utils.llm_provider import LLMProvider

llm_provider = LLMProvider()

def extract_structured_data(text: str) -> dict:
    """
    Performs extraction and returns a dictionary structured for the new
    MemoryObject model.
    """
    ner_data = extract_entities(text) or {}
    llm_data = llm_provider.extract(text) or {}

    # Combine entities from both sources
    entities = list(set(ner_data.get("persons", []) + ner_data.get("orgs", []) + ner_data.get("locations", [])))
    if "entity" in llm_data:
        entities.append(llm_data["entity"])

    # Combine topics from both sources (assuming NER might find some)
    topics = []
    if "topic" in llm_data:
        topics.append(llm_data["topic"])

    # Prepare the structured metadata object
    metadata = {
        "emotion": llm_data.get("emotion"),
        "deadline": llm_data.get("deadline")
    }

    return {
        "entities": list(set(entities)),
        "topics": list(set(topics)),
        "metadata": metadata
    }
