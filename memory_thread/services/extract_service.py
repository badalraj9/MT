from memory_thread.utils.ner import extract_entities
from memory_thread.utils.llm_provider import LLMProvider

# Initialize the LLM provider to be used for extraction.
llm_provider = LLMProvider()

def extract_structured_data(text: str) -> dict:
    """
    Orchestrates the 3-step extraction process for a given text.

    1. NER: Extracts basic entities like persons, locations, etc.
    2. Intent Classification (LLM): Uses an LLM to extract deeper insights.
    3. Filter: Combines and filters the results to keep only essential fields.

    Args:
        text: The input text from which to extract data.

    Returns:
        A dictionary containing the final extracted and filtered data.
    """
    # Step 1: NER with spaCy
    ner_entities = extract_entities(text)

    # Step 2: Intent Classification with LLM Provider
    # As per spec, the prompt is to extract entities, topics, emotions, and deadlines.
    llm_extractions = llm_provider.extract(text)

    # Step 3: Filter and combine
    # The spec requires keeping only entities, deadlines, topics, and emotion markers.

    final_extracted_data = {}

    # Add entities from both NER and LLM. NER is often more reliable for standard
    # entities, so we can prioritize it.
    final_extracted_data['entities'] = ner_entities
    if 'entity' in llm_extractions:
        # Avoid duplicating keys if NER already found them.
        # This simple logic can be expanded.
        final_extracted_data['entities']['llm_entity'] = llm_extractions['entity']

    # Add other required fields from the LLM output.
    if 'deadline' in llm_extractions and llm_extractions['deadline']:
        final_extracted_data['deadline'] = llm_extractions['deadline']

    if 'topic' in llm_extractions:
        final_extracted_data['topic'] = llm_extractions['topic']

    if 'emotion' in llm_extractions:
        final_extracted_data['emotion_markers'] = llm_extractions['emotion']

    return final_extracted_data
