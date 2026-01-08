# Memory Thread Services Package
"""Core services and cognitive components for Memory Thread"""

# Phase 8: Semantic + Symbolic Fusion
from memory_thread.services.reasoning.inference_engine import InferenceEngine
from memory_thread.services.reasoning.explainability_engine import ExplainabilityEngine
from memory_thread.services.reasoning.hybrid_reranker import HybridReranker

# Phase 9: Predictive World Model
from memory_thread.services.predictive_service import PredictiveService
from memory_thread.services.maintenance_suggester import MaintenanceSuggester
from memory_thread.services.autonomous_engine import AutonomousEngine
from memory_thread.services.feedback_service import FeedbackService

# Phase 10: Autonomic Cognition
from memory_thread.services.autonomic_controller import AutonomicController
from memory_thread.services.emergent_reasoner import EmergentReasoner
from memory_thread.services.meta_cognitive import MetaCognitiveEngine

__all__ = [
    # Reasoning
    'InferenceEngine',
    'ExplainabilityEngine', 
    'HybridReranker',
    # Predictive
    'PredictiveService',
    'MaintenanceSuggester',
    'AutonomousEngine',
    'FeedbackService',
    # Autonomic
    'AutonomicController',
    'EmergentReasoner',
    'MetaCognitiveEngine',
]
