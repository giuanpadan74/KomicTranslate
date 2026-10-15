"""
Image handlers mixin for BatchMixin.

Handles image updates, processing callbacks, and batch operations.
"""
import logging

import numpy as np
from PySide6.QtCore import QCoreApplication

from app.controllers.batch_controller.action_gate import (
    BATCH_ACTION_DETECT_ALL,
    BATCH_ACTION_SBIANCHETTA,
)
from app.ui.dayu_widgets.message import MMessage
from modules.utils.pipeline_utils import validate_settings

logger = logging.getLogger(__name__)


class ImageHandlersMixin:
    """Handlers for image updates and batch image operations."""

    def _track_batch_visual_update(self, image_index: int, image_path: str):
        """Registra un aggiornamento visivo completato per il gating del salvataggio batch."""
        if not hasattr(self, '_images_updated_visually') or not hasattr(self, '_total_images_in_batch'):
            return
        if self._total_images_in_batch <= 0:
            return

        self._images_updated_visually.add(image_index)
        logger.info(
            "[BATCH_SAVE_GATE] Aggiornamento visivo registrato per %s (%s/%s)",
            image_path,
            len(self._images_updated_visually),
            self._total_images_in_batch,
        )

        if len(self._images_updated_visually) >= self._total_images_in_batch:
            logger.info("[BATCH_SAVE_GATE] Tutte le immagini del batch risultano aggiornate visivamente")
            self._on_all_images_visually_updated()

    def on_image_processed(self, index: int, image: np.ndarray, image_path: str):
        from app.ui.commands.image import SetImageCommand
        if index == self.curr_img_idx:
            self.set_cv2_image(image)
        else:
            command = SetImageCommand(self, image_path, image, False)
            self.undo_group.activeStack().push(command)
            self.image_data[image_path] = image
        self._track_batch_visual_update(index, image_path)

    def on_image_skipped(self, image_path: str, skip_reason: str, error: str):
        message = {
            "Text Blocks": QCoreApplication.translate(
                'Messages', 'No Text Blocks Detected.\nSkipping:') + f" {image_path}\n{error}",
            "OCR": QCoreApplication.translate(
                'Messages', 'Could not OCR detected text.\nSkipping:') + f" {image_path}\n{error}",
            "Translator": QCoreApplication.translate(
                'Messages', 'Could not get translations.\nSkipping:') + f" {image_path}\n{error}"
        }
        text = message.get(skip_reason, f"Unknown skip reason: {skip_reason}. Error: {error}")
        MMessage.info(text=text, parent=self, duration=5, closable=True)

    def detect_batch(self):
        """Avvia il rilevamento batch delle caselle di testo"""
        if not self.image_files:
            return
        if not self._can_run_batch_action(BATCH_ACTION_DETECT_ALL):
            return

        self.disable_hbutton_group()
        self.detect_batch_button.setEnabled(False)
        self.translate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._in_translate_process = False
        logger.info("[DETECT_BATCH] Processo Rilevamento Batch avviato")

        self.run_threaded(
            self.pipeline.detect_all_text_boxes,
            self.on_detect_batch_finished,
            self.default_error_handler,
            None
        )

    def sbianchetta(self, force_blk_check: bool = True):
        """Avvia il processo sbianchetta per tutte le immagini."""
        if not self.image_files:
            return
        if not self._can_run_batch_action(BATCH_ACTION_SBIANCHETTA):
            return
        if self.curr_img_idx >= 0:
            self._sync_blocks_with_ui()
            self._link_text_items_to_blocks()

        # Il dropdown e' l'unica fonte di verita': sincronizza prima di
        # validare per non usare lingue obsolete dallo stato salvato.
        if hasattr(self, 'set_src_trg_all'):
            self.set_src_trg_all()
        for image_path in self.image_files:
            source_lang = self.s_combo.currentText()
            target_lang = self.t_combo.currentText()
            if not validate_settings(self, source_lang, target_lang):
                return

        if hasattr(self, "_initialize_batch_cancellation"):
            self._initialize_batch_cancellation()
            self._enable_cancel_button()

        images_with_blocks = None
        if force_blk_check:
            self.save_current_image_state()
            images_with_blocks = self._check_existing_blocks_batch()
            logger.info(
                "[SBIANCHETTA_OPTIMIZATION] %s immagini hanno già caselle di testo",
                len(images_with_blocks),
            )

        self.sbianchetta_button.setEnabled(False)
        self.translate_button.setEnabled(False)
        self.detect_batch_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._in_translate_process = False
        logger.info("[SBIANCHETTA] Processo Sbianchetta avviato - flag impostato")

        from app.pipeline_steps.sbianchetta import sbianchetta_batch_process

        # NB: non passare self.blk_list (le caselle della pagina corrente).
        # Veniva usata come fallback per OGNI immagine del batch, quindi ogni
        # pagina veniva sbianchettata con la geometria della prima pagina e il
        # il risultato veniva applicato alle immagini sbagliate.
        # Con existing_blk_list=None ogni immagine usa il proprio stato salvato
        # (lo stesso pattern di batch_processing.py).
        skip_detection = bool(images_with_blocks)
        # Snapshot della UI catturato sul thread GUI prima del dispatch.
        self.pipeline.cache_ui_snapshot()
        self.run_threaded(
            lambda: sbianchetta_batch_process(
                self.pipeline,
                existing_blk_list=None,
                skip_detection=skip_detection,
            ),
            None,
            self.default_error_handler,
            self.on_sbianchetta_finished,
        )
