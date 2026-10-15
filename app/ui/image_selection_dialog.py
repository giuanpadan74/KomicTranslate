import numpy as np
import cv2
from typing import List, Optional
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QScrollArea, QWidget
from PySide6.QtGui import QPixmap, QImage

class ImagePreviewWidget(QLabel):
    """Widget per mostrare un'anteprima di immagine selezionabile"""
    
    clicked = QtCore.Signal(int)
    
    def __init__(self, image: np.ndarray, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.image = image
        self.selected = False
        
        # Converti l'immagine OpenCV in QPixmap
        self.original_pixmap = self._numpy_to_qpixmap(image)
        
        # Imposta dimensioni fisse per l'anteprima
        self.preview_size = (200, 150)
        self.setFixedSize(*self.preview_size)
        
        # Scala l'immagine mantenendo le proporzioni
        scaled_pixmap = self.original_pixmap.scaled(
            self.preview_size[0], self.preview_size[1],
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.setPixmap(scaled_pixmap)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border: 2px solid #cccccc;
                border-radius: 8px;
                background-color: #f5f5f5;
                padding: 4px;
            }
            QLabel:hover {
                border-color: #0078d4;
                background-color: #e6f3ff;
            }
        """)
        
        # Abilita il tracking del mouse per l'hover
        self.setMouseTracking(True)
        
    def _numpy_to_qpixmap(self, image: np.ndarray) -> QPixmap:
        """Converte un'immagine NumPy in QPixmap"""
        if len(image.shape) == 3:
            # Immagine a colori (BGR -> RGB)
            height, width, channel = image.shape
            bytes_per_line = 3 * width
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        else:
            # Immagine in scala di grigi
            height, width = image.shape
            bytes_per_line = width
            q_image = QImage(image.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
        
        return QPixmap.fromImage(q_image)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
    
    def set_selected(self, selected: bool):
        """Imposta lo stato di selezione del widget"""
        self.selected = selected
        if selected:
            self.setStyleSheet("""
                QLabel {
                    border: 3px solid #0078d4;
                    border-radius: 8px;
                    background-color: #e6f3ff;
                    padding: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                QLabel {
                    border: 2px solid #cccccc;
                    border-radius: 8px;
                    background-color: #f5f5f5;
                    padding: 4px;
                }
                QLabel:hover {
                    border-color: #0078d4;
                    background-color: #e6f3ff;
                }
            """)

class ImageSelectionDialog(QDialog):
    """Dialog per la selezione di un'immagine da una lista di varianti generate"""
    
    def __init__(self, images: List[np.ndarray], title: str = "Seleziona Immagine", parent=None):
        super().__init__(parent)
        self.images = images
        self.selected_index = 0  # Default alla prima immagine
        self.image_widgets = []
        
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(800, 600)
        
        self._setup_ui()
        self._connect_signals()
        
        # Seleziona la prima immagine di default
        if self.image_widgets:
            self.image_widgets[0].set_selected(True)
    
    def _setup_ui(self):
        """Configura l'interfaccia utente del dialog"""
        layout = QVBoxLayout(self)
        
        # Titolo
        title_label = QLabel("Scegli una delle immagini generate:")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Area scrollabile per le immagini
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Widget contenitore per la griglia
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)
        
        # Calcola il numero di colonne (massimo 3 per riga)
        cols = min(3, len(self.images))
        
        # Crea i widget per ogni immagine
        for i, image in enumerate(self.images):
            row = i // cols
            col = i % cols
            
            # Container per immagine + etichetta
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(5, 5, 5, 5)
            
            # Widget immagine
            image_widget = ImagePreviewWidget(image, i)
            self.image_widgets.append(image_widget)
            
            # Etichetta con numero variante
            label = QLabel(f"Variante {i + 1}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 12px; color: #666666; margin-top: 5px;")
            
            container_layout.addWidget(image_widget)
            container_layout.addWidget(label)
            
            grid_layout.addWidget(container, row, col)
        
        scroll_area.setWidget(grid_widget)
        layout.addWidget(scroll_area)
        
        # Pulsanti
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Annulla")
        self.cancel_button.setMinimumWidth(100)
        button_layout.addWidget(self.cancel_button)
        
        self.ok_button = QPushButton("OK")
        self.ok_button.setMinimumWidth(100)
        self.ok_button.setDefault(True)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
        
        # Info sulla selezione
        self.info_label = QLabel("Variante 1 selezionata")
        self.info_label.setStyleSheet("color: #0078d4; font-size: 12px; margin: 5px;")
        layout.insertWidget(1, self.info_label)
    
    def _connect_signals(self):
        """Connette i segnali dei widget"""
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        # Connetti i segnali di click delle immagini
        for widget in self.image_widgets:
            widget.clicked.connect(self._on_image_selected)
    
    def _on_image_selected(self, index: int):
        """Gestisce la selezione di un'immagine"""
        # Deseleziona tutte le immagini
        for widget in self.image_widgets:
            widget.set_selected(False)
        
        # Seleziona l'immagine cliccata
        self.image_widgets[index].set_selected(True)
        self.selected_index = index
        
        # Aggiorna l'etichetta informativa
        self.info_label.setText(f"Variante {index + 1} selezionata")
    
    def get_selected_image(self) -> Optional[np.ndarray]:
        """Restituisce l'immagine selezionata"""
        if 0 <= self.selected_index < len(self.images):
            return self.images[self.selected_index]
        return None
    
    def get_selected_index(self) -> int:
        """Restituisce l'indice dell'immagine selezionata"""
        return self.selected_index
    
    @staticmethod
    def select_image(images: List[np.ndarray], title: str = "Seleziona Immagine", parent=None) -> Optional[np.ndarray]:
        """Metodo statico per mostrare il dialog e ottenere l'immagine selezionata"""
        if not images:
            return None
        
        if len(images) == 1:
            # Se c'è solo un'immagine, restituiscila direttamente
            return images[0]
        
        dialog = ImageSelectionDialog(images, title, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_selected_image()
        
        return None