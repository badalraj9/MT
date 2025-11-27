import spacy
from functools import lru_cache

# It's efficient to load the model once and reuse it.
# We'll use the small English model for now.
# Note: The user will need to run `python -m spacy download en_core_web_sm`
nlp = spacy.load("en_core_web_sm")

@lru_cache(maxsize=1024)
def extract_entities(text: str) -> dict:
    """
    Extracts named entities from text using spaCy.
    Filters for specific entity types as per the extraction pipeline.
    """
    doc = nlp(text)
    entities = {
        "persons": [ent.text for ent in doc.ents if ent.label_ == "PERSON"],
        "orgs": [ent.text for ent in doc.ents if ent.label_ == "ORG"],
        "dates": [ent.text for ent in doc.ents if ent.label_ == "DATE"],
        "times": [ent.text for ent in doc.ents if ent.label_ == "TIME"],
        "locations": [ent.text for ent in doc.ents if ent.label_ == "GPE"],
    }
    # A 'tasks' entity is mentioned but not a standard spaCy label.
    # For now, we will leave it empty as a placeholder.
    entities["tasks"] = []

    return entities
