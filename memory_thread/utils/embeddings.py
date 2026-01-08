"""
Memory Thread: Embeddings Utility
==================================
Generates semantic embeddings using sentence-transformers.
Uses all-MiniLM-L6-v2 (384 dimensions, fast, good quality).

Production Features:
- Lazy model loading
- Graceful fallback
- Fail-closed on errors
"""

from typing import List, Tuple, Union
from functools import lru_cache
import logging
import numpy as np

log = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2 dimension

_model = None
_model_available = True


def get_model():
    """Load embedding model with graceful error handling"""
    global _model, _model_available
    
    if _model is not None:
        return _model
    
    if not _model_available:
        raise RuntimeError("Embedding model previously failed to load")
    
    try:
        from sentence_transformers import SentenceTransformer
        log.info("Loading Embedding Model: all-MiniLM-L6-v2...")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        log.info("Embedding model loaded successfully")
        return _model
    except ImportError:
        log.error("sentence-transformers not installed. Run: pip install sentence-transformers")
        _model_available = False
        raise
    except Exception as e:
        log.error(f"Failed to load embedding model: {e}")
        _model_available = False
        raise


def generate_embeddings(texts: Union[str, List[str], Tuple[str, ...]]) -> List[List[float]]:
    """
    Generate embeddings for text(s).
    
    Fail-closed: No silent fallbacks. Caller handles exceptions.
    
    Args:
        texts: Single string, list of strings, or tuple of strings
        
    Returns:
        List of embeddings (each embedding is a list of floats)
    """
    model = get_model()
    
    # Normalize input
    if isinstance(texts, str):
        texts = [texts]
    elif isinstance(texts, tuple):
        texts = list(texts)
    
    if not texts:
        raise ValueError("Cannot generate embeddings for empty input")
    
    # Generate embeddings
    embeddings = model.encode(texts)
    
    # Validate output
    if len(embeddings) == 0:
        raise ValueError("Embedding model returned empty result")
    
    if len(embeddings) != len(texts):
        raise ValueError(f"Embedding count mismatch: {len(embeddings)} vs {len(texts)} texts")
    
    return embeddings.tolist()


def is_model_available() -> bool:
    """Check if embedding model can be loaded"""
    try:
        get_model()
        return True
    except Exception:
        return False


def get_zero_vector() -> List[float]:
    """Return a zero vector (for fallback/placeholder use)"""
    return [0.0] * EMBEDDING_DIMENSION

