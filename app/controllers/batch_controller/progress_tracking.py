"""
Progress tracking mixin for BatchMixin.

Handles progress bar updates and UI feedback during batch operations.
"""
import os
import logging
from PySide6.QtCore import QCoreApplication, QTimer

from app.ui.dayu_widgets.message import MMessage
from constants import UI_REFRESH_DELAY_MS

logger = logging.getLogger(__name__)


class ProgressTrackingMixin:
    """Progress tracking and UI feedback during batch operations."""

    def _is_final_batch_emit(self, index: int, total_images: int, step: int,
                             total_steps: int, total_archives: int) -> bool:
        return (
            total_images > 0
            and total_archives == 0
            and index >= total_images
            and step >= total_steps
        )

    def update_progress(self, index: int, total_images: int, step: int,
                        total_steps: int, change_name: bool):
        image_processing_weight = 0.9
        archiving_weight = 0.1

        archive_info_list = self.file_handler.archive_info
        total_archives = len(archive_info_list)

        if change_name:
            if index < total_images:
                im_path = self.image_files[index]
                im_name = os.path.basename(im_path)
                self.progress_bar.setFormat(
                    QCoreApplication.translate('Messages', 'Processing:') +
                    f" {im_name} . . . %p%")
            else:
                archive_index = index - total_images
                self.progress_bar.setFormat(
                    QCoreApplication.translate('Messages', 'Archiving:') +
                    f" {archive_index + 1}/{total_archives} . . . %p%")

        if self._is_final_batch_emit(index, total_images, step, total_steps, total_archives):
            progress = 100.0
            logger.info("[PROGRESS_BAR_FIX] Emit finale batch senza archivi rilevato: imposto progresso al 100%")
        elif index < total_images:
            task_progress = (index / total_images) * image_processing_weight
            step_progress = (step / total_steps) * (1 / total_images) * image_processing_weight
            progress = (task_progress + step_progress) * 100
        else:
            archive_index = index - total_images
            if total_archives > 0:
                task_progress = image_processing_weight + (archive_index / total_archives) * archiving_weight
                step_progress = (step / total_steps) * (1 / total_archives) * archiving_weight
            else:
                task_progress = image_processing_weight
                step_progress = 0
            progress = (task_progress + step_progress) * 100

        progress = min(progress, 100.0)
        self.progress_bar.setValue(int(progress))

        if int(progress) >= 100:
            logger.info(f"[PROGRESS_BAR_FIX] Progresso raggiunto 100% (valore: {progress:.2f})")
            QTimer.singleShot(UI_REFRESH_DELAY_MS, self._force_hide_progress_bar)

    def _force_hide_progress_bar(self):
        """Forza la chiusura della barra di progresso"""
        if self.progress_bar.isVisible():
            logger.info("[PROGRESS_BAR_FIX] Forzando la chiusura della barra di progresso")
            self._enable_batch_buttons()
            if hasattr(self, '_batch_completed_shown') and not self._batch_completed_shown:
                from app.ui.messages import Messages
                Messages.show_translation_complete(self)
                self._batch_completed_shown = True

    def clear_rectangles_all_pages(self):
        from loguru import logger
        logger.info(f"[DEBUG] clear_rectangles_all_pages chiamato, image_files={len(self.image_files)}")

        # Limita la pulizia alle pagine DAVVERO elaborate dal batch: prima veniva
        # azzerata la geometria (posizione/size/rotazione/shape_type) di tutte le
        # pagine, anche di quelle mai toccate, e la forma ellisse era
        # irreversibilmente persa.
        processed = getattr(self, '_images_updated_visually', None)
        total_images = getattr(self, '_total_images_in_batch', None)

        original_index = self.curr_img_idx
        for idx, image_path in enumerate(self.image_files):
            if processed is not None and idx not in processed:
                # Pagina non elaborata da questo batch: non toccarla.
                continue

            if image_path in self.image_states:
                state = self.image_states[image_path]
                if 'viewer_state' in state:
                    state['viewer_state']['rectangles'] = []
                    state['viewer_state']['overlays_hidden'] = True
                logger.info(f"[DEBUG] Pulito stato per {os.path.basename(image_path)}")

            if idx == self.curr_img_idx:
                self.image_viewer.clear_rectangles(page_switch=True)

        self.curr_img_idx = original_index
        logger.info("[DEBUG] clear_rectangles_all_pages completato")

        if processed is not None and total_images is not None and len(processed) < total_images:
            # Batch parziale (alcune pagine saltate): messaggio piu' onesto.
            MMessage.info(
                text=self.tr(f"Caselle di testo rimosse su {len(processed)} pagine elaborate"),
                parent=self, duration=3, closable=False)
        else:
            MMessage.success(
                text=self.tr("Caselle di testo rimosse su tutte le pagine"),
                parent=self, duration=3, closable=False)
