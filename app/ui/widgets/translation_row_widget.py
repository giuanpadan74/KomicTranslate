from PySide6 import QtCore, QtWidgets

from app.ui.widgets.auto_grow_plain_text_edit import AutoGrowPlainTextEdit


class TranslationRowWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)

        self.index_label = QtWidgets.QLabel("")
        self.index_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
        self.index_label.setMinimumWidth(40)
        self.index_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)

        self.source_edit = AutoGrowPlainTextEdit(read_only=True, min_lines=2)
        self.target_edit = AutoGrowPlainTextEdit(read_only=False, min_lines=2)

        self.source_edit.setTabChangesFocus(True)
        self.target_edit.setTabChangesFocus(True)

        # Le due colonne di testo devono condividere in modo uniforme tutto
        # lo spazio orizzontale disponibile. SizePolicy.Expanding su entrambe
        # fa sì che QHBoxLayout ridistribuisca lo spazio proporzionalmente
        # durante il resize della finestra, mantenendo la parità di larghezza.
        self.source_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.target_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.index_label)
        layout.addWidget(self.source_edit)
        layout.addWidget(self.target_edit)

        # Stretch identici (1:1) garantiscono larghezza uniforme e scalabile
        # delle due colonne al variare della larghezza del dialogo.
        self._apply_uniform_stretch()

    def set_index(self, index: int):
        self.index_label.setText(f"{index}.")

    def set_texts(self, source_text: str, target_text: str):
        self.source_edit.setPlainText(source_text or "")
        self.target_edit.setPlainText(target_text or "")
        self.source_edit.adjust_height_now()
        self.target_edit.adjust_height_now()

    def get_target_text(self) -> str:
        return self.target_edit.toPlainText()

    def _apply_uniform_stretch(self):
        """Imposta stretch 1:1 sulle due colonne testuali.

        Rimuove la precedente logica adattiva basata sulla lunghezza del testo
        e mantiene proporzioni uniformi in modo scalabile: il QHBoxLayout
        ridistribuisce automaticamente lo spazio al resize della finestra.
        """
        layout = self.layout()
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)
        layout.setStretch(2, 1)
