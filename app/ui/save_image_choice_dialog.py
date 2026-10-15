from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt


class SaveImageChoiceDialog(QtWidgets.QDialog):
    # Scelta di default mostrata all'apertura.
    DEFAULT_SELECTION = "all"

    def __init__(self, page_count, parent=None):
        super().__init__(parent)
        self.page_count = page_count
        self.choice = None
        # Tracciamento esplicito dell'ultima selezione: non ci si affida
        # solo allo stato interno dei radio, che puo' restare incoerente
        # (nessuno o entrambi checked) in particolari condizioni di Qt.
        self._user_selection = None
        self._user_touched = False
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(self.tr("Salva Immagine"))
        self.setModal(True)
        self.setMinimumWidth(420)

        screen_geometry = QtWidgets.QApplication.primaryScreen().geometry()
        max_width = int(screen_geometry.width() * 0.30)
        max_height = int(screen_geometry.height() * 0.30)
        self.setMaximumSize(max_width, max_height)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #242424;
                color: #f2f2f2;
            }
            QLabel#title {
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#subtitle {
                color: rgba(242, 242, 242, 0.75);
            }
            QGroupBox#choices {
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 10px;
                padding: 10px;
                margin-top: 6px;
            }
            QRadioButton {
                padding: 10px 8px;
                border-radius: 8px;
            }
            QRadioButton:hover {
                background-color: rgba(255, 255, 255, 0.06);
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid rgba(255, 255, 255, 0.35);
                background: transparent;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #2ecc71;
                background: #2ecc71;
            }
            QRadioButton:checked {
                color: #2ecc71;
                font-weight: 600;
            }
            QPushButton {
                min-height: 34px;
                padding: 0 14px;
                border-radius: 8px;
            }
            QPushButton#cancel {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.10);
            }
            QPushButton#cancel:hover {
                background-color: rgba(255, 255, 255, 0.12);
            }
            QPushButton#confirm {
                background-color: #2ecc71;
                border: 1px solid #2ecc71;
                color: #0f1a12;
                font-weight: 700;
            }
            QPushButton#confirm:hover {
                background-color: #27c267;
                border: 1px solid #27c267;
            }
            QPushButton#confirm:pressed {
                background-color: #24b860;
                border: 1px solid #24b860;
            }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QtWidgets.QLabel(self.tr("Salva immagine"))
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(
            self.tr(f"Hai {self.page_count} pagine caricate. Come vuoi salvare?")
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        choices = QtWidgets.QGroupBox()
        choices.setObjectName("choices")
        choices_layout = QtWidgets.QVBoxLayout(choices)
        choices_layout.setContentsMargins(10, 10, 10, 10)
        choices_layout.setSpacing(4)

        self.radio_current = QtWidgets.QRadioButton(self.tr("Salva pagina corrente"))
        self.radio_all = QtWidgets.QRadioButton(self.tr("Salva tutte le pagine"))

        self.radio_all.setChecked(True)

        choices_layout.addWidget(self.radio_current)
        choices_layout.addWidget(self.radio_all)
        layout.addWidget(choices)

        # Non usare setAutoExclusive(True) sui singoli radio: l'esclusivita'
        # e' gia' garantita dal parent condiviso e i due meccanismi in
        # conflitto rendevano i radio non flaggabili visivamente.
        # Neppure setFocusPolicy(StrongFocus): su alcuni temi Qt/Windows
        # blocca i click sui radio.
        self.radio_current.toggled.connect(self._on_radio_toggled)
        self.radio_all.toggled.connect(self._on_radio_toggled)

        # Default applicato DOPO aver collegato i segnali, cosi' lo stato
        # di tracciamento resta coerente.
        self._apply_default_selection()

        button_layout = QtWidgets.QHBoxLayout()

        button_layout.addStretch()

        self.cancel_button = QtWidgets.QPushButton(self.tr("Annulla"))
        self.cancel_button.setObjectName("cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.confirm_button = QtWidgets.QPushButton(self.tr("Conferma"))
        self.confirm_button.setObjectName("confirm")
        self.confirm_button.setDefault(True)
        self.confirm_button.clicked.connect(self.on_confirm)
        button_layout.addWidget(self.confirm_button)

        layout.addLayout(button_layout)

    def _apply_default_selection(self):
        """Azzera PRIMA entrambi i radio, poi imposta il default.

        Lo zero esplicito evita lo stato inconsistente di Qt iniziale
        (nessun radio checked, o entrambi checked).
        """
        self.radio_current.setChecked(False)
        self.radio_all.setChecked(False)
        self.radio_all.setChecked(True)
        self._user_selection = self.DEFAULT_SELECTION
        # I segnali toggled sono gia' scattati: l'utente non ha ancora toccato nulla.
        self._user_touched = False

    def _on_radio_toggled(self, checked):
        """Traccia in modo esplicito l'ultima selezione dell'utente."""
        if not checked:
            return
        if self.radio_current.isChecked():
            self._user_selection = "current"
        elif self.radio_all.isChecked():
            self._user_selection = "all"
        self._user_touched = True

    def showEvent(self, event):
        super().showEvent(event)
        # Se l'utente non ha toccato nulla, il default resta quello valido.
        if not self._user_touched:
            self._apply_default_selection()

    def on_confirm(self):
        # Fallback robust0: preferisci la selezione tracciata, altrimenti
        #ricava dallo stato corrente dei radio.
        selection = self._user_selection
        if selection is None:
            selection = "current" if self.radio_current.isChecked() else "all"
        self.choice = selection
        self.accept()

    def get_choice(self):
        return self.choice
