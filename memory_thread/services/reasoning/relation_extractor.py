import re
from typing import List, Dict, Tuple

class RelationExtractor:
    """
    Extracts structured relationships from text using regex patterns and heuristics.
    """

    PATTERNS = [
        (r"(?P<source>.+?) works at (?P<target>.+)", "works_at"),
        (r"(?P<source>.+?) is employed by (?P<target>.+)", "works_at"),
        (r"(?P<source>.+?) lives in (?P<target>.+)", "located_in"),
        (r"(?P<source>.+?) is located in (?P<target>.+)", "located_in"),
        (r"(?P<source>.+?) is a part of (?P<target>.+)", "part_of"),
        (r"(?P<source>.+?) knows (?P<target>.+)", "knows"),
        (r"(?P<source>.+?) is friends with (?P<target>.+)", "friend_of"),
    ]

    def extract_relations(self, text: str) -> List[Dict]:
        """
        Returns a list of relation dicts:
        [{'source': 'Alice', 'target': 'Google', 'type': 'works_at'}]
        """
        found = []
        for pattern, rel_type in self.PATTERNS:
            # Case insensitive search
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                source = match.group("source").strip()
                target = match.group("target").strip()

                # Basic cleanup
                if len(source) > 50 or len(target) > 50:
                    continue # Ignore long matches which are likely false positives

                found.append({
                    "source_name": source,
                    "target_name": target,
                    "relation_type": rel_type,
                    "confidence": 0.8 # Heuristic confidence
                })
        return found
