"""Modulo per flood fill asincrono non bloccante."""

import numpy as np
import logging
import time
from typing import Optional, Tuple, Callable
from dataclasses import dataclass
from PySide6 import QtCore, QtGui, QtWidgets
from app.ui.canvas.pixmap_state import sync_viewer_photo_to_image_data

logger = logging.getLogger(__name__)


@dataclass
class FloodFillRequest:
    scene_pos: QtCore.QPointF
    fill_color: QtGui.QColor
    tolerance: int
    timestamp: float


@dataclass
class FloodFillResult:
    success: bool
    old_pixmap: Optional[QtGui.QPixmap] = None
    new_pixmap: Optional[QtGui.QPixmap] = None
    error: Optional[str] = None
    duration_ms: float = 0


class AsyncFloodFiller(QtCore.QObject):
    """
    Gestisce flood fill in modo asincrono con thread separato.
    Implementa rate limiting e coalescing delle richieste.
    """

    result_ready = QtCore.Signal(object)
    fill_started = QtCore.Signal()
    fill_completed = QtCore.Signal(float)
    fill_failed = QtCore.Signal(str)

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self._viewer = viewer
        self._is_filling = False
        self._pending_fill: Optional[FloodFillRequest] = None
        self._coalesce_timer = QtCore.QTimer()
        self._coalesce_timer.setSingleShot(True)
        self._coalesce_timer.timeout.connect(self._process_coalesced_fill)
        self._coalesce_delay_ms = 50
        self._min_fill_interval_ms = 80
        self._last_fill_time = 0
        self._fill_count = 0
        self._total_fill_time_ms = 0
        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[QtCore.QObject] = None

    def schedule_fill(
        self,
        scene_pos: QtCore.QPointF,
        fill_color: QtGui.QColor,
        tolerance: int
    ) -> bool:
        """
        Agenda un flood fill con rate limiting e coalescing.

        Returns:
            True se il fill è stato agendato, False se rate limited
        """
        now = time.perf_counter()
        elapsed = (now - self._last_fill_time) * 1000

        if self._is_filling:
            self._pending_fill = FloodFillRequest(
                scene_pos=scene_pos,
                fill_color=fill_color,
                tolerance=tolerance,
                timestamp=now
            )
            return False

        if elapsed < self._min_fill_interval_ms:
            self._pending_fill = FloodFillRequest(
                scene_pos=scene_pos,
                fill_color=fill_color,
                tolerance=tolerance,
                timestamp=now
            )
            if not self._coalesce_timer.isActive():
                self._coalesce_timer.start(self._coalesce_delay_ms)
            return False

        self._last_fill_time = now
        self._execute_fill_async(scene_pos, fill_color, tolerance)
        return True

    def _process_coalesced_fill(self):
        if self._pending_fill:
            req = self._pending_fill
            self._pending_fill = None
            self._execute_fill_async(req.scene_pos, req.fill_color, req.tolerance)

    def _execute_fill_async(
        self,
        scene_pos: QtCore.QPointF,
        fill_color: QtGui.QColor,
        tolerance: int
    ):
        """Avvia il flood fill.

        La parte Qt (QPixmap/QImage) resta sul thread GUI, che e' l'unico
        thread valido per QPixmap. Il lavoro pesante (cv2.floodFill +
        conversioni) viene eseguito su un worker e il risultato torna al
        thread GUI che costruisce la QImage finale. Prima tutto girava inline
        sul thread GUI: su una pagina 4000x6000 il click del secchello
        congelava la UI per centinaia di ms.
        """
        self._is_filling = True
        self.fill_started.emit()

        start_time = time.perf_counter()

        try:
            old_pixmap = self._viewer.photo.pixmap().copy()
            local_pos = self._viewer.photo.mapFromScene(scene_pos)
            x = int(local_pos.x())
            y = int(local_pos.y())

            pixmap = self._viewer.photo.pixmap()
            if not pixmap or pixmap.isNull():
                raise ValueError("Pixmap non valido")

            if not (0 <= x < pixmap.width() and 0 <= y < pixmap.height()):
                raise ValueError(f"Coordinate fuori range: ({x}, {y})")

            qimage = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_RGB888)
            width = qimage.width()
            height = qimage.height()
            bytes_per_line = qimage.bytesPerLine()
            ptr = qimage.bits()
            arr = np.array(ptr).reshape((height, bytes_per_line))
            # .copy() stacca il buffer dal QImage, che verra' distrutto: senza,
            # il worker leggerebbe memoria liberata.
            arr = arr[:, :width * 3].reshape((height, width, 3)).copy()

            self._run_flood_worker(arr, x, y, fill_color, tolerance,
                                   old_pixmap, start_time, width, height)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"[FLOOD_FILL] Errore: {e}", exc_info=True)

            result = FloodFillResult(
                success=False,
                old_pixmap=None,
                new_pixmap=None,
                error=str(e),
                duration_ms=duration_ms
            )

            self.result_ready.emit(result)
            self.fill_failed.emit(str(e))
            self._finish_fill()

    @QtCore.Slot(object)
    def _on_worker_done(self, payload):
        """Callback eseguita sul thread GUI quando il worker ha finito."""
        start_time, old_pixmap, width, height, ok, value = payload
        duration_ms = (time.perf_counter() - start_time) * 1000
        try:
            if not ok:
                raise RuntimeError(str(value))

            arr = value
            # Format_RGB888 richiede che bytesPerLine sia multiplo di 4:
            # width*3 non lo e' sempre (es. width=5 -> 15) e Qt rigettava
            # l'immagine. Si usa uno stride allineato e si copia.
            stride = ((width * 3 + 3) // 4) * 4
            if stride != width * 3:
                padded = np.zeros((height, stride), dtype=arr.dtype)
                padded[:, :width * 3] = arr.reshape(height, width * 3)
                arr = padded

            new_qimage = QtGui.QImage(
                arr.data, width, height, stride, QtGui.QImage.Format.Format_RGB888
            )
            new_pixmap = QtGui.QPixmap.fromImage(new_qimage.copy())

            self._total_fill_time_ms += duration_ms
            self._fill_count += 1
            logger.info(
                f"[FLOOD_FILL] Completato in {duration_ms:.1f}ms "
                f"(media: {self._total_fill_time_ms / self._fill_count:.1f}ms)"
            )
            result = FloodFillResult(
                success=True,
                old_pixmap=old_pixmap,
                new_pixmap=new_pixmap,
                duration_ms=duration_ms,
            )
            self.result_ready.emit(result)
            self.fill_completed.emit(duration_ms)

        except Exception as e:
            logger.error(f"[FLOOD_FILL] Errore in _on_worker_done: {e}", exc_info=True)
            self.result_ready.emit(FloodFillResult(
                success=False, old_pixmap=None, new_pixmap=None,
                error=str(e), duration_ms=duration_ms))
            self.fill_failed.emit(str(e))
        finally:
            self._finish_fill()

    def _finish_fill(self):
        """Ripristina lo stato e riprocessa l'eventuale richiesta in coda."""
        self._is_filling = False
        self._thread = None
        self._worker = None

        pending = self._pending_fill
        if pending:
            self._pending_fill = None
            QtCore.QTimer.singleShot(0, lambda: self.schedule_fill(
                pending.scene_pos, pending.fill_color, pending.tolerance
            ))

    def _run_flood_worker(self, arr, x, y, fill_color, tolerance,
                          old_pixmap, start_time, width, height):
        """Esegue cv2.floodFill su un thread dedicato (solo numpy/cv2, niente Qt)."""
        from app.thread_worker import GenericWorker

        rgb_arr = arr
        seed = (int(x), int(y))
        bgr = (int(fill_color.blue()), int(fill_color.green()), int(fill_color.red()))
        tol = int(tolerance)

        def heavy():
            import cv2
            buf = np.ascontiguousarray(rgb_arr)
            bgr_buf = cv2.cvtColor(buf, cv2.COLOR_RGB2BGR)
            h, w = bgr_buf.shape[:2]
            mask = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(bgr_buf, mask, seed, bgr, (tol, tol, tol), (tol, tol, tol),
                          cv2.FLOODFILL_FIXED_RANGE)
            return cv2.cvtColor(bgr_buf, cv2.COLOR_BGR2RGB)

        worker = GenericWorker(heavy)
        self._thread = worker
        self._worker = worker

        def _deliver(payload):
            try:
                self._on_worker_done(payload)
            except Exception as e:
                logger.error(f"[FLOOD_FILL] Consegna fallita: {e}")
                self._finish_fill()

        worker.signals.result.connect(
            lambda res: _deliver((start_time, old_pixmap, width, height, True, res)))
        worker.signals.error.connect(
            lambda err: _deliver((start_time, old_pixmap, width, height, False, err)))

        QtCore.QThreadPool.globalInstance().start(worker)

    def cancel_pending(self):
        self._pending_fill = None
        self._coalesce_timer.stop()

    @property
    def is_busy(self) -> bool:
        return self._is_filling or self._coalesce_timer.isActive() or self._pending_fill is not None

    @property
    def stats(self) -> dict:
        avg_time = self._total_fill_time_ms / self._fill_count if self._fill_count > 0 else 0
        return {
            'count': self._fill_count,
            'total_time_ms': self._total_fill_time_ms,
            'avg_time_ms': avg_time,
            'is_busy': self.is_busy,
            'has_pending': self._pending_fill is not None
        }


class BucketFillUIController:
    """
    Controller per la gestione UI del bucket fill con feedback visivo.
    """

    def __init__(self, viewer, main_controller=None):
        self._viewer = viewer
        self._main_controller = main_controller
        self._flood_filler = AsyncFloodFiller(viewer)
        self._flood_filler.result_ready.connect(self._on_fill_result)
        self._flood_filler.fill_started.connect(self._on_fill_started)
        self._flood_filler.fill_completed.connect(self._on_fill_completed)
        self._flood_filler.fill_failed.connect(self._on_fill_failed)
        self._bucket_button = None
        self._loading_indicator = None
        self._timeout_timer = QtCore.QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_fill_timeout)
        self._timeout_ms = 5000

    def connect_bucket_button(self, button):
        self._bucket_button = button

    def _set_timeout(self, timeout_ms: int):
        self._timeout_ms = timeout_ms

    def _on_fill_started(self):
        if self._bucket_button:
            self._bucket_button.setEnabled(False)
        self._timeout_timer.start(self._timeout_ms)

    def _on_fill_completed(self, duration_ms: float):
        self._timeout_timer.stop()
        if self._bucket_button:
            self._bucket_button.setEnabled(True)

    def _on_fill_failed(self, error: str):
        self._timeout_timer.stop()
        if self._bucket_button:
            self._bucket_button.setEnabled(True)
        logger.error(f"[BUCKET_UI] Fill fallito: {error}")

    def _on_fill_timeout(self):
        logger.warning("[BUCKET_UI] Timeout fill raggiunto")
        if self._bucket_button:
            self._bucket_button.setEnabled(True)

    def _on_fill_result(self, result: FloodFillResult):
        if not result.success:
            return

        self._viewer.photo.setPixmap(result.new_pixmap)
        sync_viewer_photo_to_image_data(self._viewer)
        self._viewer._scene.update()

        from app.ui.commands.bucket import BucketFillCommand
        command = BucketFillCommand(
            self._viewer,
            result.old_pixmap,
            result.new_pixmap
        )
        self._viewer.command_emitted.emit(command)

    def schedule_fill(self, scene_pos: QtCore.QPointF) -> bool:
        """Agenda un fill con le impostazioni correnti del viewer."""
        fill_color = self._viewer.painting_color
        tolerance = self._viewer.bucket_fill_tolerance
        return self._flood_filler.schedule_fill(scene_pos, fill_color, tolerance)

    def cancel(self):
        self._flood_filler.cancel_pending()
        self._timeout_timer.stop()

    @property
    def flood_filler(self) -> AsyncFloodFiller:
        return self._flood_filler

    @property
    def is_responsive(self) -> bool:
        return not self._flood_filler.is_busy
