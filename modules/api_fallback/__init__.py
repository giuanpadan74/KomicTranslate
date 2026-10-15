"""Fallback verso un engine alternativo (usato da pipeline.py per DocTR).

Con la rimozione dello strato LLM questo package non gestisce piu' la
rotazione delle API key: resta solo il fallback dell'OCR locale verso
DocTR, piu' il rilevamento del tipo di errore che distingue "quota
esaurita" da "errore transitorio".
"""

from .error_detector import QuotaErrorDetector
from .simple_fallback_manager import SimpleFallbackManager, FallbackReason, SimpleFallbackResult

__all__ = [
    'QuotaErrorDetector',
    'SimpleFallbackManager',
    'FallbackReason',
    'SimpleFallbackResult',
]