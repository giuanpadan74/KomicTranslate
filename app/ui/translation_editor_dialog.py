from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt

from app.ui.widgets.translation_row_widget import TranslationRowWidget

class TranslationEditorDialog(QtWidgets.QDialog):
    """Finestra di dialogo per modificare tutte le traduzioni in blocco"""
    
    def __init__(self, blocks, parent=None):
        super().__init__(parent)
        self.blocks = blocks  # Lista di blocchi con 'text' (sorgente) e 'translation' (destinazione)
        self.row_widgets = []
        self.setupUI()
        self.load_blocks()
        
    def setupUI(self):
        self.setWindowTitle("Modifica Traduzioni")
        self.setModal(True)
        self.setMinimumSize(720, 480)
        self.resize(980, 720)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Etichetta informativa
        info_label = QtWidgets.QLabel(
            "Modifica le traduzioni: la colonna sinistra è il testo sorgente (sola lettura), la destra è modificabile"
        )
        layout.addWidget(info_label)
        
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll_area, 1)

        self.rows_container = QtWidgets.QWidget()
        self.rows_layout = QtWidgets.QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        self.rows_layout.addStretch(1)
        self.scroll_area.setWidget(self.rows_container)
        
        # Pulsanti
        button_layout = QtWidgets.QHBoxLayout()
        
        self.cancel_button = QtWidgets.QPushButton("Annulla")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.ok_button = QtWidgets.QPushButton("OK")
        self.ok_button.clicked.connect(self._on_ok_clicked)
        self.ok_button.setDefault(True)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
        
    def load_blocks(self):
        for w in self.row_widgets:
            w.setParent(None)
            w.deleteLater()
        self.row_widgets.clear()
        
        insert_at = max(0, self.rows_layout.count() - 1)
        for row, block in enumerate(self.blocks):
            source_text = block.text if hasattr(block, 'text') else ""
            target_text = block.translation if hasattr(block, 'translation') else ""
            row_widget = TranslationRowWidget()
            row_widget.set_index(row + 1)
            row_widget.set_texts(source_text, target_text)
            self.rows_layout.insertWidget(insert_at + row, row_widget)
            self.row_widgets.append(row_widget)
    
    def get_updated_translations(self):
        """Restituisce la lista dei blocchi con le traduzioni aggiornate"""
        for row, block in enumerate(self.blocks):
            if row >= len(self.row_widgets):
                break
            if hasattr(block, 'translation'):
                block.translation = self.row_widgets[row].get_target_text()
        return self.blocks

    def _on_ok_clicked(self):
        self.get_updated_translations()
        self.accept()
