"""
Memory Thread: Demo Data Loader
================================
Phase 11.3: Sample data for investor demo

Creates a curated dataset demonstrating:
- Multiple entity types
- Rich relationships
- Temporal patterns
- Inference opportunities

Usage: python -m memory_thread.demo.load_demo_data
"""

import uuid
import json
from datetime import datetime, timedelta

# Demo entities with narrative structure
DEMO_ENTITIES = [
    # === PEOPLE ===
    {
        "id": "person-alice-001",
        "type": "person",
        "name": "Alice Chen",
        "data": {
            "role": "CEO",
            "company": "TechCorp",
            "location": "San Francisco",
            "expertise": ["AI", "Product Strategy"],
            "linkedin": "alice-chen-ceo"
        }
    },
    {
        "id": "person-bob-002",
        "type": "person",
        "name": "Bob Martinez",
        "data": {
            "role": "CTO",
            "company": "TechCorp",
            "location": "San Francisco",
            "expertise": ["ML Infrastructure", "Distributed Systems"],
            "reports_to": "alice-chen-ceo"
        }
    },
    {
        "id": "person-carol-003",
        "type": "person",
        "name": "Carol Johnson",
        "data": {
            "role": "VP Engineering",
            "company": "DataFlow Inc",
            "location": "New York",
            "expertise": ["Data Pipelines", "Real-time Processing"]
        }
    },
    
    # === ORGANIZATIONS ===
    {
        "id": "org-techcorp-001",
        "type": "organization",
        "name": "TechCorp",
        "data": {
            "industry": "Enterprise AI",
            "founded": 2019,
            "headquarters": "San Francisco",
            "employees": 150,
            "valuation_millions": 250,
            "investors": ["Sequoia", "a16z"]
        }
    },
    {
        "id": "org-dataflow-002",
        "type": "organization",
        "name": "DataFlow Inc",
        "data": {
            "industry": "Data Infrastructure",
            "founded": 2018,
            "headquarters": "New York",
            "employees": 200,
            "valuation_millions": 400
        }
    },
    
    # === PLACES ===
    {
        "id": "place-sf-001",
        "type": "place",
        "name": "San Francisco",
        "data": {
            "country": "USA",
            "state": "California",
            "tech_hub": True,
            "population_millions": 0.87
        }
    },
    {
        "id": "place-nyc-002",
        "type": "place",
        "name": "New York",
        "data": {
            "country": "USA",
            "state": "New York",
            "tech_hub": True,
            "population_millions": 8.3
        }
    },
    
    # === CONCEPTS ===
    {
        "id": "concept-ai-001",
        "type": "concept",
        "name": "Artificial Intelligence",
        "data": {
            "category": "Technology",
            "related": ["Machine Learning", "Deep Learning", "NLP"],
            "maturity": "growth"
        }
    },
    {
        "id": "concept-rag-002",
        "type": "concept",
        "name": "Retrieval Augmented Generation",
        "data": {
            "category": "AI Pattern",
            "parent": "Artificial Intelligence",
            "trend": "hot",
            "adoption": "early_majority"
        }
    },
    
    # === EVENTS ===
    {
        "id": "event-funding-001",
        "type": "event",
        "name": "TechCorp Series B",
        "data": {
            "date": "2024-06-15",
            "amount_millions": 50,
            "lead_investor": "Sequoia",
            "company": "TechCorp",
            "valuation_post": 250
        }
    },
    {
        "id": "event-partnership-002",
        "type": "event",
        "name": "TechCorp-DataFlow Partnership",
        "data": {
            "date": "2024-09-01",
            "type": "strategic_partnership",
            "parties": ["TechCorp", "DataFlow Inc"],
            "focus": "AI-powered data pipelines"
        }
    }
]

# Demo relationships (for inference demonstrations)
DEMO_RELATIONS = [
    # Work relationships
    ("person-alice-001", "works_at", "org-techcorp-001", 0.99),
    ("person-bob-002", "works_at", "org-techcorp-001", 0.99),
    ("person-carol-003", "works_at", "org-dataflow-002", 0.99),
    
    # Location relationships
    ("person-alice-001", "located_in", "place-sf-001", 0.95),
    ("person-bob-002", "located_in", "place-sf-001", 0.95),
    ("org-techcorp-001", "headquartered_in", "place-sf-001", 0.99),
    ("org-dataflow-002", "headquartered_in", "place-nyc-002", 0.99),
    
    # Expertise relationships
    ("person-alice-001", "expert_in", "concept-ai-001", 0.85),
    ("org-techcorp-001", "focuses_on", "concept-rag-002", 0.90),
    
    # Organizational hierarchy
    ("person-bob-002", "reports_to", "person-alice-001", 0.99),
    
    # Event relationships
    ("event-funding-001", "involves", "org-techcorp-001", 0.99),
    ("event-partnership-002", "involves", "org-techcorp-001", 0.99),
    ("event-partnership-002", "involves", "org-dataflow-002", 0.99),
    
    # Social (inferred - for demo of inference)
    ("person-alice-001", "knows", "person-carol-003", 0.70),  # From partnership
]

# Demo events (temporal data for predictions)
DEMO_EVENTS = [
    # TechCorp growth metrics
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "employees", "value": 50, "days_ago": 365},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "employees", "value": 80, "days_ago": 270},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "employees", "value": 100, "days_ago": 180},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "employees", "value": 130, "days_ago": 90},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "employees", "value": 150, "days_ago": 0},
    
    # Revenue growth
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "arr_millions", "value": 2, "days_ago": 365},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "arr_millions", "value": 5, "days_ago": 270},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "arr_millions", "value": 10, "days_ago": 180},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "arr_millions", "value": 18, "days_ago": 90},
    {"entity": "org-techcorp-001", "action": "metric_update", "metric": "arr_millions", "value": 25, "days_ago": 0},
]


def generate_demo_sql():
    """Generate SQL statements for demo data"""
    sql_statements = []
    
    # Entities
    for entity in DEMO_ENTITIES:
        sql = f"""
INSERT INTO entities (id, entity_type, name, metadata, created_at) VALUES (
    '{entity['id']}',
    '{entity['type']}',
    '{entity['name']}',
    '{json.dumps(entity['data'])}',
    NOW()
) ON CONFLICT (id) DO UPDATE SET metadata = EXCLUDED.metadata;
"""
        sql_statements.append(sql)
    
    # Relations
    for source, rel_type, target, conf in DEMO_RELATIONS:
        sql = f"""
INSERT INTO relations (id, source_entity_id, target_entity_id, relation_type, confidence, created_at)
VALUES (
    '{uuid.uuid4()}',
    '{source}',
    '{target}',
    '{rel_type}',
    {conf},
    NOW()
) ON CONFLICT DO NOTHING;
"""
        sql_statements.append(sql)
    
    # Events
    for evt in DEMO_EVENTS:
        event_time = (datetime.utcnow() - timedelta(days=evt['days_ago'])).isoformat()
        sql = f"""
INSERT INTO events (id, object_id, action, delta, timestamp)
VALUES (
    '{uuid.uuid4()}',
    '{evt['entity']}',
    '{evt['action']}',
    '{json.dumps({evt['metric']: evt['value']})}',
    '{event_time}'
);
"""
        sql_statements.append(sql)
    
    return "\n".join(sql_statements)


def load_demo_data():
    """Load demo data into database"""
    from memory_thread.db.postgres_client import PostgresClient
    
    pg = PostgresClient()
    sql = generate_demo_sql()
    
    with pg.get_cursor() as cur:
        cur.execute(sql)
    
    print(f"✓ Loaded {len(DEMO_ENTITIES)} entities")
    print(f"✓ Loaded {len(DEMO_RELATIONS)} relations")
    print(f"✓ Loaded {len(DEMO_EVENTS)} events")
    print("\nDemo data ready!")


def print_demo_sql():
    """Print SQL for manual execution"""
    print(generate_demo_sql())


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--sql":
        print_demo_sql()
    else:
        load_demo_data()
