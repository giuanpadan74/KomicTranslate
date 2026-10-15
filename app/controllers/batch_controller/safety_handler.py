"""
Safety handler mixin for BatchMixin.

Handles timeout safety and Gemini saturation popup.
"""
import logging
import threading
from PySide6 import QtCore, QtWidgets

logger = logging.getLogger(__name__)


class SafetyHandlerMixin:
    """Safety handlers for batch operations."""

    def _safety_timeout_handler(self):
        """Gestisce il timeout di sicurezza per forzare la chiusura della barra di progresso"""
        logger.warning("[PROGRESS_BAR_FIX] TIMEOUT DI SICUREZZA: Forzando la chiusura della barra di progresso dopo 5 minuti")

        if self.progress_bar.isVisible():
            self._enable_batch_buttons()

            if not getattr(self, '_batch_completed_shown', True):
                from app.ui.messages import Messages
                Messages.show_translation_complete(self)
                self._batch_completed_shown = True

            logger.info("[PROGRESS_BAR_FIX] Barra di progresso chiusa tramite timeout di sicurezza")

    @QtCore.Slot()
    def _show_gemini_saturation_popup(self):
        """
        Slot eseguito sul thread GUI. Non chiamare direttamente dal worker.
        Scrive il risultato e rilascia l'evento atteso da handle_gemini_saturation.
        """
        try:
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tr("Geminiamo Saturo"),
                self.tr("gemini.google.com saturo. Cosa vuoi fare?\n\n• Continua con Geminiamo (potrebbe fallire)\n• Riprova (rilascia le credenziali)"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Cancel
            )

            if reply == QtWidgets.QMessageBox.Yes:
                logger.info("[GEMINIAMO_SATURATION] Utente ha scelto il retry")
                self._gemini_saturation_result = 'retry'
            else:
                logger.info("[GEMINIAMO_SATURATION] Utente ha scelto di interrompere")
                self._gemini_saturation_result = 'continue'
        except Exception as e:
            logger.error(f"Errore nel mostrare popup saturazione: {e}")
            self._gemini_saturation_result = 'continue'
        finally:
            evt = getattr(self, '_gemini_saturation_event', None)
            if evt is not None:
                evt.set()

    def handle_gemini_saturation(self):
        """
        Gestisce la saturazione di Geminiamo chiamando un popup sul thread principale.
        Chiamato dal worker thread.
        Ritorna 'retry' o 'continue' basandosi sulla scelta dell'utente.
        """
        logger.warning("[GEMINIAMO_SATURATION] Rilevata saturazione, chiedo all'utente...")

        self._gemini_saturation_result = 'continue'
        self._gemini_saturation_event = threading.Event()

        # Il worker gira in un QThreadPool, che NON ha event loop: il vecchio
        # QTimer.singleShot(0, ...) veniva creato in quel thread e non scattava
        # mai, mentre done_event.wait() non aveva timeout => il batch restava
        # bloccato per sempre (e la UI ferma a "in corso").
        # Ora si posta un metacall sul thread GUI (che ha l'event loop) e si
        # attende con un timeout di sicurezza: nessun blocco infinito possibile.
        try:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_show_gemini_saturation_popup",
                QtCore.Qt.ConnectionType.QueuedConnection,
            )
        except Exception as e:
            logger.error(f"[GEMINIAMO_SATURATION] Impossibile invocare il popup: {e}")
            return 'continue'

        try:
            from constants import BATCH_SAFETY_TIMEOUT_MS
            timeout_ms = BATCH_SAFETY_TIMEOUT_MS
        except Exception:
            timeout_ms = 300000

        if not self._gemini_saturation_event.wait(timeout=timeout_ms / 1000.0):
            logger.error(
                "[GEMINIAMO_SATURATION] Nessuna risposta entro il timeout, proseguo con 'continue'"
            )
            return 'continue'

        return getattr(self, '_gemini_saturation_result', 'continue')
