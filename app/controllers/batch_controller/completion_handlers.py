"""
Completion handlers mixin for BatchMixin.

Handles callbacks when batch operations complete.
"""
import logging
from PySide6.QtCore import QTimer

from app.controllers.batch_controller.action_gate import (
    BATCH_ACTION_DETECT_ALL,
    BATCH_ACTION_TRANSLATE_ALL,
    BATCH_ACTION_SBIANCHETTA,
)
from app.ui.dayu_widgets.message import MMessage
from app.controllers.text_edits_sync import refresh_text_edits_for_current_block
from constants import UI_REFRESH_DELAY_MS

logger = logging.getLogger(__name__)


class CompletionHandlersMixin:
    """Callbacks for batch operation completion."""

    def _batch_failed(self) -> bool:
        """True se il worker ha sollevato un'eccezione.

        GenericWorker emette 'error' e poi 'finished': senza questo controllo i
        callback mostravano "Traduzione Completata" / "completato con successo"
        anche dopo un crash.
        """
        return bool(getattr(self, '_batch_error', False))

    def _is_batch_cancelled(self) -> bool:
        """Verifica se il batch è stato cancellato."""
        if hasattr(self, '_cancellation_manager') and self._cancellation_manager:
            return self._cancellation_manager.check()
        return False

    def on_batch_process_finished(self):
        from loguru import logger
        logger.info("[DEBUG] on_batch_process_finished CHIAMATO")
        logger.info("[PROGRESS_BAR_FIX] Callback on_batch_process_finished chiamato")

        if self._batch_failed():
            logger.warning("[BATCH] Processo terminato con errore: nessun messaggio di successo")
            return

        if hasattr(self, 'stop_gpu_monitor'):
            self.stop_gpu_monitor()

        if self._is_batch_cancelled():
            logger.info("[CANCELLATION] Batch process interrotto dall'utente")
            self._handle_cancelled_batch_cleanup()
            return

        QTimer.singleShot(UI_REFRESH_DELAY_MS, self._delayed_reset_translate_flag)

        if hasattr(self, '_safety_timer') and self._safety_timer.isActive():
            self._safety_timer.stop()
            logger.info("[PROGRESS_BAR_FIX] Timer di sicurezza fermato")

        self.progress_bar.setVisible(False)
        if hasattr(self, "image_viewer") and self.image_viewer:
            self.image_viewer.clear_text_item_markers()
            self.image_viewer.clear_rect_item_markers()
        self.clear_rectangles_all_pages()
        if self.curr_img_idx >= 0 and self.curr_img_idx < len(self.image_files):
            current_image = self.image_files[self.curr_img_idx]
            if current_image in self.image_states and 'blk_list' in self.image_states[current_image]:
                self.blk_list = self.image_states[current_image]['blk_list']
                self._link_text_items_to_blocks()
                refresh_text_edits_for_current_block(self)
        self._mark_batch_action_completed(BATCH_ACTION_TRANSLATE_ALL)
        self.translate_button.setEnabled(False)
        self.detect_batch_button.setEnabled(not self._is_batch_action_completed(BATCH_ACTION_DETECT_ALL))
        self.set_tool('pan')
        if hasattr(self, 'pan_button'):
            self.pan_button.setFocus()
        
        if hasattr(self, 'cancel_batch_button'):
            self.cancel_batch_button.setVisible(False)
            self.cancel_batch_button.setEnabled(False)
        
        self._batch_completed_shown = True

        from app.ui.messages import Messages
        Messages.show_translation_complete(self)

        logger.info("[PROGRESS_BAR_FIX] Batch process completato correttamente")

    def on_semi_auto_batch_finished(self):
        """Callback speciale per la modalità semi-automatica che ripristina image_files"""
        from loguru import logger
        logger.info("[DEBUG] on_semi_auto_batch_finished CHIAMATO")
        logger.info("[SEMI_AUTO_MODE] Callback on_semi_auto_batch_finished chiamato")

        if self._batch_failed():
            logger.warning("[SEMI_AUTO_MODE] Processo terminato con errore: nessun messaggio di successo")
            return

        if hasattr(self, 'stop_gpu_monitor'):
            self.stop_gpu_monitor()

        if self._is_batch_cancelled():
            logger.info("[CANCELLATION] Batch semi-auto interrotto dall'utente")
            if hasattr(self, '_original_image_files'):
                self.image_files = self._original_image_files.copy()
                delattr(self, '_original_image_files')
            self._handle_cancelled_batch_cleanup()
            return

        if hasattr(self, '_original_image_files'):
            self.image_files = self._original_image_files.copy()
            delattr(self, '_original_image_files')
            logger.info(f"Lista immagini ripristinata: {len(self.image_files)} immagini totali")

        QTimer.singleShot(UI_REFRESH_DELAY_MS, self._delayed_reset_translate_flag)

        if hasattr(self, '_safety_timer') and self._safety_timer.isActive():
            self._safety_timer.stop()
            logger.info("[SEMI_AUTO_MODE] Timer di sicurezza fermato")

        self.progress_bar.setVisible(False)
        if hasattr(self, "image_viewer") and self.image_viewer:
            self.image_viewer.clear_text_item_markers()
            self.image_viewer.clear_rect_item_markers()
        self.clear_rectangles_all_pages()
        if self.curr_img_idx >= 0 and self.curr_img_idx < len(self.image_files):
            current_image = self.image_files[self.curr_img_idx]
            if current_image in self.image_states and 'blk_list' in self.image_states[current_image]:
                self.blk_list = self.image_states[current_image]['blk_list']
                self._link_text_items_to_blocks()
                refresh_text_edits_for_current_block(self)
        self._mark_batch_action_completed(BATCH_ACTION_TRANSLATE_ALL)
        self.translate_button.setEnabled(False)
        self.detect_batch_button.setEnabled(not self._is_batch_action_completed(BATCH_ACTION_DETECT_ALL))
        self.set_tool('pan')
        if hasattr(self, 'pan_button'):
            self.pan_button.setFocus()
        
        if hasattr(self, 'cancel_batch_button'):
            self.cancel_batch_button.setVisible(False)
            self.cancel_batch_button.setEnabled(False)
        
        self._batch_completed_shown = True

        from app.ui.messages import Messages
        Messages.show_info(
            self,
            "Traduzione Completata",
            "L'immagine corrente è stata tradotta con successo utilizzando le caselle selezionate."
        )

        logger.info("[SEMI_AUTO_MODE] Processo semi-automatico completato correttamente")
        logger.info("═══════════════════════════════════════════════════")
        logger.info("Processo Semi-Automatico Completato!")
        logger.info("═══════════════════════════════════════════════════")

    def on_detect_batch_finished(self, results):
        """Callback chiamato alla fine del rilevamento batch"""
        self._mark_batch_action_completed(BATCH_ACTION_DETECT_ALL)
        self._enable_batch_buttons()
        self.enable_hbutton_group()
        self.loading.setVisible(False)

        try:
            from modules.audio_notifications import get_audio_system
            audio_system = get_audio_system()
            if audio_system and audio_system.enabled:
                audio_system._play_completion_sound('detect_all')
        except Exception as e:
            logging.warning(f"Impossibile riprodurre suono detect_all: {e}")

        if self.curr_img_idx >= 0 and self.curr_img_idx < len(self.image_files):
            current_image = self.image_files[self.curr_img_idx]
            if current_image in results:
                self.blk_list = results[current_image]
                if current_image in self.image_states:
                    self.image_states[current_image]['blk_list'] = self.blk_list
                    self.image_states[current_image]['text_blocks'] = self.blk_list
                self.clear_multi_selection()
                refresh_text_edits_for_current_block(self)
                self.pipeline.load_box_coords(self.blk_list)
            self._link_text_items_to_blocks()

        count = sum(len(blks) for blk_list in results.values() for blks in [blk_list] if blk_list)
        MMessage.info(
            text=f"Rilevamento batch completato.\nTrovate {count} caselle in {len(results)} immagini.",
            parent=self,
            duration=3
        )
        logger.info("[DETECT_BATCH] Processo rilevamento batch terminato")

    def on_sbianchetta_finished(self):
        """Callback chiamato alla fine del processo sbianchetta."""
        if self._batch_failed():
            logger.warning("[SBIANCHETTA] Processo terminato con errore: nessun messaggio di successo")
            self._in_translate_process = False
            if hasattr(self, '_safety_timer') and self._safety_timer.isActive():
                self._safety_timer.stop()
            self.progress_bar.setVisible(False)
            self._enable_batch_buttons()
            return

        if self._is_batch_cancelled():
            logger.info("[CANCELLATION] Sbianchetta batch interrotto dall'utente")
            self._handle_cancelled_batch_cleanup()
            return

        self._in_translate_process = False
        logger.info("[SBIANCHETTA] Processo Sbianchetta completato - flag confermato False")

        self._mark_batch_action_completed(BATCH_ACTION_SBIANCHETTA)

        if hasattr(self, '_safety_timer') and self._safety_timer.isActive():
            self._safety_timer.stop()

        self.progress_bar.setVisible(False)
        self._enable_batch_buttons()

        if hasattr(self, 'cancel_batch_button'):
            self.cancel_batch_button.setVisible(False)
            self.cancel_batch_button.setEnabled(False)

        if hasattr(self, 'sbianchetta_button'):
            self.sbianchetta_button.setEnabled(
                not self._is_batch_action_completed(BATCH_ACTION_SBIANCHETTA)
            )

        from app.ui.messages import Messages
        Messages.show_info(
            self, "Sbianchetta Completata",
            "Il processo sbianchetta è stato completato con successo.",
        )
        logger.info("[SBIANCHETTA] Processo sbianchetta terminato")

    def _handle_cancelled_batch_cleanup(self):
        """
        Pulizia finale dopo la cancellazione del batch.
        """
        logger.info("[CANCELLATION] Eseguendo pulizia post-cancellazione")

        if hasattr(self, '_finalize_cancellation'):
            processed = 0
            total = 0
            if hasattr(self, '_cancellation_manager') and self._cancellation_manager:
                processed = self._cancellation_manager.get_cancellation_info().get('processed_items', 0)
                total = self._cancellation_manager.get_cancellation_info().get('total_items', 0)
            self._finalize_cancellation(success=True, message="Elaborazione batch interrotta")
        else:
            self._enable_batch_buttons()
            self.enable_hbutton_group()
            if hasattr(self, 'cancel_batch_button'):
                self.cancel_batch_button.setVisible(False)
                self.cancel_batch_button.setEnabled(False)
            self._in_translate_process = False

            if hasattr(self, '_safety_timer') and self._safety_timer.isActive():
                self._safety_timer.stop()

        logger.info("[CANCELLATION] Pulizia post-cancellazione completata")

    def _delayed_reset_translate_flag(self):
        """Reset ritardato del flag _in_translate_process"""
        self._in_translate_process = False
        logger.info("[TRANSLATE] Processo Translate completato - flag resettato (ritardato)")

    def _on_all_images_visually_updated(self):
        """Chiamato quando tutte le immagini del batch sono state aggiornate visualmente"""
        logger.info("Tutte le immagini sono ora visualmente aggiornate - il pulsante 'Tutte le immagini' può essere abilitato")
