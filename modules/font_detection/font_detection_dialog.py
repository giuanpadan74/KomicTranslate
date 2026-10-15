"""Font Detection Results Dialog."""

import os
import json
import logging
from typing import List, Optional
from PySide6 import QtCore, QtGui, QtWidgets

try:
    from ...app.ui.dayu_widgets.label import MLabel
    from ...app.ui.dayu_widgets.divider import MDivider
    from ...app.ui.dayu_widgets.message import MMessage
    from ...app.ui.dayu_widgets.push_button import MPushButton
except ImportError:
    # Fallback to standard Qt widgets if dayu_widgets not available
    MLabel = QtWidgets.QLabel
    MDivider = QtWidgets.QFrame
    MMessage = None
    MPushButton = QtWidgets.QPushButton

from .font_detector import FontDetectionResult
from .font_installer import FontInstaller

class FontAvailabilityChecker(QtCore.QObject):
    """Worker class to check font availability on Google Fonts asynchronously."""
    
    font_availability_checked = QtCore.Signal(bool)  # Signal emitted when check is complete
    
    def __init__(self, font_name: str):
        super().__init__()
        self.font_name = font_name
    
    def check_availability(self):
        """Check if font is available on Google Fonts without downloading."""
        try:
            import requests
            from urllib.parse import quote
            
            # Google Fonts API endpoint
            api_key = "AIzaSyBC8xFJrwBKONaWdGHlLvOhOOOOOOOOOOO"  # Replace with actual API key
            font_name_encoded = quote(self.font_name.replace(' ', '+'))
            
            # Search for font
            search_url = f"https://www.googleapis.com/webfonts/v1/webfonts?key={api_key}&family={font_name_encoded}"
            
            response = requests.get(search_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                is_available = bool(data.get('items'))
            else:
                is_available = False
                
        except Exception as e:
            logging.warning(f"Failed to check font availability: {e}")
            is_available = False
        
        self.font_availability_checked.emit(is_available)

class FontResultWidget(QtWidgets.QWidget):
    """Widget to display a single font detection result."""
    
    def __init__(self, result: FontDetectionResult, block_index: int, parent=None):
        super().__init__(parent)
        self.result = result
        self.block_index = block_index
        self.font_installer = FontInstaller()
        self.install_btn = None  # Will be created later if font is available
        self._init_ui()
        self._check_font_availability()
    
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QtWidgets.QVBoxLayout()
        
        # Header with block number
        header_layout = QtWidgets.QHBoxLayout()
        block_label = MLabel(f"Blocco di Testo {self.block_index + 1}")
        block_label.setProperty("h4", True)
        header_layout.addWidget(block_label)
        
        # Confidence indicator
        confidence_label = MLabel(f"Confidenza: {self.result.confidence:.1%}")
        if self.result.confidence >= 0.8:
            confidence_label.setProperty("success", True)
        elif self.result.confidence >= 0.5:
            confidence_label.setProperty("warning", True)
        else:
            confidence_label.setProperty("error", True)
        header_layout.addWidget(confidence_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Font details grid
        details_layout = QtWidgets.QGridLayout()
        
        # Font Family
        details_layout.addWidget(MLabel("Famiglia Font:"), 0, 0)
        font_family_label = MLabel(self.result.font_family)
        font_family_label.setProperty("strong", True)
        details_layout.addWidget(font_family_label, 0, 1)
        
        # Font Style
        details_layout.addWidget(MLabel("Stile:"), 1, 0)
        details_layout.addWidget(MLabel(self.result.font_style), 1, 1)
        
        # Font Weight
        details_layout.addWidget(MLabel("Peso:"), 2, 0)
        details_layout.addWidget(MLabel(self.result.font_weight), 2, 1)
        
        # Font Size
        details_layout.addWidget(MLabel("Dimensione:"), 3, 0)
        details_layout.addWidget(MLabel(self.result.font_size_estimate), 3, 1)
        
        # Serif Type
        details_layout.addWidget(MLabel("Tipo:"), 4, 0)
        details_layout.addWidget(MLabel(self.result.serif_type), 4, 1)
        
        layout.addLayout(details_layout)
        
        # Action buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        # Search font button
        search_btn = MPushButton("🔍 Cerca Font")
        search_btn.clicked.connect(self._search_font)
        button_layout.addWidget(search_btn)
        
        # Install font button will be added later if font is available on Google Fonts
        # Store button layout reference for later use
        self.button_layout = button_layout
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Additional info (if available)
        if self.result.additional_info:
            info_text = "\n".join([f"{k}: {v}" for k, v in self.result.additional_info.items()])
            if info_text.strip():
                info_label = MLabel("Informazioni aggiuntive:")
                info_label.setProperty("secondary", True)
                layout.addWidget(info_label)
                
                info_content = QtWidgets.QTextEdit()
                info_content.setPlainText(info_text)
                info_content.setMaximumHeight(80)
                info_content.setReadOnly(True)
                layout.addWidget(info_content)
        
        self.setLayout(layout)
        
        # Add border and padding
        self.setStyleSheet("""
            FontResultWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                margin: 4px;
                background-color: #fafafa;
            }
        """)
    
    def _search_font(self):
        """Open web search for the font."""
        import webbrowser
        search_query = f"{self.result.font_family} font download free"
        search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
        webbrowser.open(search_url)
    
    def _check_font_availability(self):
        """Check if font is available on Google Fonts asynchronously."""
        if not self.font_installer.can_install_fonts():
            return
            
        # Create worker thread to check font availability
        self.availability_thread = QtCore.QThread()
        self.availability_checker = FontAvailabilityChecker(self.result.font_family)
        self.availability_checker.moveToThread(self.availability_thread)
        
        # Connect signals
        self.availability_thread.started.connect(self.availability_checker.check_availability)
        self.availability_checker.font_availability_checked.connect(self._on_font_availability_checked)
        self.availability_checker.font_availability_checked.connect(self.availability_thread.quit)
        self.availability_thread.finished.connect(self.availability_thread.deleteLater)
        
        # Start the check
        self.availability_thread.start()
    
    def _on_font_availability_checked(self, is_available: bool):
        """Handle the result of font availability check."""
        if is_available:
            # Font is available on Google Fonts, show install button
            self.install_btn = MPushButton("📥 Installa Google Font")
            self.install_btn.clicked.connect(self._install_font)
            # Insert before the stretch
            self.button_layout.insertWidget(self.button_layout.count() - 1, self.install_btn)
    
    def _install_font(self):
        """Attempt to install the font."""
        try:
            success = self.font_installer.search_and_install(self.result.font_family)
            if success:
                if MMessage:
                    MMessage.success(f"Font {self.result.font_family} installato con successo!", parent=self)
                else:
                    QtWidgets.QMessageBox.information(self, "Successo", f"Font {self.result.font_family} installato!")
            else:
                if MMessage:
                    MMessage.warning(f"Font {self.result.font_family} non trovato per l'installazione automatica.", parent=self)
                else:
                    QtWidgets.QMessageBox.warning(self, "Avviso", f"Font {self.result.font_family} non trovato.")
        except Exception as e:
            if MMessage:
                MMessage.error(f"Errore durante l'installazione: {str(e)}", parent=self)
            else:
                QtWidgets.QMessageBox.critical(self, "Errore", f"Errore durante l'installazione: {str(e)}")

class FontDetectionDialog(QtWidgets.QDialog):
    """Dialog to display font detection results."""
    
    # Segnale emesso quando il dialog viene chiuso per richiedere l'aggiornamento della lista font
    font_list_update_requested = QtCore.Signal()
    
    def __init__(self, results: List[FontDetectionResult], parent=None):
        super().__init__(parent)
        self.results = results
        self._init_ui()
        self.setWindowTitle("Risultati Riconoscimento Font")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)
    
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QtWidgets.QVBoxLayout()
        
        # Header
        header_layout = QtWidgets.QHBoxLayout()
        title_label = MLabel("Risultati Riconoscimento Font")
        title_label.setProperty("h2", True)
        header_layout.addWidget(title_label)
        
        # Summary info
        summary_label = MLabel(f"Analizzati {len(self.results)} blocchi di testo")
        summary_label.setProperty("secondary", True)
        header_layout.addWidget(summary_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        layout.addWidget(MDivider() if MDivider != QtWidgets.QFrame else QtWidgets.QFrame())
        
        # Scrollable results area
        scroll_area = QtWidgets.QScrollArea()
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        
        # Add result widgets
        for i, result in enumerate(self.results):
            result_widget = FontResultWidget(result, i, self)
            scroll_layout.addWidget(result_widget)
        
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        # Action buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        button_layout.addStretch()
        
        # Close button
        close_btn = MPushButton("Chiudi")
        close_btn.clicked.connect(self._on_close_clicked)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    

    
    def _on_close_clicked(self):
        """Gestisce il click del pulsante Chiudi."""
        # Emetti il segnale per richiedere l'aggiornamento della lista font
        self.font_list_update_requested.emit()
        # Chiudi il dialog
        self.accept()
    
    @staticmethod
    def show_results(results: List[FontDetectionResult], parent=None) -> 'FontDetectionDialog':
        """Static method to show font detection results."""
        dialog = FontDetectionDialog(results, parent)
        dialog.exec_()
        return dialog