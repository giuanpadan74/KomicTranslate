"""
geminiamo_client.py
-------------------
Client Gemini ottimizzato:
  - Nessun .env, nessun .bat: cookie letti live da Firefox via get_firefox_cookies().
  - Auto-refresh automatico al primo errore 401/403/session.
  - Debouncing umano tra le richieste (5-12s randomizzato).
  - Lazy initialization: il client viene creato solo al primo utilizzo.
  - Singleton thread-safe.
"""

import threading
import time
import random
import asyncio
import hashlib
import logging
import json
import os
from statistics import mean, stdev
from collections import deque

from gemini_webapi import GeminiClient
from PySide6.QtCore import QObject, Signal

from modules.geminiamo_auth.get_gemini_cookie import get_firefox_cookies


# Configure logging levels for compactness
logging.getLogger('gemini_webapi').setLevel(logging.ERROR)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('hpack').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Create logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


_SESSION_ERROR_KEYWORDS = ("403", "401", "invalid", "expired", "unauthorized", "session", "forbidden", "queue")
_STREAM_ERROR_KEYWORDS = ("stalled", "zombie", "timeout", "timed out", "connection reset")
_DEBOUNCE_MIN = 2.0  # Ridotto da 5.0 a 2.0 secondi
_DEBOUNCE_MAX = 4.0  # Ridotto da 12.0 a 4.0 secondi
_REQUEST_TIMEOUT = 60  # Timeout per singola richiesta (secondi)


class ResponseTracker:
    """Tracks response times and calculates optimal debounce timing with persistence."""
    
    def __init__(self, request_type: str, max_samples=50):
        self.request_type = request_type
        self.metrics_file = f"config/gemini_{request_type}_metrics.json"
        self.max_samples = max_samples
        self.response_times = deque(maxlen=max_samples)
        self._lock = threading.Lock()
        
        # Load persisted metrics
        self._load_metrics()
        
        # Default values if no data
        self.avg_response_time = 20.0  # seconds
        self.std_dev = 5.0
        self.optimal_debounce = 3.0
        self.last_updated = time.time()
        
        # Request tracking metrics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.requests_per_hour = 0
        self.last_hour_reset = time.time()
        
        # Update from loaded data
        self._calculate_optimal_debounce()
    
    def _load_metrics(self):
        """Load metrics from JSON file."""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    times = data.get('response_times', [])
                    self.response_times.extend(times[-self.max_samples:])
                    self.last_updated = data.get('last_updated', time.time())
                    
                    # Load request metrics
                    self.total_requests = data.get('total_requests', 0)
                    self.successful_requests = data.get('successful_requests', 0)
                    self.failed_requests = data.get('failed_requests', 0)
                    self.requests_per_hour = data.get('requests_per_hour', 0)
                    self.last_hour_reset = data.get('last_hour_reset', time.time())
                    
                    logger.info(f"Loaded {len(self.response_times)} response time samples and {self.total_requests} total requests for {self.request_type}")
        except Exception as e:
            logger.warning(f"Failed to load metrics: {e}")
    
    def _save_metrics(self):
        """Save metrics to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
            data = {
                'response_times': list(self.response_times),
                'last_updated': self.last_updated,
                'avg_response_time': self.avg_response_time,
                'std_dev': self.std_dev,
                'optimal_debounce': self.optimal_debounce,
                
                # Request metrics
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'requests_per_hour': self.requests_per_hour,
                'last_hour_reset': self.last_hour_reset
            }
            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save metrics: {e}")
    
    def record_response_time(self, response_time: float, success: bool = True):
        """Record a new response time and update metrics."""
        with self._lock:
            self.response_times.append(response_time)
            self.last_updated = time.time()
            
            # Update request metrics
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            
            # Reset hourly counter if needed
            current_time = time.time()
            if current_time - self.last_hour_reset >= 3600:  # 1 hour
                self.requests_per_hour = 0
                self.last_hour_reset = current_time
            
            self.requests_per_hour += 1
            
            self._calculate_optimal_debounce()
            self._save_metrics()
    
    def _calculate_optimal_debounce(self):
        """Calculate optimal debounce based on response times and request volume."""
        if len(self.response_times) < 3:
            # Not enough data, use conservative defaults
            self.optimal_debounce = 3.0
            return
        
        try:
            self.avg_response_time = mean(self.response_times)
            if len(self.response_times) > 1:
                self.std_dev = stdev(self.response_times)
            else:
                self.std_dev = 0
            
            # Base debounce on response time and variability
            base_debounce = self.avg_response_time * 0.15 + self.std_dev * 0.5
            
            # Increase debounce if high request volume to reduce polling
            if self.requests_per_hour > 10:
                volume_factor = min(2.0, self.requests_per_hour / 20.0)  # Max 2x increase
                base_debounce *= volume_factor
            
            # Apply bounds
            self.optimal_debounce = max(_DEBOUNCE_MIN, min(_DEBOUNCE_MAX, base_debounce))
            
            logger.debug(f"Updated {self.request_type} metrics: avg={self.avg_response_time:.2f}s, std={self.std_dev:.2f}s, req/hour={self.requests_per_hour}, debounce={self.optimal_debounce:.2f}s")
        except Exception as e:
            logger.warning(f"Error calculating optimal debounce: {e}")
            self.optimal_debounce = 3.0
    
    def get_adaptive_debounce(self) -> float:
        """Get the current optimal debounce time."""
        with self._lock:
            return self.optimal_debounce
    
    def get_stats(self) -> dict:
        """Get current statistics."""
        with self._lock:
            return {
                'samples': len(self.response_times),
                'avg_response_time': self.avg_response_time,
                'std_dev': self.std_dev,
                'optimal_debounce': self.optimal_debounce,
                'last_updated': self.last_updated,
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'requests_per_hour': self.requests_per_hour,
                'success_rate': self.successful_requests / max(1, self.total_requests)
            }


class GeminiamoClient(QObject):
    _instance = None
    _lock = threading.Lock()
    cookies_updated = Signal(dict)
    refresh_failed = Signal()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self.client: GeminiClient | None = None
        self._client_initialized = False
        self._last_request_time = 0.0
        self._refresh_lock = threading.Lock()
        self._request_cache = {}  # Cache per evitare richieste duplicate
        self._cache_lock = threading.Lock()
        self.translation_tracker = ResponseTracker("translation")  # Adaptive timing tracker for text requests
        self.ocr_tracker = ResponseTracker("ocr")  # Adaptive timing tracker for image requests
        self._initialized = True

    # ------------------------------------------------------------------
    # Inizializzazione client (lazy)
    # ------------------------------------------------------------------

    def _init_client(self, cookies: dict | None = None) -> None:
        if self._client_initialized:
            return
        self._client_initialized = True

        if cookies is None:
            cookies = get_firefox_cookies()

        if not cookies or not cookies.get("__Secure-1PSID"):
            logger.info("Nessun cookie disponibile. Accedi a gemini.google.com in Firefox.")
            self.client = None
            return

        try:
            # Inizializza il client (gemini_webapi gestisce internamente timeout e connessioni)
            self.client = GeminiClient(
                cookies["__Secure-1PSID"],
                cookies.get("__Secure-1PSIDTS"),
            )
            logger.info("Client inizializzato da Firefox.")
        except Exception as e:
            logger.error(f"Errore di inizializzazione: {e}")
            self.client = None

    # ------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        cookies = get_firefox_cookies()
        return bool(cookies and cookies.get("__Secure-1PSID"))

    def extract_text(self, image_path: str) -> str:
        prompt = "Extract all text from this image exactly as it appears. Do not add any commentary."
        return self._call_with_retry(prompt, files=[image_path]).text

    def translate_text(self, text: str, target_lang: str = "Italian") -> str:
        prompt = f"Translate the following text into {target_lang}. Only provide the translation:\n\n{text}"
        return self._call_with_retry(prompt).text

    def generate_content(self, prompt: str, image_path: str | None = None) -> str:
        files = [image_path] if image_path else None
        return self._call_with_retry(prompt, files=files).text

    def clear_cache(self) -> None:
        """Pulisce la cache delle richieste."""
        with self._cache_lock:
            # Clear all cached responses to free memory
            self._request_cache.clear()
            logger.info("Cache pulita")

    def _cleanup_expired_cache(self) -> None:
        """Rimuove entries cache scaduti per liberare memoria."""
        current_time = time.monotonic()
        expired_keys = []
        
        with self._cache_lock:
            for cache_key, (response, timestamp) in self._request_cache.items():
                if current_time - timestamp >= 60:
                    expired_keys.append(cache_key)
            
            for key in expired_keys:
                del self._request_cache[key]
        
        if expired_keys:
            logger.debug(f"Rimossi {len(expired_keys)} entries cache scaduti")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refresh_cookies(self) -> bool:
        with self._refresh_lock:
            logger.info("Sessione scaduta — refresh cookie da Firefox...")
            cookies = get_firefox_cookies()
            if not cookies or not cookies.get("__Secure-1PSID"):
                logger.info("Refresh fallito: nessun cookie trovato in Firefox.")
                return False

            self._client_initialized = False
            self.client = None
            self._init_client(cookies)

            if self.client:
                self.cookies_updated.emit(cookies)
                logger.info("Refresh completato da Firefox.")
                return True
            return False

    def _wait_human_delay(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        # Use adaptive debounce with small random variation
        base_wait = self.translation_tracker.get_adaptive_debounce()
        wait = base_wait + random.uniform(-0.5, 0.5)  # Small variation
        wait = max(_DEBOUNCE_MIN, min(_DEBOUNCE_MAX, wait))  # Clamp to bounds
        remaining = wait - elapsed
        if remaining > 0:
            logger.info(f"Adaptive debounce: attesa {remaining:.1f}s (base: {base_wait:.1f}s)...")
            time.sleep(remaining)
        self._last_request_time = time.monotonic()

    def _get_cache_key(self, prompt: str, files: list | None) -> str:
        """Genera una chiave di cache per la richiesta."""
        key_parts = [prompt]
        if files:
            # Usa solo i nomi dei file per la cache, non il contenuto
            key_parts.extend([str(f) for f in files])
        return hashlib.md5("".join(key_parts).encode()).hexdigest()

    def _get_from_cache(self, cache_key: str):
        """Recupera una risposta dalla cache se disponibile e recente."""
        with self._cache_lock:
            if cache_key in self._request_cache:
                cached_response, timestamp = self._request_cache[cache_key]
                # Cache valida per 60 secondi
                if time.monotonic() - timestamp < 60:
                    logger.info("Risposta recuperata dalla cache")
                    return cached_response
                else:
                    # Rimuovi cache scaduta
                    del self._request_cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, response):
        """Salva una risposta nella cache."""
        with self._cache_lock:
            self._request_cache[cache_key] = (response, time.monotonic())
            # Limita dimensione cache a 100 elementi
            if len(self._request_cache) > 100:
                # Rimuovi l'elemento più vecchio
                oldest_key = min(self._request_cache.keys(), 
                               key=lambda k: self._request_cache[k][1])
                del self._request_cache[oldest_key]

    def _run_async(self, coro):
        """Esegue una coroutine in modo thread-safe con timeout applicato."""
        async def _with_timeout():
            return await asyncio.wait_for(coro, timeout=_REQUEST_TIMEOUT)

        # Ogni thread usa il proprio event loop isolato per evitare race condition.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_with_timeout())
        finally:
            try:
                # Cancella task pendenti e chiudi il loop per evitare resource leak
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                loop.close()

    def _call_with_retry(self, prompt: str, files: list | None = None):
        if not self.client:
            self._init_client()
            if not self.client:
                raise RuntimeError(
                    "GeminiamoClient non inizializzato. "
                    "Accedi a gemini.google.com in Firefox e riprova."
                )

        # Verifica cache
        cache_key = self._get_cache_key(prompt, files)
        cached_response = self._get_from_cache(cache_key)
        if cached_response:
            return cached_response

        self._wait_human_delay()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self._call_api(prompt, files)
                # Salva in cache
                self._save_to_cache(cache_key, response)
                return response
            except Exception as e:
                error_msg = str(e).lower()
                
                # Gestione errori di sessione
                if self._is_session_error(e):
                    logger.info(f"Errore sessione rilevato ({e}): tentativo refresh.")
                    if self._refresh_cookies():
                        self._wait_human_delay()
                        response = self._call_api(prompt, files)
                        self._save_to_cache(cache_key, response)
                        return response
                    self.refresh_failed.emit()
                    raise
                
                # Gestione errori di stream (zombie/stalled)
                if self._is_stream_error(e):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3  # Backoff: 3s, 6s, 9s
                        logger.info(f"Stream bloccato (tentativo {attempt + 1}/{max_retries})")
                        logger.info(f"Attesa {wait_time}s prima di riprovare...")
                        time.sleep(wait_time)
                        
                        # Reinizializza il client per forzare nuova connessione
                        self._client_initialized = False
                        self.client = None
                        self._init_client()
                        continue
                    else:
                        logger.info(f"Stream bloccato dopo {max_retries} tentativi")
                        raise RuntimeError(f"Stream bloccato dopo {max_retries} tentativi: {e}")
                
                # Altri errori - rilancia
                raise

    def _call_api(self, prompt: str, files: list | None):
        """Chiama l'API Gemini con timeout e ottimizzazioni."""
        start_time = time.monotonic()
        logger.info("Invio richiesta a Gemini...")
        
        try:
            if files:
                response = self._run_async(self.client.generate_content(prompt, files=files))
            else:
                response = self._run_async(self.client.generate_content(prompt))
            
            elapsed = time.monotonic() - start_time
            logger.info(f"Risposta ricevuta in {elapsed:.2f}s")
            
            # Record response time for adaptive timing
            if files:
                self.ocr_tracker.record_response_time(elapsed, success=True)
            else:
                self.translation_tracker.record_response_time(elapsed, success=True)
            
            return response
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            # Record failed request
            if files:
                self.ocr_tracker.record_response_time(elapsed, success=False)
            else:
                self.translation_tracker.record_response_time(elapsed, success=False)
            raise RuntimeError(f"Timeout dopo {elapsed:.2f}s - Gemini non ha risposto in tempo")
        except Exception as e:
            elapsed = time.monotonic() - start_time
            # Record failed request
            if files:
                self.ocr_tracker.record_response_time(elapsed, success=False)
            else:
                self.translation_tracker.record_response_time(elapsed, success=False)
            logger.error(f"Errore dopo {elapsed:.2f}s: {e}")
            raise

    @staticmethod
    def _is_session_error(exc: Exception) -> bool:
        return any(k in str(exc).lower() for k in _SESSION_ERROR_KEYWORDS)

    @staticmethod
    def _is_stream_error(exc: Exception) -> bool:
        """Verifica se l'errore è dovuto a stream bloccato/zombie."""
        return any(k in str(exc).lower() for k in _STREAM_ERROR_KEYWORDS)


geminiamo_client = GeminiamoClient()
