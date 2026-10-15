"""
Gating helpers for batch actions that should run once per loaded file/project.
"""
import logging

from app.ui.dayu_widgets.message import MMessage

logger = logging.getLogger(__name__)

BATCH_ACTION_DETECT_ALL = "detect_all"
BATCH_ACTION_TRANSLATE_ALL = "translate_all"
BATCH_ACTION_SBIANCHETTA = "sbianchetta"

_ACTION_LABELS = {
    BATCH_ACTION_DETECT_ALL: "Rileva Tutto",
    BATCH_ACTION_TRANSLATE_ALL: "Traduci Tutto",
    BATCH_ACTION_SBIANCHETTA: "Sbianchetta",
}


class BatchActionGateMixin:
    """Gestisce il blocco delle azioni batch già completate nel file corrente."""

    def _ensure_batch_action_gate_state(self):
        if not hasattr(self, "_completed_batch_actions") or self._completed_batch_actions is None:
            self._completed_batch_actions = set()

    def reset_batch_action_gate(self):
        """Sblocca le azioni batch quando viene aperto un nuovo file/progetto."""
        self._ensure_batch_action_gate_state()
        self._completed_batch_actions.clear()
        logger.info("[BATCH_ACTION_GATE] Reset completato per nuovo file/progetto")
        self._apply_batch_action_gate()

    def _mark_batch_action_completed(self, action_name: str):
        """Segna l'azione come completata per il file corrente."""
        self._ensure_batch_action_gate_state()
        self._completed_batch_actions.add(action_name)
        logger.info("[BATCH_ACTION_GATE] Azione completata: %s", action_name)
        self._apply_batch_action_gate()

    def _is_batch_action_completed(self, action_name: str) -> bool:
        self._ensure_batch_action_gate_state()
        return action_name in self._completed_batch_actions

    def _can_run_batch_action(self, action_name: str, show_message: bool = True) -> bool:
        """Verifica se l'azione puo' essere rieseguita nel file corrente."""
        if not self._is_batch_action_completed(action_name):
            return True

        if show_message:
            action_label = _ACTION_LABELS.get(action_name, action_name)
            MMessage.info(
                text=(
                    f"{action_label} e' gia' stato completato per il file corrente.\n"
                    "Apri un nuovo file o progetto per eseguirlo di nuovo."
                ),
                parent=self,
                duration=4,
                closable=True,
            )
        logger.info("[BATCH_ACTION_GATE] Riesecuzione bloccata: %s", action_name)
        return False

    def _apply_batch_action_gate(self):
        """Aggiorna lo stato enabled dei pulsanti batch soggetti a gating."""
        self._ensure_batch_action_gate_state()

        if hasattr(self, "detect_batch_button"):
            self.detect_batch_button.setEnabled(
                not self._is_batch_action_completed(BATCH_ACTION_DETECT_ALL)
            )
        if hasattr(self, "translate_button"):
            self.translate_button.setEnabled(
                not self._is_batch_action_completed(BATCH_ACTION_TRANSLATE_ALL)
            )
        if hasattr(self, "sbianchetta_button"):
            self.sbianchetta_button.setEnabled(
                not self._is_batch_action_completed(BATCH_ACTION_SBIANCHETTA)
            )
