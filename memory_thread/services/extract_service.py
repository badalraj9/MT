from memory_thread.utils.ner import extract_entities
from memory_thread.utils.llm_provider import LLMProvider
from memory_thread.utils.regex_extractor import extract_patterns
from memory_thread.services.reasoning.relation_extractor import RelationExtractor

llm_provider = LLMProvider()
relation_extractor = RelationExtractor()

def extract_structured_data(text: str) -> dict:
    regex_data = extract_patterns(text) or {}
    ner_data = extract_entities(text) or {}
    llm_data = llm_provider.extract(text) or {}

    entities = list(set(ner_data.get("persons", []) + ner_data.get("orgs", []) + ner_data.get("locations", [])))
    if "entity" in llm_data: entities.append(llm_data["entity"])
    if "email" in regex_data: entities.extend(regex_data["email"])

    topics = [llm_data["topic"]] if "topic" in llm_data else []
    metadata = {"emotion": llm_data.get("emotion"), "deadline": llm_data.get("deadline")}
    if "date" in regex_data: metadata["dates"] = regex_data["date"]

    # Extract relations
    relations = relation_extractor.extract_relations(text)

    return {
        "entities": list(set(entities)),
        "topics": topics,
        "metadata": metadata,
        "relations": relations
    }
