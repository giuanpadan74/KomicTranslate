#!/usr/bin/env python3
"""
Modulo di logging automatico per KomicTranslate.
Fornisce funzionalità di logging centralizzate per tutte le operazioni.
"""

from .auto_logger import (
    log_api_error,
    log_ocr_error,
    log_translation_error,
    log_textblock_error,
    log_encoding_error,
    log_performance_warning,
    log_fallback_activation,
    log_batch_operation
)

__all__ = [
    'log_api_error',
    'log_ocr_error',
    'log_translation_error',
    'log_textblock_error',
    'log_encoding_error',
    'log_performance_warning',
    'log_fallback_activation',
    'log_batch_operation'
]