"""
Batch processing mixin for BatchMixin.

Handles starting batch processes for translation and similar operations.
"""
import logging
import time
from PySide6 import QtCore

from app.controllers.batch_controller.action_gate import BATCH_ACTION_TRANSLATE_ALL
from constants import BATCH_SAFETY_TIMEOUT_MS
from modules.utils.pipeline_utils import validate_settings

logger = logging.getLogger(__name__)


class BatchProcessingMixin:
    """Batch processing start logic."""

    def start_batch_process(self, force_blk_check=True):
        if not self.image_files:
            return
        if not self._can_run_batch_action(BATCH_ACTION_TRANSLATE_ALL):
            return
        if self.curr_img_idx >= 0:
            self._sync_blocks_with_ui()
            self._link_text_items_to_blocks()

        self._start_full_auto_batch(force_blk_check)

    def _initialize_batch_cancellation(self):
        """Inizializza il sistema di cancellazione per un nuovo batch."""
        from app.controllers.batch_controller.cancellation_manager import get_cancellation_manager

        self._cancellation_manager = get_cancellation_manager()
        self._cancellation_manager.reset()
        self._cancellation_manager.timeout_seconds = 5.0

        self._cancellation_start_time = None
        self._cancellation_in_progress = False

    def cancel_batch_operation(self):
        """
        Richiede la cancellazione dell'operazione batch in corso.
        
        Questo metodo viene chiamato quando l'utente clicca sul pulsante 'Annulla'.
        Implementa:
        1. Interruzione immediata del flag di cancellazione
        2. Salvataggio dello stato corrente
        3. Notifica all'utente
        4. Timeout di 5 secondi per completamento
        """
        logger.info("[CANCELLATION] ===========================================")
        logger.info("[CANCELLATION] CANCELLAZIONE RICHIESTA DALL'UTENTE")
        logger.info("[CANCELLATION] ===========================================")
        
        if not hasattr(self, '_cancellation_manager'):
            logger.warning("[CANCELLATION] Sistema di cancellazione non inizializzato")
            return
        
        self._cancellation_start_time = time.time()
        self._cancellation_in_progress = True
        
        requested = self._cancellation_manager.request_cancellation(
            reason="User clicked Cancel button"
        )
        
        if requested:
            logger.info("[CANCELLATION] Flag di cancellazione impostato")
            
            self.cancel_batch_button.setEnabled(False)
            self.cancel_batch_button.setText(self.tr("Stopping..."))
            
            self._save_cancellation_checkpoint()
            
            self._start_cancellation_timeout()
        else:
            logger.info("[CANCELLATION] Cancellazione già richiesta")

    def _save_cancellation_checkpoint(self):
        """Salva lo stato corrente prima dell'interruzione.

        Non esiste piu' il PartialStateManager: scriveva file di stato che
        nessuno rileggeva mai (il percorso di ripresa non e' mai stato
        collegato alla UI). Salvava pero' un messaggio di log che diceva
        "Stato parziale salvato" senza che nulla venisse scritto.
        """
        logger.info(
            "[CANCELLATION] Batch interrotto dall'utente. "
            "Lo stato parziale non viene ripreso: il batch riparte da capo."
        )

    def _start_cancellation_timeout(self):
        """Avvia il timer di timeout per la cancellazione."""
        if hasattr(self, '_cancellation_timer') and self._cancellation_timer.isActive():
            self._cancellation_timer.stop()
        
        self._cancellation_timer = QtCore.QTimer()
        self._cancellation_timer.setSingleShot(True)
        self._cancellation_timer.timeout.connect(self._on_cancellation_timeout)
        self._cancellation_timer.start(5000)
        
        logger.info("[CANCELLATION] Timer di timeout avviato (5 secondi)")

    def _on_cancellation_timeout(self):
        """Gestisce il timeout della cancellazione."""
        elapsed = time.time() - self._cancellation_start_time if self._cancellation_start_time else 0
        
        logger.warning(
            f"[CANCELLATION] TIMEOUT: Cancellazione non completata in {elapsed:.1f}s"
        )
        
        self._cancellation_manager.complete_cancellation(success=False)
        
        self._finalize_cancellation(success=False, message="Cancellazione terminata per timeout")

    def _finalize_cancellation(self, success: bool, message: str):
        """
        Finalizza la cancellazione e ripristina l'interfaccia.
        
        Args:
            success: True se la cancellazione è avvenuta con successo
            message: Messaggio da mostrare all'utente
        """
        elapsed = 0
        if self._cancellation_start_time:
            elapsed = time.time() - self._cancellation_start_time
        
        logger.info(f"[CANCELLATION] Finalizzazione: {message} (elapsed: {elapsed:.2f}s)")
        
        if hasattr(self, '_cancellation_timer') and self._cancellation_timer.isActive():
            self._cancellation_timer.stop()
        
        self._cancellation_manager.complete_cancellation(success=success)
        
        self._cancellation_in_progress = False
        
        self._enable_batch_buttons()
        
        self.cancel_batch_button.setVisible(False)
        self.cancel_batch_button.setEnabled(False)
        self.cancel_batch_button.setText(self.tr("Cancel"))
        
        self._in_translate_process = False
        
        if hasattr(self, '_safety_timer') and self._safety_timer.isActive():
            self._safety_timer.stop()
        
        info = self._cancellation_manager.get_cancellation_info()
        processed = info.get('processed_items', 0)
        total = info.get('total_items', 0)
        
        logger.info(
            f"[CANCELLATION] ==========================================="
        )
        logger.info(f"[CANCELLATION] OPERAZIONE INTERROTTA")
        logger.info(f"[CANCELLATION] Immagini processate: {processed}/{total}")
        logger.info(f"[CANCELLATION] Tempo trascorso: {elapsed:.2f}s")
        logger.info(f"[CANCELLATION] Stato finale: {info.get('state', 'unknown')}")
        logger.info(
            f"[CANCELLATION] ==========================================="
        )
        
        from app.ui.dayu_widgets.message import MMessage
        from app.ui.messages import Messages
        
        if success:
            MMessage.warning(
                text=f"{message}\n\nImmagini processate: {processed}/{total}",
                parent=self,
                duration=5,
                closable=True
            )
        else:
            Messages.show_warning(
                self,
                self.tr("Cancellazione"),
                f"{message}\n\nImmagini processate: {processed}/{total}"
            )

    def _enable_cancel_button(self):
        """Abilita il pulsante Annulla durante il batch."""
        if hasattr(self, 'cancel_batch_button'):
            self.cancel_batch_button.setVisible(True)
            self.cancel_batch_button.setEnabled(True)

    def _disable_cancel_button(self):
        """Disabilita il pulsante Annulla."""
        if hasattr(self, 'cancel_batch_button'):
            self.cancel_batch_button.setEnabled(False)

    def _start_semi_auto_batch(self):
        """Avvia la modalità semi-automatica per una singola immagine"""
        logger.info("═══════════════════════════════════════════════════")
        logger.info("Modalità Semi-Automatica Attivata!")
        logger.info(f"Immagine corrente: {self.curr_img_idx}")
        logger.info(f"Caselle filtrate dall'utente: {len(self.blk_list)}")
        logger.info("═══════════════════════════════════════════════════")

        self._initialize_batch_cancellation()
        self._enable_cancel_button()

        # Il dropdown e' l'unica fonte di verita': sincronizza lo stato prima
        # di validare, altrimenti la validazione userebbe lingue obsolete.
        if hasattr(self, 'set_src_trg_all'):
            self.set_src_trg_all()
        current_image_path = self.image_files[self.curr_img_idx]
        source_lang = self.s_combo.currentText()
        target_lang = self.t_combo.currentText()

        if not validate_settings(self, source_lang, target_lang):
            self._finalize_cancellation(success=False, message="Validazione impostazioni fallita")
            return

        self.save_current_image_state()
        logger.info(f"Stato salvato con {len(self.blk_list)} caselle")

        self._original_image_files = self.image_files.copy()
        self.image_files = [current_image_path]

        self.translate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._batch_completed_shown = False
        self._in_translate_process = True
        if hasattr(self, 'start_gpu_monitor'):
            self.start_gpu_monitor()
        logger.info("Processo Semi-Automatico avviato")

        self._images_processed_count = 0
        self._images_updated_visually.clear()
        self._total_images_in_batch = 1
        logger.info("[SEMI_AUTO_MODE] Batch process per 1 immagine (modalità intermedia)")

        self._setup_safety_timer()

        # Ottimizzazione Multithreading: Limitiamo i worker concorrenti per operazioni pesanti (GPU/CPU)
        # per evitare deadlock o saturazione memoria.
        self.threadpool.setMaxThreadCount(max(2, QtCore.QThread.idealThreadCount() // 2))
        
        logger.info(f"Avvio batch_process distribuito su {self.threadpool.maxThreadCount()} worker")

        # Congela lingua + render settings qui, sul thread GUI: il worker non
        # deve leggere i widget Qt (QFont/QTextDocument sono GUI-thread-only).
        self.pipeline.cache_ui_snapshot()

        self.run_threaded(
            lambda: self.pipeline.batch_process(
                existing_blk_list=self.blk_list.copy(), skip_detection=True),
            None,
            self.default_error_handler,
            self.on_semi_auto_batch_finished
        )

    def _start_full_auto_batch(self, force_blk_check=True):
        """Avvia la modalità batch completo automatico"""
        logger.info("Modalità Batch Completo Automatico")

        self._initialize_batch_cancellation()
        self._enable_cancel_button()

        # Il dropdown e' l'unica fonte di verita': sincronizza lo stato prima
        # di validare, altrimenti la validazione userebbe lingue obsolete.
        if hasattr(self, 'set_src_trg_all'):
            self.set_src_trg_all()
        for image_path in self.image_files:
            source_lang = self.s_combo.currentText()
            target_lang = self.t_combo.currentText()
            if not validate_settings(self, source_lang, target_lang):
                self._finalize_cancellation(success=False, message="Validazione impostazioni fallita")
                return

        images_with_blocks = None
        if force_blk_check:
            self.save_current_image_state()
            images_with_blocks = self._check_existing_blocks_batch()
            logger.info(f"[BATCH_OPTIMIZATION] {len(images_with_blocks)} immagini hanno già caselle di testo")

        self.translate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._batch_completed_shown = False
        self._in_translate_process = True
        if hasattr(self, 'start_gpu_monitor'):
            self.start_gpu_monitor()
        logger.info("Processo Translate avviato - flag impostato")

        self._images_processed_count = 0
        self._images_updated_visually.clear()
        self._total_images_in_batch = len(self.image_files)
        logger.info(f"[BATCH_TRACKING] Iniziato batch process per {self._total_images_in_batch} immagini")

        self._setup_safety_timer()

        # Ottimizzazione Multithreading: Bilanciamento carico per batch completo
        self.threadpool.setMaxThreadCount(max(2, QtCore.QThread.idealThreadCount() // 2))

        skip_detection = images_with_blocks is not None and len(images_with_blocks) > 0
        existing_blk_list = None
        logger.debug(f"[BATCH_SKIP_LOGIC] skip_detection={skip_detection}, existing_blk_list={'presente' if existing_blk_list else 'None'}")

        # Snapshot della UI catturato sul thread GUI (vedi _start_semi_auto_batch).
        self.pipeline.cache_ui_snapshot()

        self.run_threaded(
            lambda: self.pipeline.batch_process(
                existing_blk_list=existing_blk_list, skip_detection=skip_detection),
            None,
            self.default_error_handler,
            self.on_batch_process_finished
        )

    def _setup_safety_timer(self):
        """Configura il timer di sicurezza"""
        self._safety_timer = QtCore.QTimer()
        self._safety_timer.setSingleShot(True)
        self._safety_timer.timeout.connect(self._safety_timeout_handler)
        self._safety_timer.start(BATCH_SAFETY_TIMEOUT_MS)
