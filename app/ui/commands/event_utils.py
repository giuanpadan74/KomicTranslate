"""Utility per debouncing, profiling e gestione eventi con timeout."""

import time
import logging
import functools
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass, field
from PySide6 import QtCore

logger = logging.getLogger(__name__)


@dataclass
class TimingRecord:
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None

    def finish(self):
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000


class ProfilingContext:
    """Context manager per misurare i tempi di esecuzione."""

    def __init__(self, name: str, log_threshold_ms: float = 50.0):
        self.name = name
        self.log_threshold_ms = log_threshold_ms
        self.record = TimingRecord(name, time.perf_counter())

    def __enter__(self):
        return self.record

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.record.finish()
        if self.record.duration_ms > self.log_threshold_ms:
            logger.warning(
                f"[PROFILING] {self.name} took {self.record.duration_ms:.2f}ms "
                f"(threshold: {self.log_threshold_ms}ms)"
            )
        return False


class EventDebouncer:
    """Debouncer generico per eventi Qt con timeout di sicurezza."""

    def __init__(self, delay_ms: int = 100, timeout_ms: int = 5000):
        self.delay_ms = delay_ms
        self.timeout_ms = timeout_ms
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._pending_call: Optional[Callable] = None
        self._pending_args: tuple = ()
        self._pending_kwargs: dict = {}
        self._timeout_timer = QtCore.QTimer()
        self._timeout_timer.setSingleShot(True)
        self._last_execution_time: float = 0
        self._execution_count: int = 0
        self._consecutive_timeouts: int = 0
        self._is_executing: bool = False

        self._timer.timeout.connect(self._execute_pending)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def _execute_pending(self):
        self._is_executing = True
        try:
            if self._pending_call:
                with ProfilingContext(f"Debounced_{self._pending_call.__name__}", 20.0):
                    self._pending_call(*self._pending_args, **self._pending_kwargs)
        except Exception as e:
            logger.error(f"Errore nell'esecuzione debounced: {e}", exc_info=True)
        finally:
            self._is_executing = False
            self._timeout_timer.stop()

    def _on_timeout(self):
        self._is_executing = False
        self._consecutive_timeouts += 1
        logger.warning(
            f"[DEBOUNCE] Timeout raggiunto per evento pendente "
            f"(timeout #{self._consecutive_timeouts})"
        )

    def debounce(self, func: Callable) -> Callable:
        """Decoratore per debounce."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            self._pending_call = func
            self._pending_args = args
            self._pending_kwargs = kwargs
            self._timer.stop()
            self._timer.start(self.delay_ms)
            self._timeout_timer.stop()
            self._timeout_timer.start(self.timeout_ms)
        return wrapper

    def trigger(self, func: Callable, *args, **kwargs):
        """Esegue immediatamente senza debounce (per eventi urgenti)."""
        self._timer.stop()
        self._timeout_timer.stop()
        func(*args, **kwargs)

    @property
    def is_busy(self) -> bool:
        return self._timer.isActive() or self._is_executing


class AsyncOperationManager:
    """Gestisce operazioni asincrone con timeout e feedback."""

    def __init__(self, parent: QtCore.QObject = None):
        self._parent = parent
        self._active_operations: Dict[str, QtCore.QTimer] = {}
        self._operation_results: Dict[str, Any] = {}
        self._timeout_callbacks: Dict[str, Callable] = {}
        self._completion_callbacks: Dict[str, Callable] = {}
        self._status_callback: Optional[Callable] = None

    def set_status_callback(self, callback: Callable):
        self._status_callback = callback

    def _report_status(self, operation: str, status: str, progress: float = 0):
        if self._status_callback:
            try:
                self._status_callback(operation, status, progress)
            except Exception as e:
                logger.error(f"Errore nel callback di status: {e}")

    def execute_async(
        self,
        operation_id: str,
        work_func: Callable,
        result_callback: Callable,
        error_callback: Optional[Callable] = None,
        timeout_ms: int = 10000,
        work_args: tuple = (),
        work_kwargs: dict = None
    ):
        """
        Esegue un'operazione in modo asincrono con timeout.

        Args:
            operation_id: Identificatore univoco dell'operazione
            work_func: Funzione da eseguire (verrà chiamata in un worker thread)
            result_callback: Callback chiamato al completamento con il risultato
            error_callback: Callback chiamato in caso di errore
            timeout_ms: Timeout in millisecondi
            work_args: Argomenti per work_func
            work_kwargs: Keyword arguments per work_func
        """
        if work_kwargs is None:
            work_kwargs = {}

        def cleanup_and_result(result):
            # Ferma il timer: senza questo, un'operazione RIUSCITA generava
            # comunque un TimeoutError timeout_ms dopo, mostrato all'utente come
            # se fosse fallita (il timer non ha parent e resta attivo).
            if timer is not None:
                timer.stop()
            self._active_operations.pop(operation_id, None)
            self._operation_results[operation_id] = result
            self._report_status(operation_id, "completato", 100)
            result_callback(result)

        def handle_error(error_tuple):
            if timer is not None:
                timer.stop()
            self._active_operations.pop(operation_id, None)
            self._report_status(operation_id, "errore", 0)
            if error_callback:
                error_callback(error_tuple)

        def timeout_handler():
            logger.warning(f"[ASYNC] Timeout ({timeout_ms}ms) per operazione: {operation_id}")
            if timer is not None:
                timer.stop()
            self._active_operations.pop(operation_id, None)
            self._report_status(operation_id, "timeout", 0)
            if error_callback:
                error_callback(("TimeoutError", f"Operazione {operation_id} scaduta", ""))

        self._report_status(operation_id, "iniziato", 0)

        timer = None   # creato sotto; serve per poterlo fermare nei callback

        from app.thread_worker import GenericWorker
        worker = GenericWorker(lambda: work_func(*work_args, **work_kwargs))

        worker.signals.result.connect(cleanup_and_result)
        worker.signals.error.connect(handle_error)

        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(timeout_handler)
        timer.start(timeout_ms)

        self._active_operations[operation_id] = timer

        # 'parent' non e' un parametro di execute_async: il riferimento al
        # main page e' self._parent (impostato in __init__). Usare 'parent'
        # causava NameError e l'operazione non partiva mai.
        parent = self._parent
        if parent is not None and hasattr(parent, 'threadpool'):
            parent.threadpool.start(worker)

    def cancel_operation(self, operation_id: str) -> bool:
        if operation_id in self._active_operations:
            self._active_operations[operation_id].stop()
            del self._active_operations[operation_id]
            self._report_status(operation_id, "cancellato", 0)
            return True
        return False

    def cancel_all(self):
        for op_id, timer in list(self._active_operations.items()):
            timer.stop()
            self._report_status(op_id, "cancellato", 0)
        self._active_operations.clear()

    @property
    def has_active_operations(self) -> bool:
        return len(self._active_operations) > 0


class BucketFillScheduler:
    """Scheduler ottimizzato per operazioni di bucket fill."""

    def __init__(self, image_viewer, parent_controller=None):
        self._viewer = image_viewer
        self._controller = parent_controller
        self._debouncer = EventDebouncer(delay_ms=50, timeout_ms=3000)
        self._last_fill_pos: Optional[QtCore.QPointF] = None
        self._last_fill_time: float = 0
        self._fill_cooldown_ms: float = 100
        self._pending_fill: Optional[QtCore.QPointF] = None
        self._is_filling: bool = False
        self._fill_count: int = 0
        self._total_fill_time_ms: float = 0

    def schedule_fill(self, scene_pos: QtCore.QPointF):
        """Agenda un flood fill con debouncing e rate limiting."""
        now = time.perf_counter()
        time_since_last = (now - self._last_fill_time) * 1000

        if time_since_last < self._fill_cooldown_ms:
            self._pending_fill = scene_pos
            return

        self._last_fill_pos = scene_pos
        self._last_fill_time = now
        self._debouncer._pending_call = self._execute_fill
        self._debouncer._pending_args = (scene_pos,)
        self._debouncer._pending_kwargs = {}
        self._debouncer._timer.stop()
        self._debouncer._timer.start(0)

    def _execute_fill(self, scene_pos: QtCore.QPointF):
        if self._is_filling:
            return

        self._is_filling = True
        start = time.perf_counter()

        try:
            with ProfilingContext("flood_fill_at", 100.0):
                self._viewer.flood_fill_at(scene_pos)
        except Exception as e:
            logger.error(f"Errore in flood_fill_at: {e}", exc_info=True)
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            self._total_fill_time_ms += elapsed
            self._fill_count += 1
            self._is_filling = False

            logger.info(
                f"[BUCKET] Fill #{self._fill_count} completato in {elapsed:.1f}ms "
                f"(media: {self._total_fill_time_ms / self._fill_count:.1f}ms)"
            )

            if self._pending_fill:
                next_pos = self._pending_fill
                self._pending_fill = None
                QtCore.QTimer.singleShot(0, lambda: self.schedule_fill(next_pos))

    def cancel(self):
        self._debouncer._timer.stop()
        self._debouncer._timeout_timer.stop()
        self._pending_fill = None
        self._is_filling = False

    @property
    def is_busy(self) -> bool:
        return self._is_filling or self._debouncer.is_busy


def profile_execution(threshold_ms: float = 50.0):
    """Decoratore per profilare l'esecuzione di una funzione."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                if elapsed > threshold_ms:
                    logger.warning(
                        f"[PROFILE] {func.__qualname__} took {elapsed:.2f}ms "
                        f"(threshold: {threshold_ms}ms)"
                    )
        return wrapper
    return decorator


def rate_limit(calls_per_second: float = 10.0):
    """Decoratore per rate limiting."""
    min_interval = 1.0 / calls_per_second
    last_call_times: Dict[str, float] = {}

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}_{id(args[0]) if args else 'none'}"
            now = time.perf_counter()
            if key in last_call_times:
                elapsed = now - last_call_times[key]
                if elapsed < min_interval:
                    return
            last_call_times[key] = now
            return func(*args, **kwargs)
        return wrapper
    return decorator