"""
Cancellation Manager - Thread-safe cancellation flag for batch operations.

Provides a centralized mechanism to request cancellation of long-running
batch processes with proper synchronization and timeout handling.
"""
import threading
import logging
import time
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CancellationState(Enum):
    IDLE = "idle"
    REQUESTED = "requested"
    PROCESSING = "processing"
    COMPLETED = "completed"
    TIMEOUT = "timeout"


class CancellationManager:
    """
    Thread-safe cancellation manager for batch operations.
    
    Provides:
    - Atomic cancellation flag
    - State tracking
    - Timeout handling
    - Callback support
    """
    
    _instance: Optional['CancellationManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._cancel_event = threading.Event()
        self._state = CancellationState.IDLE
        self._state_lock = threading.Lock()
        self._request_time: Optional[float] = None
        self._completion_time: Optional[float] = None
        self._timeout_seconds = 5.0
        self._callbacks: list = []
        self._cancellation_reason: Optional[str] = None
        self._processed_items: int = 0
        self._total_items: int = 0
        self._last_checkpoint: dict = {}
        self._initialized = True
        
        logger.info("[CANCELLATION] CancellationManager initialized")
    
    @property
    def is_cancellation_requested(self) -> bool:
        """Check if cancellation has been requested (thread-safe)."""
        return self._cancel_event.is_set()
    
    @property
    def state(self) -> CancellationState:
        """Get current cancellation state (thread-safe)."""
        with self._state_lock:
            return self._state
    
    @property
    def timeout_seconds(self) -> float:
        """Get configured timeout for cancellation completion."""
        return self._timeout_seconds
    
    @timeout_seconds.setter
    def timeout_seconds(self, value: float):
        """Set timeout for cancellation completion (max 5 seconds)."""
        self._timeout_seconds = max(0.1, min(5.0, value))
    
    def request_cancellation(self, reason: str = "User requested") -> bool:
        """
        Request cancellation of batch operation.
        
        Args:
            reason: Reason for cancellation
            
        Returns:
            True if cancellation was requested, False if already cancelled
        """
        if self._cancel_event.is_set():
            logger.warning("[CANCELLATION] Cancellation already requested")
            return False
        
        with self._state_lock:
            self._cancel_event.set()
            self._state = CancellationState.REQUESTED
            self._request_time = time.time()
            self._cancellation_reason = reason
            
        logger.info(f"[CANCELLATION] Cancellation requested: {reason}")
        self._notify_callbacks()
        return True
    
    def begin_cancellation_processing(self):
        """Mark that cancellation is being processed."""
        with self._state_lock:
            self._state = CancellationState.PROCESSING
        logger.info("[CANCELLATION] Beginning cancellation processing")
    
    def complete_cancellation(self, success: bool = True):
        """
        Mark cancellation as complete.
        
        Args:
            success: True if cancellation completed successfully
        """
        with self._state_lock:
            self._completion_time = time.time()
            if success:
                self._state = CancellationState.COMPLETED
                duration = self._completion_time - self._request_time if self._request_time else 0
                logger.info(f"[CANCELLATION] Cancellation completed successfully in {duration:.2f}s")
            else:
                self._state = CancellationState.TIMEOUT
                logger.warning("[CANCELLATION] Cancellation timed out")
    
    def reset(self):
        """Reset cancellation state for new operation."""
        with self._state_lock:
            self._cancel_event.clear()
            self._state = CancellationState.IDLE
            self._request_time = None
            self._completion_time = None
            self._cancellation_reason = None
            self._processed_items = 0
            self._total_items = 0
            self._last_checkpoint = {}
        logger.info("[CANCELLATION] Cancellation state reset")
    
    def check(self) -> bool:
        """
        Check if cancellation is requested.
        
        Returns:
            True if cancellation should stop, False otherwise
        """
        return self._cancel_event.is_set()
    
    def check_with_checkpoint(self, checkpoint_name: str, checkpoint_data: dict = None) -> bool:
        """
        Check cancellation and save checkpoint data.
        
        Args:
            checkpoint_name: Name of the current checkpoint
            checkpoint_data: Optional data to save at this checkpoint
            
        Returns:
            True if cancellation should stop, False otherwise
        """
        if checkpoint_data:
            self._last_checkpoint = {
                'name': checkpoint_name,
                'data': checkpoint_data,
                'time': time.time()
            }
        return self.check()
    
    def update_progress(self, processed: int, total: int):
        """Update cancellation progress tracking."""
        self._processed_items = processed
        self._total_items = total
    
    def get_progress(self) -> tuple:
        """Get current cancellation progress."""
        return (self._processed_items, self._total_items)
    
    def get_last_checkpoint(self) -> dict:
        """Get the last saved checkpoint data."""
        return self._last_checkpoint.copy()
    
    def get_cancellation_info(self) -> dict:
        """Get detailed cancellation information."""
        with self._state_lock:
            info = {
                'state': self._state.value,
                'requested': self._cancel_event.is_set(),
                'reason': self._cancellation_reason,
                'request_time': self._request_time,
                'completion_time': self._completion_time,
                'timeout': self._timeout_seconds,
                'processed_items': self._processed_items,
                'total_items': self._total_items,
                'last_checkpoint': self._last_checkpoint.get('name') if self._last_checkpoint else None
            }
            
            if self._request_time and not self._completion_time:
                info['elapsed_since_request'] = time.time() - self._request_time
                
            return info
    
    def add_callback(self, callback: callable):
        """Add a callback to be notified on cancellation request."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)
    
    def remove_callback(self, callback: callable):
        """Remove a cancellation callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_callbacks(self):
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(self._cancellation_reason)
            except Exception as e:
                logger.error(f"[CANCELLATION] Callback error: {e}")
    
    def wait_for_completion(self, timeout: float = None) -> bool:
        """
        Wait for cancellation to be completed.
        
        Args:
            timeout: Maximum time to wait (uses timeout_seconds if None)
            
        Returns:
            True if cancellation completed, False if timed out
        """
        timeout = timeout or self._timeout_seconds
        start = time.time()
        
        while self._state in (CancellationState.REQUESTED, CancellationState.PROCESSING):
            if time.time() - start > timeout:
                logger.warning(f"[CANCELLATION] Timeout waiting for completion after {timeout}s")
                return False
            time.sleep(0.05)
        
        return True


_cancellation_manager = None


def get_cancellation_manager() -> CancellationManager:
    """Get the global CancellationManager instance."""
    global _cancellation_manager
    if _cancellation_manager is None:
        _cancellation_manager = CancellationManager()
    return _cancellation_manager


def request_batch_cancellation(reason: str = "User requested") -> bool:
    """Convenience function to request batch cancellation."""
    return get_cancellation_manager().request_cancellation(reason)


def check_cancellation() -> bool:
    """Convenience function to check if cancellation is requested."""
    return get_cancellation_manager().check()
