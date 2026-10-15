from PySide6 import QtWidgets, QtCore, QtGui
from ..shortcut_manager import format_shortcut_for_display, normalize_shortcut_text

_STYLE_IDLE = """
    ShortcutEditWidget {
        background-color: #1a1a1a;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
        padding: 5px;
        color: #3498db;
        font-weight: bold;
    }
    ShortcutEditWidget:focus {
        border-color: #3498db;
        background-color: #2a2a2a;
    }
"""

_STYLE_RECORDING = """
    ShortcutEditWidget {
        background-color: #1e2a3a;
        border: 2px solid #3498db;
        border-radius: 4px;
        padding: 5px;
        color: #5dade2;
        font-weight: bold;
    }
"""


class ShortcutEditWidget(QtWidgets.QLineEdit):
    shortcutChanged = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setPlaceholderText(self.tr("Clicca e premi un tasto..."))
        self._recording = False
        self._previous_text = ""
        self.setStyleSheet(_STYLE_IDLE)

    # ------------------------------------------------------------------
    # Stato di registrazione
    # ------------------------------------------------------------------
    def _enter_recording(self):
        if not self._recording:
            self._recording = True
            self._previous_text = self.text()
            self.setPlaceholderText(self.tr("Premi un tasto... (ESC per annullare)"))
            self.setStyleSheet(_STYLE_RECORDING)

    def _leave_recording(self, accept: bool = True):
        if self._recording:
            self._recording = False
            self.setPlaceholderText(self.tr("Clicca e premi un tasto..."))
            self.setStyleSheet(_STYLE_IDLE)
            if not accept:
                # Ripristina il testo precedente senza emettere il segnale
                self.blockSignals(True)
                self.setText(self._previous_text)
                self.blockSignals(False)

    # ------------------------------------------------------------------
    # Override eventi Qt
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Entra in modalità registrazione al click."""
        self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        self._enter_recording()
        # NON chiamare super() per evitare che QLineEdit gestisca il cursore
        event.accept()

    def focusInEvent(self, event: QtGui.QFocusEvent):
        super().focusInEvent(event)

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        # Se perde il focus mentre stava registrando, annulla
        self._leave_recording(accept=False)
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        # Accetta sempre l'evento per bloccare la propagazione al parent
        event.accept()

        key = event.key()
        modifiers = event.modifiers()

        # ESC: annulla la registrazione e ripristina il valore precedente
        if key == QtCore.Qt.Key.Key_Escape:
            self._leave_recording(accept=False)
            self.clearFocus()
            return

        # Backspace senza modificatori: cancella la shortcut assegnata.
        # Delete deve restare assegnabile, anche per shortcut come Shift+Delete.
        if (
            key == QtCore.Qt.Key.Key_Backspace
            and modifiers == QtCore.Qt.KeyboardModifier.NoModifier
        ):
            self.setText("")
            self.shortcutChanged.emit("")
            self._leave_recording(accept=True)
            return

        # Tasti modificatori da soli: non fare nulla
        if key in (
            QtCore.Qt.Key.Key_Control,
            QtCore.Qt.Key.Key_Shift,
            QtCore.Qt.Key.Key_Alt,
            QtCore.Qt.Key.Key_Meta,
            QtCore.Qt.Key.Key_AltGr,
        ):
            return

        # Se non siamo in modalità registrazione, un click attiva la registrazione
        # ma il tasto corrente diventa la nuova shortcut (comportamento intuitivo)
        if not self._recording:
            self._enter_recording()

        # Costruisce la sequenza con i modificatori correnti
        seq = QtGui.QKeySequence(modifiers.value | key)
        text = seq.toString()
        if text:
            display_text = format_shortcut_for_display(normalize_shortcut_text(text))
            self.setText(display_text)
            self.shortcutChanged.emit(display_text)
            self._leave_recording(accept=True)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        # Blocca anche il keyRelease per evitare propagazione indesiderata
        event.accept()