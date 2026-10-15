from PySide6 import QtCore, QtWidgets

from app.ui.dayu_widgets import MLabel, MPushButton, MTextEdit


class GvbPromptDialog(QtWidgets.QDialog):
    prompt_saved = QtCore.Signal(str)

    def __init__(self, initial_text: str, parent=None):
        super().__init__(parent)
        self._initial_text = initial_text or ""
        self._setup_ui()

    def prompt_text(self) -> str:
        return self._prompt_input.toPlainText()

    def _setup_ui(self) -> None:
        self.setWindowTitle("PROMPT")
        self.setModal(True)
        self.setMinimumSize(520, 320)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = MLabel("PROMPT").h3()
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._prompt_input = MTextEdit()
        self._prompt_input.setPlaceholderText("Scrivi qui il prompt da inviare a Gemini insieme all'immagine…")
        self._prompt_input.setPlainText(self._initial_text)
        layout.addWidget(self._prompt_input)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()

        cancel_button = MPushButton("Annulla")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)

        save_button = MPushButton("Salva")
        save_button.setDefault(True)
        save_button.clicked.connect(self._on_save)
        buttons.addWidget(save_button)

        layout.addLayout(buttons)

    def _on_save(self) -> None:
        self.prompt_saved.emit(self.prompt_text())
        self.accept()
