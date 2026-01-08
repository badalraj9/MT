"""
Memory Thread: Inference Engine
================================
Phase 8.1: Semantic + Symbolic Fusion

This module implements the core inference engine that applies symbolic
reasoning rules to the knowledge graph. It supports:
- Pattern matching against graph relations
- Confidence calculation for inferred facts
- Idempotent rule application
- Complete inference traces for explainability

Performance Target: <10ms to apply 20 rules to 1000 entities
"""

import yaml
import uuid
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime
from pathlib import Path

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class RuleMatch:
    """Represents a successful pattern match"""
    rule_name: str
    bindings: Dict[str, str]  # Variable -> Entity ID mapping
    confidences: List[float]  # Confidence of each matched relation
    matched_relations: List[Tuple[str, str, str]]  # (from, to, type)


@dataclass
class InferenceResult:
    """Result of applying a single rule"""
    rule_name: str
    action: str  # 'create', 'boost', 'flag'
    source_entity: str
    target_entity: str
    relation_type: str
    confidence: float
    is_new: bool  # True if this created a new relation
    trace: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceTrace:
    """Complete trace of how a conclusion was reached"""
    conclusion: str
    rule_chain: List[str]
    source_facts: List[Tuple[str, str, str]]  # The facts that triggered inference
    confidence_breakdown: Dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# INFERENCE ENGINE
# ============================================================================

class InferenceEngine:
    """
    Production-grade inference engine for knowledge graph reasoning.
    
    Features:
    - Load rules from YAML configuration
    - Pattern matching with variable binding
    - Confidence propagation
    - Idempotent rule application
    - Full inference traces
    """
    
    def __init__(self, rule_config_path: Optional[str] = None):
        self.pg = PostgresClient()
        self.rules: Dict[str, List[Dict]] = {}
        self.settings: Dict[str, Any] = {}
        self._load_rules(rule_config_path)
        self._inference_cache: Set[str] = set()  # Prevent duplicate inferences
        
    def _load_rules(self, config_path: Optional[str] = None):
        """Load rules from YAML configuration"""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "rules" / "rule_library.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            self.settings = config.get('settings', {})
            
            # Load rules by category
            for category in ['hierarchical', 'inverse', 'temporal', 'social', 'contradiction', 'boosting']:
                self.rules[category] = config.get(category, [])
            
            total = sum(len(r) for r in self.rules.values())
            log.info(f"InferenceEngine: Loaded {total} rules from {config_path}")
        except Exception as e:
            log.error(f"Failed to load rules: {e}")
            self.rules = {}
    
    def get_all_rules(self) -> List[Dict]:
        """Get flattened list of all rules"""
        all_rules = []
        for category, rules in self.rules.items():
            for rule in rules:
                rule['category'] = category
                all_rules.append(rule)
        return all_rules
    
    # ========================================================================
    # PATTERN MATCHING
    # ========================================================================
    
    def _match_pattern(self, pattern: List[Dict], start_entity: Optional[str] = None) -> List[RuleMatch]:
        """
        Match a rule pattern against the knowledge graph.
        Returns all valid variable bindings.
        """
        matches = []
        
        # Get the first pattern element
        first_match = pattern[0].get('match', {})
        
        # Build SQL query to find matching relations
        with self.pg.get_cursor() as cur:
            # Start with first pattern
            from_var = first_match.get('from', '?X')
            to_var = first_match.get('to', '?Y')
            rel_type = first_match.get('relation')
            
            query = """
                SELECT source_entity_id, target_entity_id, relation_type, confidence
                FROM relations
                WHERE relation_type = %s
            """
            params = [rel_type]
            
            if start_entity and not from_var.startswith('?'):
                query += " AND source_entity_id = %s"
                params.append(start_entity)
            
            cur.execute(query, tuple(params))
            first_matches = cur.fetchall()
            
            # For each first-level match, try to complete the pattern
            for row in first_matches:
                src = row['source_entity_id'] if isinstance(row, dict) else row[0]
                tgt = row['target_entity_id'] if isinstance(row, dict) else row[1]
                conf = row['confidence'] if isinstance(row, dict) else row[3]
                
                bindings = {from_var: str(src), to_var: str(tgt)}
                confidences = [conf]
                matched_rels = [(str(src), str(tgt), rel_type)]
                
                # Try to match remaining patterns
                if len(pattern) == 1:
                    matches.append(RuleMatch(
                        rule_name="",
                        bindings=bindings,
                        confidences=confidences,
                        matched_relations=matched_rels
                    ))
                else:
                    # Multi-pattern matching
                    for subsequent in pattern[1:]:
                        if 'match' in subsequent:
                            sub_match = subsequent['match']
                            sub_from = sub_match.get('from', '?A')
                            sub_to = sub_match.get('to', '?B')
                            sub_rel = sub_match.get('relation')
                            
                            # Resolve variables
                            resolved_from = bindings.get(sub_from, sub_from)
                            resolved_to = bindings.get(sub_to, sub_to)
                            
                            # Query for matches
                            sub_query = "SELECT source_entity_id, target_entity_id, confidence FROM relations WHERE relation_type = %s"
                            sub_params = [sub_rel]
                            
                            if not resolved_from.startswith('?'):
                                sub_query += " AND source_entity_id = %s"
                                sub_params.append(resolved_from)
                            if not resolved_to.startswith('?'):
                                sub_query += " AND target_entity_id = %s"
                                sub_params.append(resolved_to)
                            
                            cur.execute(sub_query, tuple(sub_params))
                            sub_rows = cur.fetchall()
                            
                            for sub_row in sub_rows:
                                s_src = sub_row['source_entity_id'] if isinstance(sub_row, dict) else sub_row[0]
                                s_tgt = sub_row['target_entity_id'] if isinstance(sub_row, dict) else sub_row[1]
                                s_conf = sub_row['confidence'] if isinstance(sub_row, dict) else sub_row[2]
                                
                                new_bindings = bindings.copy()
                                new_bindings[sub_from] = str(s_src)
                                new_bindings[sub_to] = str(s_tgt)
                                
                                # Check constraints
                                if self._check_constraints(pattern, new_bindings):
                                    matches.append(RuleMatch(
                                        rule_name="",
                                        bindings=new_bindings,
                                        confidences=confidences + [s_conf],
                                        matched_relations=matched_rels + [(str(s_src), str(s_tgt), sub_rel)]
                                    ))
        
        return matches
    
    def _check_constraints(self, pattern: List[Dict], bindings: Dict[str, str]) -> bool:
        """Check if variable bindings satisfy all constraints"""
        for item in pattern:
            if 'constraint' in item:
                constraint = item['constraint']
                if 'not_equal' in constraint:
                    var = constraint.get('var', '')
                    other = constraint.get('not_equal', '')
                    if bindings.get(var) == bindings.get(other):
                        return False
        return True
    
    # ========================================================================
    # RULE EXECUTION
    # ========================================================================
    
    def apply_rule(self, rule: Dict, entity_id: Optional[str] = None) -> List[InferenceResult]:
        """Apply a single rule and return inference results"""
        results = []
        rule_name = rule.get('name', 'unknown')
        pattern = rule.get('pattern', [])
        action = rule.get('action', {})
        confidence_formula = rule.get('confidence_formula', '1.0')
        
        # Find pattern matches
        matches = self._match_pattern(pattern, entity_id)
        
        for match in matches:
            match.rule_name = rule_name
            
            # Execute action based on type
            if 'create' in action:
                result = self._execute_create(rule_name, action['create'], match, confidence_formula)
                if result:
                    results.append(result)
            elif 'boost' in action:
                result = self._execute_boost(rule_name, action['boost'], match, confidence_formula)
                if result:
                    results.append(result)
            elif 'flag' in action:
                result = self._execute_flag(rule_name, action['flag'], match)
                if result:
                    results.append(result)
        
        return results
    
    def _execute_create(self, rule_name: str, create_action: Dict, match: RuleMatch, 
                        confidence_formula: str) -> Optional[InferenceResult]:
        """Execute a 'create' action to add a new relation"""
        from_var = create_action.get('from', '')
        to_var = create_action.get('to', '')
        rel_type = create_action.get('relation', '')
        
        from_id = match.bindings.get(from_var)
        to_id = match.bindings.get(to_var)
        
        if not from_id or not to_id:
            return None
        
        # Calculate confidence
        confidence = self._calculate_confidence(confidence_formula, match.confidences)
        
        # Check minimum threshold
        min_threshold = self.settings.get('min_confidence_threshold', 0.3)
        if confidence < min_threshold:
            return None
        
        # Check idempotency (don't create duplicates)
        cache_key = f"{from_id}:{to_id}:{rel_type}"
        if cache_key in self._inference_cache:
            return None
        
        # Check if relation already exists
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT id FROM relations 
                WHERE source_entity_id = %s AND target_entity_id = %s AND relation_type = %s
            """, (from_id, to_id, rel_type))
            existing = cur.fetchone()
            
            if existing:
                self._inference_cache.add(cache_key)
                return InferenceResult(
                    rule_name=rule_name,
                    action='create',
                    source_entity=from_id,
                    target_entity=to_id,
                    relation_type=rel_type,
                    confidence=confidence,
                    is_new=False,
                    trace={'matched_relations': match.matched_relations}
                )
            
            # Create new inferred relation
            cur.execute("""
                INSERT INTO relations (source_entity_id, target_entity_id, relation_type, confidence, is_inferred, metadata)
                VALUES (%s, %s, %s, %s, TRUE, %s)
                RETURNING id
            """, (from_id, to_id, rel_type, confidence, 
                  f'{{"rule": "{rule_name}", "source_facts": {len(match.matched_relations)}}}'))
            
            self._inference_cache.add(cache_key)
            
            return InferenceResult(
                rule_name=rule_name,
                action='create',
                source_entity=from_id,
                target_entity=to_id,
                relation_type=rel_type,
                confidence=confidence,
                is_new=True,
                trace={'matched_relations': match.matched_relations, 'bindings': match.bindings}
            )
    
    def _execute_boost(self, rule_name: str, boost_action: Dict, match: RuleMatch,
                       confidence_formula: str) -> Optional[InferenceResult]:
        """Execute a 'boost' action to increase relation confidence"""
        from_var = boost_action.get('from', '')
        to_var = boost_action.get('to', '')
        rel_var = boost_action.get('relation', '')
        boost_field = boost_action.get('field', 'confidence')
        
        from_id = match.bindings.get(from_var)
        to_id = match.bindings.get(to_var)
        rel_type = match.bindings.get(rel_var, rel_var)  # Can be literal or variable
        
        if not from_id or not to_id:
            return None
        
        # Calculate boost amount
        new_confidence = self._calculate_confidence(confidence_formula, match.confidences)
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE relations 
                SET confidence = %s, last_confirmed = NOW()
                WHERE source_entity_id = %s AND target_entity_id = %s AND relation_type = %s
                RETURNING id
            """, (new_confidence, from_id, to_id, rel_type))
            
            result = cur.fetchone()
            if result:
                return InferenceResult(
                    rule_name=rule_name,
                    action='boost',
                    source_entity=from_id,
                    target_entity=to_id,
                    relation_type=rel_type,
                    confidence=new_confidence,
                    is_new=False,
                    trace={'boost_field': boost_field}
                )
        return None
    
    def _execute_flag(self, rule_name: str, flag_action: Dict, match: RuleMatch) -> Optional[InferenceResult]:
        """Execute a 'flag' action to report a conflict or issue"""
        entity_var = flag_action.get('entity', '')
        issue = flag_action.get('issue', 'unknown')
        details = flag_action.get('details', [])
        
        entity_id = match.bindings.get(entity_var)
        resolved_details = [match.bindings.get(d, d) for d in details]
        
        log.warning(f"CONFLICT DETECTED [{rule_name}]: Entity {entity_id} - {issue}: {resolved_details}")
        
        return InferenceResult(
            rule_name=rule_name,
            action='flag',
            source_entity=entity_id or '',
            target_entity='',
            relation_type=issue,
            confidence=1.0,
            is_new=True,
            trace={'issue': issue, 'details': resolved_details}
        )
    
    def _calculate_confidence(self, formula: str, confidences: List[float]) -> float:
        """Calculate confidence using the rule's formula"""
        try:
            # Build context for formula evaluation
            context = {
                'min': min,
                'max': max,
                'conf_1': confidences[0] if len(confidences) > 0 else 1.0,
                'conf_2': confidences[1] if len(confidences) > 1 else 1.0,
                'conf_3': confidences[2] if len(confidences) > 2 else 1.0,
                'base_conf': confidences[0] if confidences else 1.0,
                'source_count': len(confidences),
            }
            
            result = eval(formula, {"__builtins__": {}}, context)
            return max(0.0, min(1.0, float(result)))
        except Exception as e:
            log.warning(f"Confidence calculation failed: {e}, returning 0.5")
            return 0.5
    
    # ========================================================================
    # INFERENCE CYCLES
    # ========================================================================
    
    def run_inference_cycle(self, max_iterations: int = 3) -> Dict[str, Any]:
        """
        Run a complete inference cycle, applying all rules.
        Iterates until no new inferences are made or max_iterations reached.
        """
        start = time.perf_counter()
        self._inference_cache.clear()
        
        total_results = []
        iteration = 0
        
        for iteration in range(max_iterations):
            iter_results = []
            
            for rule in self.get_all_rules():
                results = self.apply_rule(rule)
                iter_results.extend(results)
            
            new_inferences = [r for r in iter_results if r.is_new and r.action == 'create']
            total_results.extend(iter_results)
            
            if not new_inferences:
                break  # Fixed point reached
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        summary = {
            'iterations': iteration + 1,
            'total_inferences': len(total_results),
            'new_relations': len([r for r in total_results if r.is_new and r.action == 'create']),
            'boosts': len([r for r in total_results if r.action == 'boost']),
            'conflicts': len([r for r in total_results if r.action == 'flag']),
            'elapsed_ms': round(elapsed_ms, 2),
            'rules_applied': len(self.get_all_rules())
        }
        
        log.info(f"Inference Cycle Complete: {summary}")
        return summary
    
    def get_inference_trace(self, entity_id: str) -> List[InferenceTrace]:
        """Get explanation chain for all inferred relations involving an entity"""
        traces = []
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT source_entity_id, target_entity_id, relation_type, confidence, metadata
                FROM relations
                WHERE is_inferred = TRUE 
                  AND (source_entity_id = %s OR target_entity_id = %s)
            """, (entity_id, entity_id))
            
            rows = cur.fetchall()
            
            for row in rows:
                src = row['source_entity_id'] if isinstance(row, dict) else row[0]
                tgt = row['target_entity_id'] if isinstance(row, dict) else row[1]
                rel = row['relation_type'] if isinstance(row, dict) else row[2]
                conf = row['confidence'] if isinstance(row, dict) else row[3]
                meta = row['metadata'] if isinstance(row, dict) else row[4]
                
                import json
                if isinstance(meta, str):
                    meta = json.loads(meta)
                
                traces.append(InferenceTrace(
                    conclusion=f"{src} -{rel}-> {tgt}",
                    rule_chain=[meta.get('rule', 'unknown')] if meta else [],
                    source_facts=[],  # Would need to query further
                    confidence_breakdown={'final': conf}
                ))
        
        return traces


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def run_inference(entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function to run inference"""
    engine = InferenceEngine()
    return engine.run_inference_cycle()


def explain_inference(entity_id: str) -> List[InferenceTrace]:
    """Convenience function to get inference explanation"""
    engine = InferenceEngine()
    return engine.get_inference_trace(entity_id)
