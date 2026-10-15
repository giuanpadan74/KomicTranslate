"""Rilevatore di errori per il sistema di fallback delle API keys.

Questo modulo fornisce funzionalità per rilevare e classificare diversi tipi di errori
che possono verificarsi durante le chiamate API, inclusi errori di quota, rate limiting
e autenticazione.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
from dataclasses import dataclass
from .config import FALLBACK_CONFIG, PROVIDER_CONFIG

# Configurazione del logger
logger = logging.getLogger('api_fallback.error_detector')

class ErrorType(Enum):
    """Tipi di errori rilevabili dal sistema."""
    QUOTA_EXCEEDED = "quota_exceeded"
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    UNKNOWN_ERROR = "unknown_error"
    NO_ERROR = "no_error"

class ErrorSeverity(Enum):
    """Livelli di gravità degli errori."""
    LOW = "low"          # Errore temporaneo, retry immediato possibile
    MEDIUM = "medium"    # Errore che richiede cooldown breve
    HIGH = "high"        # Errore che richiede cooldown lungo
    CRITICAL = "critical" # Errore che richiede intervento manuale

@dataclass
class ErrorInfo:
    """Informazioni dettagliate su un errore rilevato."""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    provider: Optional[str] = None
    status_code: Optional[int] = None
    retry_after: Optional[int] = None
    suggested_cooldown: Optional[int] = None
    is_recoverable: bool = True
    metadata: Optional[Dict] = None

class QuotaErrorDetector:
    """Rilevatore principale per errori di quota e altri tipi di errori API."""
    
    def __init__(self):
        """Inizializza il rilevatore di errori."""
        self.quota_patterns = self._compile_patterns(FALLBACK_CONFIG['quota_error_patterns'])
        self.rate_limit_patterns = self._compile_patterns(FALLBACK_CONFIG['rate_limit_patterns'])
        self.auth_patterns = self._compile_patterns(FALLBACK_CONFIG['auth_error_patterns'])
        
        # Compila i pattern specifici per provider
        self.provider_patterns = {}
        for provider, config in PROVIDER_CONFIG.items():
            if 'specific_error_patterns' in config:
                self.provider_patterns[provider] = self._compile_patterns(
                    config['specific_error_patterns']
                )
    
    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """Compila una lista di pattern regex.
        
        Args:
            patterns: Lista di pattern regex come stringhe
            
        Returns:
            Lista di pattern regex compilati
        """
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Pattern regex non valido '{pattern}': {e}")
        return compiled
    
    def detect_error(self, 
                    error_message: str = "", 
                    status_code: Optional[int] = None,
                    response_headers: Optional[Dict[str, str]] = None,
                    provider: Optional[str] = None,
                    exception: Optional[Exception] = None) -> ErrorInfo:
        """Rileva e classifica un errore basandosi sui parametri forniti.
        
        Args:
            error_message: Messaggio di errore da analizzare
            status_code: Codice di stato HTTP
            response_headers: Headers della risposta HTTP
            provider: Nome del provider API
            exception: Eccezione originale se disponibile
            
        Returns:
            ErrorInfo con i dettagli dell'errore rilevato
        """
        # Normalizza il messaggio di errore
        normalized_message = self._normalize_error_message(error_message, exception)
        
        # Rileva il tipo di errore
        error_type = self._detect_error_type(
            normalized_message, status_code, provider
        )
        
        # Determina la gravità
        severity = self._determine_severity(error_type, status_code, provider)
        
        # Estrai informazioni aggiuntive
        retry_after = self._extract_retry_after(response_headers)
        suggested_cooldown = self._calculate_suggested_cooldown(
            error_type, provider, retry_after
        )
        
        # Determina se l'errore è recuperabile
        is_recoverable = self._is_recoverable(error_type, status_code)
        
        # Crea metadata aggiuntivi
        metadata = {
            'original_message': error_message,
            'normalized_message': normalized_message,
            'detection_timestamp': self._get_timestamp(),
            'provider_config': PROVIDER_CONFIG.get(provider, {}) if provider else None
        }
        
        if exception:
            metadata['exception_type'] = type(exception).__name__
        
        return ErrorInfo(
            error_type=error_type,
            severity=severity,
            message=normalized_message,
            provider=provider,
            status_code=status_code,
            retry_after=retry_after,
            suggested_cooldown=suggested_cooldown,
            is_recoverable=is_recoverable,
            metadata=metadata
        )
    
    def _normalize_error_message(self, 
                               error_message: str, 
                               exception: Optional[Exception] = None) -> str:
        """Normalizza il messaggio di errore per l'analisi.
        
        Args:
            error_message: Messaggio di errore originale
            exception: Eccezione originale se disponibile
            
        Returns:
            Messaggio di errore normalizzato
        """
        # Combina messaggio di errore ed eccezione
        combined_message = error_message
        if exception:
            combined_message += f" {str(exception)}"
        
        # Normalizza il testo
        normalized = combined_message.lower().strip()
        
        # Rimuovi caratteri speciali e normalizza spazi
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized
    
    def _detect_error_type(self, 
                          message: str, 
                          status_code: Optional[int], 
                          provider: Optional[str]) -> ErrorType:
        """Rileva il tipo di errore basandosi sul messaggio e codice di stato.
        
        Args:
            message: Messaggio di errore normalizzato
            status_code: Codice di stato HTTP
            provider: Nome del provider
            
        Returns:
            Tipo di errore rilevato
        """
        # Controlla prima i pattern specifici del provider
        if provider and provider in self.provider_patterns:
            for pattern in self.provider_patterns[provider]:
                if pattern.search(message):
                    # Determina il tipo basandosi sul provider e pattern
                    return self._classify_provider_error(provider, message, status_code)
        
        # Controlla i codici di stato HTTP
        if status_code:
            if status_code == 429:
                return ErrorType.RATE_LIMIT
            elif status_code in [401, 403]:
                # Distingui tra errori di auth e quota basandosi sul messaggio
                if self._matches_patterns(message, self.quota_patterns):
                    return ErrorType.QUOTA_EXCEEDED
                return ErrorType.AUTH_ERROR
            elif status_code in [402, 456]:  # Payment required, quota exceeded
                return ErrorType.QUOTA_EXCEEDED
            elif 500 <= status_code < 600:
                return ErrorType.SERVER_ERROR
        
        # Controlla i pattern di errore generici
        if self._matches_patterns(message, self.quota_patterns):
            return ErrorType.QUOTA_EXCEEDED
        
        if self._matches_patterns(message, self.rate_limit_patterns):
            return ErrorType.RATE_LIMIT
        
        if self._matches_patterns(message, self.auth_patterns):
            return ErrorType.AUTH_ERROR
        
        # Controlla errori di rete
        network_keywords = ['connection', 'timeout', 'network', 'dns', 'socket']
        if any(keyword in message for keyword in network_keywords):
            return ErrorType.NETWORK_ERROR
        
        return ErrorType.UNKNOWN_ERROR
    
    def _classify_provider_error(self, 
                               provider: str, 
                               message: str, 
                               status_code: Optional[int]) -> ErrorType:
        """Classifica l'errore basandosi sul provider specifico.
        
        Args:
            provider: Nome del provider
            message: Messaggio di errore
            status_code: Codice di stato HTTP
            
        Returns:
            Tipo di errore classificato
        """
        provider_config = PROVIDER_CONFIG.get(provider, {})
        quota_codes = provider_config.get('quota_status_codes', [])
        
        # Se il codice di stato indica quota exceeded per questo provider
        if status_code and status_code in quota_codes:
            return ErrorType.QUOTA_EXCEEDED
        
        # Analisi basata su parole chiave specifiche del provider
        if provider == 'Google':
            if 'resource exhausted' in message or 'quota exceeded' in message:
                return ErrorType.QUOTA_EXCEEDED
            elif 'rate limit' in message:
                return ErrorType.RATE_LIMIT
        
        elif provider == 'OpenAI':
            if 'insufficient_quota' in message or 'billing' in message:
                return ErrorType.QUOTA_EXCEEDED
            elif 'rate_limit_exceeded' in message:
                return ErrorType.RATE_LIMIT
        
        elif provider == 'Anthropic':
            if 'credit_balance_too_low' in message:
                return ErrorType.QUOTA_EXCEEDED
            elif 'rate_limit' in message:
                return ErrorType.RATE_LIMIT
        
        # Default: prova a classificare con i pattern generici
        return self._detect_error_type(message, status_code, None)
    
    def _matches_patterns(self, message: str, patterns: List[re.Pattern]) -> bool:
        """Verifica se il messaggio corrisponde a uno dei pattern.
        
        Args:
            message: Messaggio da verificare
            patterns: Lista di pattern compilati
            
        Returns:
            True se il messaggio corrisponde a almeno un pattern
        """
        return any(pattern.search(message) for pattern in patterns)
    
    def _determine_severity(self, 
                          error_type: ErrorType, 
                          status_code: Optional[int], 
                          provider: Optional[str]) -> ErrorSeverity:
        """Determina la gravità dell'errore.
        
        Args:
            error_type: Tipo di errore
            status_code: Codice di stato HTTP
            provider: Nome del provider
            
        Returns:
            Livello di gravità dell'errore
        """
        if error_type == ErrorType.QUOTA_EXCEEDED:
            return ErrorSeverity.HIGH
        elif error_type == ErrorType.RATE_LIMIT:
            return ErrorSeverity.MEDIUM
        elif error_type == ErrorType.AUTH_ERROR:
            return ErrorSeverity.CRITICAL
        elif error_type == ErrorType.NETWORK_ERROR:
            return ErrorSeverity.LOW
        elif error_type == ErrorType.SERVER_ERROR:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW
    
    def _extract_retry_after(self, headers: Optional[Dict[str, str]]) -> Optional[int]:
        """Estrae il valore Retry-After dagli headers HTTP.
        
        Args:
            headers: Headers della risposta HTTP
            
        Returns:
            Secondi da aspettare prima del retry, se specificato
        """
        if not headers:
            return None
        
        retry_after = headers.get('Retry-After') or headers.get('retry-after')
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                logger.warning(f"Valore Retry-After non valido: {retry_after}")
        
        return None
    
    def _calculate_suggested_cooldown(self, 
                                    error_type: ErrorType, 
                                    provider: Optional[str], 
                                    retry_after: Optional[int]) -> Optional[int]:
        """Calcola il cooldown suggerito per l'errore.
        
        Args:
            error_type: Tipo di errore
            provider: Nome del provider
            retry_after: Valore Retry-After se disponibile
            
        Returns:
            Secondi di cooldown suggerito
        """
        # Se c'è un Retry-After, usalo
        if retry_after:
            return retry_after
        
        # Usa il cooldown specifico del provider
        if provider and provider in PROVIDER_CONFIG:
            base_cooldown = PROVIDER_CONFIG[provider]['base_cooldown']
        else:
            base_cooldown = FALLBACK_CONFIG['cooldown_period']
        
        # Modifica il cooldown basandosi sul tipo di errore
        if error_type == ErrorType.QUOTA_EXCEEDED:
            return base_cooldown * 2  # Cooldown più lungo per quota
        elif error_type == ErrorType.RATE_LIMIT:
            return base_cooldown
        elif error_type == ErrorType.AUTH_ERROR:
            return None  # Errori di auth non si risolvono con il tempo
        elif error_type == ErrorType.NETWORK_ERROR:
            return 30  # Retry veloce per errori di rete
        else:
            return base_cooldown // 2  # Cooldown più breve per altri errori
    
    def _is_recoverable(self, error_type: ErrorType, status_code: Optional[int]) -> bool:
        """Determina se l'errore è recuperabile automaticamente.
        
        Args:
            error_type: Tipo di errore
            status_code: Codice di stato HTTP
            
        Returns:
            True se l'errore è recuperabile
        """
        # Errori non recuperabili
        if error_type == ErrorType.AUTH_ERROR:
            return False
        
        # Alcuni codici di stato indicano errori non recuperabili
        if status_code in [400, 404, 405, 422]:  # Bad request, not found, etc.
            return False
        
        return True
    
    def _get_timestamp(self) -> float:
        """Ottiene il timestamp corrente.
        
        Returns:
            Timestamp Unix corrente
        """
        import time
        return time.time()
    
    def is_quota_error(self, error_info: ErrorInfo) -> bool:
        """Verifica se l'errore è di tipo quota exceeded.
        
        Args:
            error_info: Informazioni sull'errore
            
        Returns:
            True se è un errore di quota
        """
        return error_info.error_type == ErrorType.QUOTA_EXCEEDED
    
    def is_rate_limit_error(self, error_info: ErrorInfo) -> bool:
        """Verifica se l'errore è di tipo rate limit.
        
        Args:
            error_info: Informazioni sull'errore
            
        Returns:
            True se è un errore di rate limit
        """
        return error_info.error_type == ErrorType.RATE_LIMIT
    
    def should_trigger_fallback(self, error_info: ErrorInfo) -> bool:
        """Determina se l'errore dovrebbe attivare il fallback.
        
        Args:
            error_info: Informazioni sull'errore
            
        Returns:
            True se dovrebbe essere attivato il fallback
        """
        # Attiva fallback per errori recuperabili
        fallback_types = {
            ErrorType.QUOTA_EXCEEDED,
            ErrorType.RATE_LIMIT,
            ErrorType.AUTH_ERROR,
            ErrorType.SERVER_ERROR,
            ErrorType.NETWORK_ERROR,
            ErrorType.UNKNOWN_ERROR
        }
        
        return (
            error_info.error_type in fallback_types and 
            error_info.is_recoverable
        )

# Istanza globale del rilevatore
detector = QuotaErrorDetector()

# Funzioni di convenienza
def detect_quota_error(error_message: str = "", 
                     status_code: Optional[int] = None,
                     response_headers: Optional[Dict[str, str]] = None,
                     provider: Optional[str] = None,
                     exception: Optional[Exception] = None) -> ErrorInfo:
    """Funzione di convenienza per rilevare errori di quota.
    
    Args:
        error_message: Messaggio di errore
        status_code: Codice di stato HTTP
        response_headers: Headers della risposta
        provider: Nome del provider
        exception: Eccezione originale
        
    Returns:
        Informazioni sull'errore rilevato
    """
    return detector.detect_error(
        error_message=error_message,
        status_code=status_code,
        response_headers=response_headers,
        provider=provider,
        exception=exception
    )

def is_quota_exceeded(error_message: str = "", 
                     status_code: Optional[int] = None,
                     provider: Optional[str] = None) -> bool:
    """Verifica rapidamente se un errore indica quota exceeded.
    
    Args:
        error_message: Messaggio di errore
        status_code: Codice di stato HTTP
        provider: Nome del provider
        
    Returns:
        True se è un errore di quota exceeded
    """
    error_info = detect_quota_error(
        error_message=error_message,
        status_code=status_code,
        provider=provider
    )
    return detector.is_quota_error(error_info)
