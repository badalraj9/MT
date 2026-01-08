"""
Memory Thread: Feedback Service
================================
Phase 9.4: Predictive World Model

Closed-loop learning system that:
1. Tracks prediction accuracy
2. Tracks suggestion acceptance rates
3. Triggers model retraining when performance degrades
4. Improves over time

Target: 10% accuracy improvement over 3 months
"""

import logging
import json
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from collections import defaultdict

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# ============================================================================
# DATA CLASSES
# ============================================================================

class FeedbackType(Enum):
    PREDICTION = "prediction"
    SUGGESTION = "suggestion"
    AUTONOMOUS = "autonomous"


@dataclass
class FeedbackRecord:
    """A single feedback record"""
    id: str
    feedback_type: FeedbackType
    entity_id: str
    predicted_value: Any
    actual_value: Any
    error: float  # Absolute error or 0/1 for binary
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics"""
    total_predictions: int
    mean_absolute_error: float
    mean_squared_error: float
    accuracy: float  # For classification
    acceptance_rate: float  # For suggestions
    period_start: datetime
    period_end: datetime


# ============================================================================
# FEEDBACK SERVICE
# ============================================================================

class FeedbackService:
    """
    Tracks prediction accuracy and suggestion acceptance.
    Enables continuous improvement of the predictive system.
    """
    
    def __init__(self):
        self.pg = PostgresClient()
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create feedback tracking tables"""
        with self.pg.get_cursor() as cur:
            # Predictions tracking
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prediction_feedback (
                    id VARCHAR(64) PRIMARY KEY,
                    feedback_type VARCHAR(32),
                    entity_id VARCHAR(36),
                    metric VARCHAR(64),
                    predicted_value JSONB,
                    actual_value JSONB,
                    error FLOAT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    metadata JSONB
                )
            """)
            
            # Suggestion feedback
            cur.execute("""
                CREATE TABLE IF NOT EXISTS suggestion_feedback (
                    id VARCHAR(64) PRIMARY KEY,
                    suggestion_id VARCHAR(64),
                    accepted BOOLEAN,
                    feedback_reason TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Model performance history
            cur.execute("""
                CREATE TABLE IF NOT EXISTS model_performance (
                    id SERIAL PRIMARY KEY,
                    model_type VARCHAR(64),
                    period_start TIMESTAMP,
                    period_end TIMESTAMP,
                    mae FLOAT,
                    mse FLOAT,
                    accuracy FLOAT,
                    sample_count INT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
    
    # ========================================================================
    # PREDICTION FEEDBACK
    # ========================================================================
    
    def record_prediction(self, prediction_id: str, entity_id: str, 
                          metric: str, predicted: Any, actual: Any):
        """Record a prediction outcome for feedback"""
        # Calculate error
        try:
            if isinstance(predicted, (int, float)) and isinstance(actual, (int, float)):
                error = abs(float(predicted) - float(actual))
            elif predicted == actual:
                error = 0.0
            else:
                error = 1.0  # Binary error for non-numeric
        except:
            error = 1.0
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO prediction_feedback 
                (id, feedback_type, entity_id, metric, predicted_value, actual_value, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    actual_value = EXCLUDED.actual_value,
                    error = EXCLUDED.error
            """, (
                prediction_id,
                FeedbackType.PREDICTION.value,
                entity_id,
                metric,
                json.dumps(predicted),
                json.dumps(actual),
                error
            ))
        
        log.debug(f"Recorded prediction feedback: {prediction_id}, error={error:.2f}")
    
    def record_suggestion_feedback(self, suggestion_id: str, accepted: bool, 
                                   reason: str = ""):
        """Record whether a suggestion was accepted or rejected"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO suggestion_feedback (id, suggestion_id, accepted, feedback_reason)
                VALUES (%s, %s, %s, %s)
            """, (
                f"fb-{suggestion_id}",
                suggestion_id,
                accepted,
                reason
            ))
        
        log.debug(f"Recorded suggestion feedback: {suggestion_id}, accepted={accepted}")
    
    # ========================================================================
    # PERFORMANCE METRICS
    # ========================================================================
    
    def get_prediction_metrics(self, days: int = 7) -> PerformanceMetrics:
        """Calculate prediction performance over recent period"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    AVG(error) as mae,
                    AVG(error * error) as mse,
                    SUM(CASE WHEN error < 0.1 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) as accuracy
                FROM prediction_feedback
                WHERE created_at >= %s
            """, (cutoff,))
            
            row = cur.fetchone()
            
            if row:
                total = row[0] if row[0] else 0
                mae = row[1] if row[1] else 0.0
                mse = row[2] if row[2] else 0.0
                accuracy = row[3] if row[3] else 0.0
            else:
                total, mae, mse, accuracy = 0, 0.0, 0.0, 0.0
        
        return PerformanceMetrics(
            total_predictions=total,
            mean_absolute_error=round(mae, 4),
            mean_squared_error=round(mse, 4),
            accuracy=round(accuracy, 4),
            acceptance_rate=0.0,  # Filled separately
            period_start=cutoff,
            period_end=datetime.utcnow()
        )
    
    def get_suggestion_acceptance_rate(self, days: int = 30) -> float:
        """Calculate suggestion acceptance rate"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN accepted THEN 1 ELSE 0 END) as accepted_count
                FROM suggestion_feedback
                WHERE created_at >= %s
            """, (cutoff,))
            
            row = cur.fetchone()
            
            if row and row[0] and row[0] > 0:
                return round(row[1] / row[0], 4)
            return 0.0
    
    def save_performance_snapshot(self, model_type: str = "combined"):
        """Save current performance metrics for historical tracking"""
        metrics = self.get_prediction_metrics(days=7)
        acceptance = self.get_suggestion_acceptance_rate(days=7)
        
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO model_performance 
                (model_type, period_start, period_end, mae, mse, accuracy, sample_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                model_type,
                metrics.period_start,
                metrics.period_end,
                metrics.mean_absolute_error,
                metrics.mean_squared_error,
                metrics.accuracy,
                metrics.total_predictions
            ))
        
        log.info(f"Saved performance snapshot: MAE={metrics.mean_absolute_error:.4f}, Acc={metrics.accuracy:.2%}")
    
    # ========================================================================
    # RETRAINING TRIGGER
    # ========================================================================
    
    def should_retrain(self, mae_threshold: float = 0.3) -> Tuple[bool, str]:
        """Determine if model retraining is needed"""
        metrics = self.get_prediction_metrics(days=7)
        
        # Check if we have enough data
        if metrics.total_predictions < 10:
            return False, "Insufficient data (< 10 predictions)"
        
        # Check MAE threshold
        if metrics.mean_absolute_error > mae_threshold:
            return True, f"MAE ({metrics.mean_absolute_error:.2f}) exceeds threshold ({mae_threshold})"
        
        # Check accuracy (if applicable)
        if metrics.accuracy < 0.7 and metrics.total_predictions > 20:
            return True, f"Accuracy ({metrics.accuracy:.2%}) below 70%"
        
        # Check if acceptance rate is low
        acceptance = self.get_suggestion_acceptance_rate(days=30)
        if acceptance < 0.5 and acceptance > 0:
            return True, f"Suggestion acceptance rate ({acceptance:.2%}) below 50%"
        
        return False, "Performance within acceptable range"
    
    def get_performance_trend(self, periods: int = 4) -> List[Dict]:
        """Get recent performance trend"""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT model_type, period_start, period_end, mae, accuracy, sample_count
                FROM model_performance
                ORDER BY created_at DESC
                LIMIT %s
            """, (periods,))
            
            rows = cur.fetchall()
            
            trend = []
            for row in rows:
                if isinstance(row, dict):
                    trend.append({
                        'period_end': row['period_end'].isoformat() if row['period_end'] else None,
                        'mae': row['mae'],
                        'accuracy': row['accuracy'],
                        'samples': row['sample_count']
                    })
            
            return list(reversed(trend))  # Oldest first
    
    # ========================================================================
    # MODEL RETRAINING (STUB)
    # ========================================================================
    
    def trigger_retraining(self) -> Dict[str, Any]:
        """Trigger model retraining pipeline"""
        log.info("Triggering model retraining...")
        
        # In production, this would:
        # 1. Export recent data
        # 2. Retrain models
        # 3. Validate new models
        # 4. Hot-swap if improved
        
        # For now, just log and return status
        should_retrain, reason = self.should_retrain()
        
        return {
            'triggered': should_retrain,
            'reason': reason,
            'status': 'queued' if should_retrain else 'not_needed',
            'timestamp': datetime.utcnow().isoformat()
        }


# ============================================================================
# FEEDBACK LOOP RUNNER
# ============================================================================

class FeedbackLoop:
    """
    Orchestrates the complete feedback loop:
    1. Collect feedback from predictions
    2. Calculate performance metrics
    3. Determine if retraining needed
    4. Trigger retraining if necessary
    """
    
    def __init__(self):
        self.feedback = FeedbackService()
        self._last_snapshot = None
    
    def run_daily(self) -> Dict[str, Any]:
        """Run daily feedback loop tasks"""
        log.info("Running daily feedback loop...")
        
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'tasks': {}
        }
        
        # 1. Save performance snapshot
        self.feedback.save_performance_snapshot()
        results['tasks']['snapshot'] = 'saved'
        
        # 2. Check if retraining needed
        should_retrain, reason = self.feedback.should_retrain()
        results['tasks']['retraining_check'] = {
            'needed': should_retrain,
            'reason': reason
        }
        
        # 3. Get performance trend
        trend = self.feedback.get_performance_trend()
        results['performance_trend'] = trend
        
        # 4. Trigger retraining if needed
        if should_retrain:
            retrain_result = self.feedback.trigger_retraining()
            results['tasks']['retraining'] = retrain_result
        
        log.info(f"Feedback loop complete: {results}")
        return results
    
    def run_weekly(self) -> Dict[str, Any]:
        """Run weekly feedback loop tasks (more intensive)"""
        log.info("Running weekly feedback loop...")
        
        # Daily tasks first
        daily_results = self.run_daily()
        
        # Weekly-specific tasks
        weekly_results = {
            **daily_results,
            'weekly_tasks': {}
        }
        
        # Force model evaluation
        metrics = self.feedback.get_prediction_metrics(days=30)
        weekly_results['weekly_tasks']['30_day_metrics'] = {
            'total_predictions': metrics.total_predictions,
            'mae': metrics.mean_absolute_error,
            'accuracy': metrics.accuracy
        }
        
        # Get suggestion acceptance rate
        acceptance = self.feedback.get_suggestion_acceptance_rate(days=30)
        weekly_results['weekly_tasks']['suggestion_acceptance'] = acceptance
        
        return weekly_results


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def record_prediction_outcome(prediction_id: str, entity_id: str,
                              metric: str, predicted: Any, actual: Any):
    """Quick recording of prediction outcome"""
    FeedbackService().record_prediction(prediction_id, entity_id, metric, predicted, actual)


def get_model_status() -> Dict[str, Any]:
    """Get current model status and performance"""
    service = FeedbackService()
    metrics = service.get_prediction_metrics()
    should_retrain, reason = service.should_retrain()
    
    return {
        'predictions_last_7d': metrics.total_predictions,
        'mae': metrics.mean_absolute_error,
        'accuracy': metrics.accuracy,
        'retrain_needed': should_retrain,
        'retrain_reason': reason
    }
