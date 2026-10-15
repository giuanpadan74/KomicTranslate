#!/usr/bin/env python3
"""
Sistema di logging automatico per KomicTranslate.
Fornisce funzioni di logging specializzate per diversi tipi di operazioni e errori.
"""

import logging
import time
import traceback
from typing import Any, Dict, Optional, List
from functools import wraps

# Configurazione del logger principale
logger = logging.getLogger('komictranslate.auto_logger')

# Configurazione dei logger specializzati
api_logger = logging.getLogger('komictranslate.api')
ocr_logger = logging.getLogger('komictranslate.ocr')
textblock_logger = logging.getLogger('komictranslate.textblock')
encoding_logger = logging.getLogger('komictranslate.encoding')
performance_logger = logging.getLogger('komictranslate.performance')
fallback_logger = logging.getLogger('komictranslate.fallback')
batch_logger = logging.getLogger('komictranslate.batch')

class ColorFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    COLORS = {
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[1;31m",
    }
    def __init__(self, fmt: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt: str | None = None):
        super().__init__(fmt=fmt, datefmt=datefmt)
        try:
            import colorama
            colorama.just_fix_windows_console()
        except Exception:
            pass
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        color = self.COLORS.get(record.levelno)
        return f"{color}{msg}{self.RESET}" if color else msg

def log_api_error(provider: str, operation: str, error: Exception, 
                 context: Optional[Dict[str, Any]] = None, 
                 api_key_hint: Optional[str] = None):
    """
    Registra errori delle API con informazioni dettagliate.
    
    Args:
        provider: Nome del provider API (es. 'google', 'openai')
        operation: Nome dell'operazione che ha causato l'errore
        error: Eccezione verificatasi
        context: Contesto aggiuntivo dell'errore
        api_key_hint: Suggerimento sulla chiave API (primi/ultimi caratteri)
    """
    error_msg = f"[API ERROR] Provider: {provider}, Operation: {operation}"
    
    if api_key_hint:
        error_msg += f", Key: {api_key_hint}"
    
    error_msg += f", Error: {str(error)}"
    
    if context:
        error_msg += f", Context: {context}"
    
    api_logger.error(error_msg)
    
    # Log del traceback se disponibile
    if hasattr(error, '__traceback__') and error.__traceback__:
        api_logger.debug(f"Traceback for {provider} {operation}: {traceback.format_exc()}")

def log_ocr_error(engine: str, image_info: Dict[str, Any], error: Exception,
                 processing_stage: str = "unknown"):
    """
    Registra errori specifici dell'OCR.
    
    Args:
        engine: Nome del motore OCR utilizzato
        image_info: Informazioni sull'immagine processata
        error: Eccezione verificatasi
        processing_stage: Fase del processing dove è avvenuto l'errore
    """
    error_msg = f"[OCR ERROR] Engine: {engine}, Stage: {processing_stage}"
    
    if 'size' in image_info:
        error_msg += f", Image Size: {image_info['size']}"
    
    if 'format' in image_info:
        error_msg += f", Format: {image_info['format']}"
    
    error_msg += f", Error: {str(error)}"
    
    ocr_logger.error(error_msg)
    
    # Log dettagli aggiuntivi in debug
    ocr_logger.debug(f"Full image info: {image_info}")

def log_textblock_error(textblock_id: str, operation: str, error: Exception,
                       textblock_data: Optional[Dict[str, Any]] = None):
    """
    Registra errori nella gestione dei textblock.
    
    Args:
        textblock_id: ID del textblock che ha causato l'errore
        operation: Operazione che stava sendo eseguita
        error: Eccezione verificatasi
        textblock_data: Dati del textblock per debug
    """
    error_msg = f"[TEXTBLOCK ERROR] ID: {textblock_id}, Operation: {operation}, Error: {str(error)}"
    
    textblock_logger.error(error_msg)
    
    if textblock_data:
        textblock_logger.debug(f"Textblock data for {textblock_id}: {textblock_data}")

def log_encoding_error(text: str, encoding: str, error: Exception,
                      operation: str = "encode/decode"):
    """
    Registra errori di encoding/decoding del testo.
    
    Args:
        text: Testo che ha causato l'errore (troncato per sicurezza)
        encoding: Encoding utilizzato
        error: Eccezione verificatasi
        operation: Tipo di operazione di encoding
    """
    # Tronca il testo per evitare log troppo lunghi
    text_preview = text[:100] + "..." if len(text) > 100 else text
    
    error_msg = f"[ENCODING ERROR] Operation: {operation}, Encoding: {encoding}"
    error_msg += f", Text Preview: '{text_preview}', Error: {str(error)}"
    
    encoding_logger.error(error_msg)

def log_performance_warning(operation: str, duration: float, threshold: float,
                          details: Optional[Dict[str, Any]] = None):
    """
    Registra warning per operazioni che superano le soglie di performance.
    
    Args:
        operation: Nome dell'operazione lenta
        duration: Durata effettiva in secondi
        threshold: Soglia di performance superata
        details: Dettagli aggiuntivi sull'operazione
    """
    warning_msg = f"[PERFORMANCE WARNING] Operation: {operation}"
    warning_msg += f", Duration: {duration:.2f}s, Threshold: {threshold:.2f}s"
    
    if details:
        warning_msg += f", Details: {details}"
    
    performance_logger.warning(warning_msg)

def log_fallback_activation(provider: str, original_key: str, fallback_key: str,
                           reason: str, attempt: int, max_attempts: int):
    """
    Registra l'attivazione del sistema di fallback delle API keys.
    
    Args:
        provider: Provider API
        original_key: Chiave originale che ha fallito (hint)
        fallback_key: Chiave di fallback utilizzata (hint)
        reason: Motivo del fallback
        attempt: Numero del tentativo corrente
        max_attempts: Numero massimo di tentativi
    """
    fallback_msg = f"[FALLBACK ACTIVATED] Provider: {provider}"
    fallback_msg += f", From: {original_key}, To: {fallback_key}"
    fallback_msg += f", Reason: {reason}, Attempt: {attempt}/{max_attempts}"
    
    fallback_logger.info(fallback_msg)

def log_batch_operation(operation: str, batch_size: int, success_count: int,
                       failure_count: int, duration: float,
                       details: Optional[Dict[str, Any]] = None):
    """
    Registra risultati di operazioni batch.
    
    Args:
        operation: Nome dell'operazione batch
        batch_size: Dimensione del batch
        success_count: Numero di operazioni riuscite
        failure_count: Numero di operazioni fallite
        duration: Durata totale dell'operazione
        details: Dettagli aggiuntivi
    """
    success_rate = (success_count / batch_size * 100) if batch_size > 0 else 0
    
    batch_msg = f"[BATCH OPERATION] Operation: {operation}"
    batch_msg += f", Size: {batch_size}, Success: {success_count}, Failed: {failure_count}"
    batch_msg += f", Success Rate: {success_rate:.1f}%, Duration: {duration:.2f}s"
    
    if details:
        batch_msg += f", Details: {details}"
    
    batch_logger.info(batch_msg)

def log_translation_error(translator: str, source_text: str, error: Exception,
                         source_lang: str = "unknown", target_lang: str = "unknown",
                         context: Optional[Dict[str, Any]] = None):
    """
    Registra errori specifici della traduzione.
    
    Args:
        translator: Nome del traduttore utilizzato
        source_text: Testo sorgente che ha causato l'errore (troncato)
        error: Eccezione verificatasi
        source_lang: Lingua sorgente
        target_lang: Lingua di destinazione
        context: Contesto aggiuntivo dell'errore
    """
    # Tronca il testo per evitare log troppo lunghi
    text_preview = source_text[:100] + "..." if len(source_text) > 100 else source_text
    
    error_msg = f"[TRANSLATION ERROR] Translator: {translator}"
    error_msg += f", {source_lang} -> {target_lang}"
    error_msg += f", Text: '{text_preview}', Error: {str(error)}"
    
    if context:
        error_msg += f", Context: {context}"
    
    # Usa il logger API per errori di traduzione
    api_logger.error(error_msg)
    
    # Log del traceback se disponibile
    if hasattr(error, '__traceback__') and error.__traceback__:
        api_logger.debug(f"Translation traceback for {translator}: {traceback.format_exc()}")

def performance_monitor(threshold: float = 1.0, log_args: bool = False):
    """
    Decorator per monitorare automaticamente le performance delle funzioni.
    
    Args:
        threshold: Soglia in secondi oltre la quale loggare un warning
        log_args: Se True, logga anche gli argomenti della funzione
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                if duration > threshold:
                    details = {}
                    if log_args:
                        details['args_count'] = len(args)
                        details['kwargs_keys'] = list(kwargs.keys())
                    
                    log_performance_warning(
                        operation=func.__name__,
                        duration=duration,
                        threshold=threshold,
                        details=details
                    )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                # Log dell'errore con informazioni di performance
                error_details = {
                    'function': func.__name__,
                    'duration_before_error': duration,
                    'args_count': len(args),
                    'kwargs_keys': list(kwargs.keys()) if log_args else None
                }
                
                logger.error(f"Function {func.__name__} failed after {duration:.2f}s: {str(e)}")
                logger.debug(f"Error details: {error_details}")
                
                raise
        
        return wrapper
    return decorator

def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """
    Configura il sistema di logging per KomicTranslate.
    
    Args:
        log_level: Livello di logging (DEBUG, INFO, WARNING, ERROR)
        log_file: File di log opzionale
    """
    # Configura il formato dei log
    formatter = ColorFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Configura l'handler per console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Configura tutti i logger
    loggers = [
        logger, api_logger, ocr_logger, textblock_logger,
        encoding_logger, performance_logger, fallback_logger, batch_logger
    ]
    
    for log in loggers:
        log.setLevel(getattr(logging, log_level.upper()))
        log.addHandler(console_handler)
        
        # Aggiungi file handler se specificato
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            log.addHandler(file_handler)

# Inizializzazione di default
if not logger.handlers:
    setup_logging()
