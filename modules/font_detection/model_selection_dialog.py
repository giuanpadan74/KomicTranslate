"""Dialog for selecting OCR Vision model for font detection."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt
from typing import List, Optional

class ModelSelectionDialog(QDialog):
    """Dialog for selecting an OCR Vision model for font detection."""
    
    def __init__(self, available_models: List[str], parent=None):
        super().__init__(parent)
        self.selected_model = None
        self.available_models = available_models
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface."""
        self.setWindowTitle(self.tr("Seleziona Modello Vision"))
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QVBoxLayout(self)
        
        # Etichetta informativa
        info_label = QLabel(
            self.tr("Seleziona il modello Vision da utilizzare per il rilevamento dei font:")
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # ComboBox per la selezione del modello
        self.model_combo = QComboBox()
        if self.available_models:
            self.model_combo.addItems(self.available_models)
            # Seleziona GPT-4o come default se disponibile
            if 'GPT-4o' in self.available_models:
                self.model_combo.setCurrentText('GPT-4o')
        else:
            self.model_combo.addItem(self.tr("Nessun modello disponibile"))
            
        layout.addWidget(self.model_combo)
        
        # Pulsanti
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton(self.tr("OK"))
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setEnabled(bool(self.available_models))
        
        self.cancel_button = QPushButton(self.tr("Annulla"))
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
    def get_selected_model(self) -> Optional[str]:
        """Get the selected model name."""
        if self.available_models and self.model_combo.currentIndex() >= 0:
            return self.model_combo.currentText()
        return None
        
    def tr(self, text: str) -> str:
        """Translation helper method."""
        # Per ora ritorna il testo così com'è
        # In futuro può essere integrato con il sistema di traduzione dell'app
        return text