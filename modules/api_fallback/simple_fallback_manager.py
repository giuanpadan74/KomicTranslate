#!/usr/bin/env python3
"""Fallback verso un engine alternativo (usato da pipeline.py per DocTR).

Prima esisteva anche la rotazione delle API key, eliminata insieme allo
strato LLM: questo manager ora esegue solo la funzione di fallback.

Nota sul bug corretto: pipeline.py chiama
    execute_with_fallback(func, FallbackReason.QUOTA_EXCEEDED)
mentre la firma precedente era
    execute_with_fallback(api_call_func, operation_name='api_call')
e inoltre chiamava api_call_func(api_key) mentre la funzione di pipeline non
accetta argomenti, e con fallback_engine=None la funzione non veniva mai
eseguita. Il fallback DocTR quindi non ha mai girato.
"""
import logging
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass

from .error_detector import ErrorType, QuotaErrorDetector

logger = logging.getLogger('api_fallback.simple_manager')


class FallbackReason(Enum):
    """Motivi per cui viene attivato il fallback."""
    QUOTA_EXCEEDED = "quota_exceeded"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    UNKNOWN_ERROR = "unknown_error"
    NO_ERROR = "no_error"

    @classmethod
    def from_error_type(cls, error_type: ErrorType) -> 'FallbackReason':
        if error_type == ErrorType.QUOTA_EXCEEDED:
            return cls.QUOTA_EXCEEDED
        if error_type == ErrorType.RATE_LIMIT:
            return cls.RATE_LIMITED
        if error_type == ErrorType.AUTH_ERROR:
            return cls.AUTH_ERROR
        if error_type == ErrorType.NETWORK_ERROR:
            return cls.NETWORK_ERROR
        if error_type == ErrorType.SERVER_ERROR:
            return cls.SERVER_ERROR
        return cls.UNKNOWN_ERROR


@dataclass
class SimpleFallbackResult:
    """Esito di un tentativo di fallback."""
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    fallback_reason: Optional[FallbackReason] = None
    attempts_made: int = 0
    keys_used: Optional[List[str]] = None


class SimpleFallbackManager:
    """Esegue un engine alternativo quando quello primario fallisce."""

    def __init__(self, provider: str = 'default', api_keys: List[str] = None,
                 max_attempts: int = 3, fallback_engine=None):
        self.provider = provider
        self.api_keys = api_keys or []
        self.max_attempts = max_attempts
        # fallback_engine puo' essere una callable: e' l'engine alternativo
        # (DocTR) da usare quando il primario solleva QuotaExhaustedException.
        self.fallback_engine = fallback_engine
        self.error_detector = QuotaErrorDetector()

        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0

    def execute_with_fallback(self, func: Callable[[], Any],
                              reason: FallbackReason = FallbackReason.UNKNOWN_ERROR,
                              operation_name: str = "fallback") -> SimpleFallbackResult:
        """Esegue func(), oppure il fallback_engine se func() fallisce.

        Firma compatibile con le chiamate di pipeline.py:
            execute_with_fallback(func, FallbackReason.QUOTA_EXCEEDED)
        """
        self.total_calls += 1
        reason = self._coerce_reason(reason, operation_name)

        try:
            result = func()
            self.successful_calls += 1
            return SimpleFallbackResult(
                success=True, result=result, attempts_made=1,
                fallback_reason=reason, keys_used=[],
            )
        except Exception as primary_error:
            logger.warning(
                f"[FALLBACK] {operation_name}: funzione primaria fallita "
                f"({primary_error}), tento il fallback"
            )
            return self._run_fallback_engine(primary_error, reason, operation_name)

    def _run_fallback_engine(self, primary_error: Exception, reason: FallbackReason,
                             operation_name: str) -> SimpleFallbackResult:
        """Usa fallback_engine se disponibile, altrimenti riporta l'errore originale."""
        if self.fallback_engine is None:
            self.failed_calls += 1
            logger.error(
                f"[FALLBACK] {operation_name}: nessun engine di fallback configurato"
            )
            return SimpleFallbackResult(
                success=False, error=primary_error, fallback_reason=reason,
                attempts_made=0, keys_used=[],
            )

        try:
            result = self.fallback_engine()
            self.successful_calls += 1
            logger.info(f"[FALLBACK] {operation_name}: fallback completato")
            return SimpleFallbackResult(
                success=True, result=result, fallback_reason=reason,
                attempts_made=1, keys_used=[],
            )
        except Exception as fallback_error:
            self.failed_calls += 1
            error_info = self.error_detector.detect_error(
                str(fallback_error), provider=self.provider
            )
            logger.error(
                f"[FALLBACK] {operation_name}: anche il fallback e' fallito "
                f"({fallback_error})"
            )
            return SimpleFallbackResult(
                success=False, error=fallback_error,
                fallback_reason=FallbackReason.from_error_type(error_info.error_type),
                attempts_made=1, keys_used=[],
            )

    def _coerce_reason(self, reason, operation_name: str) -> FallbackReason:
        """Normalizza il 2' argomento, che arriva come FallbackReason o stringa."""
        if isinstance(reason, FallbackReason):
            return reason
        if isinstance(reason, str):
            try:
                return FallbackReason(reason)
            except ValueError:
                return FallbackReason.UNKNOWN_ERROR
        # chiamata all-inclusive in stile api-key (operation_name come 2' arg)
        if isinstance(reason, str) and operation_name != "fallback":
            return FallbackReason.UNKNOWN_ERROR
        return FallbackReason.UNKNOWN_ERROR

    def get_stats(self) -> Dict[str, Any]:
        success_rate = 0.0
        if self.total_calls > 0:
            success_rate = self.successful_calls / self.total_calls
        return {
            'provider': self.provider,
            'total_calls': self.total_calls,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'success_rate': success_rate,
            'max_attempts': self.max_attempts,
        }

    def reset_stats(self):
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0

    def is_key_available(self) -> bool:
        """Deprecato: senza API key questo e' sempre False."""
        return False

    def get_next_available_key(self) -> Optional[str]:
        """Deprecato: la rotazione delle API key non esiste piu'."""
        return None
