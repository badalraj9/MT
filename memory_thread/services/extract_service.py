from memory_thread.utils.ner import extract_entities
from memory_thread.utils.llm_provider import LLMProvider
from memory_thread.utils.regex_extractor import extract_patterns

llm_provider = LLMProvider()

def extract_structured_data(text: str) -> dict:
    """
    Performs a hybrid extraction using regex, spaCy NER, and a placeholder LLM,
    then returns a dictionary structured for the MemoryObject model.
    """
    # Step 1: Fast Regex Extraction
    regex_data = extract_patterns(text) or {}

    # Step 2: spaCy NER Extraction
    ner_data = extract_entities(text) or {}

    # Step 3: LLM Extraction (placeholder)
    llm_data = llm_provider.extract(text) or {}

    # Step 4: Merge results
    # spaCy provides more structured entities, so we start with that.
    entities = list(set(ner_data.get("persons", []) + ner_data.get("orgs", []) + ner_data.get("locations", [])))
    if "entity" in llm_data:
        entities.append(llm_data["entity"])

    # Add regex-found items to the entities list if they are not already covered
    for entity_type, found_items in regex_data.items():
        if entity_type in ['email', 'url']:
             entities.extend(found_items)

    # Topics are primarily from the LLM for now
    topics = []
    if "topic" in llm_data:
        topics.append(llm_data["topic"])

    # Prepare the structured metadata object
    metadata = {
        "emotion": llm_data.get("emotion"),
        "deadline": llm_data.get("deadline")
    }
    # Add dates from regex to metadata
    if "date" in regex_data:
        metadata["dates"] = regex_data["date"]

    return {
        "entities": list(set(entities)),
        "topics": list(set(topics)),
        "metadata": metadata
    }
