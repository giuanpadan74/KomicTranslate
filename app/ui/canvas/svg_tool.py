import os
import re
import xml.etree.ElementTree as ET
from PySide6.QtCore import Qt, QPointF, Signal, QSize
from PySide6.QtGui import QPainter, QPixmap, QIcon, QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QMessageBox
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
from .base_tool import BaseTool
from .svg_item import SvgItem
from .balloon_svg_item import BalloonSvgItem
from .z_layers import IMPORTED_SHAPE_LAYER_DEFAULT


class SvgSelectionDialog(QDialog):
    """Dialog per selezionare un file SVG dalla cartella baloons"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona File SVG")
        self.setModal(True)
        self.resize(400, 500)
        
        self.selected_svg_path = None
        self.selected_svg_size = None # Dimensione originale
        # Percorso alla cartella baloons nella root del progetto
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.baloons_folder = os.path.join(project_root, "baloons")
        
        self.setup_ui()
        self.load_svg_files()
    
    def setup_ui(self):
        """Configura l'interfaccia utente del dialog"""
        layout = QVBoxLayout(self)
        
        # Etichetta
        label = QLabel("Seleziona un file SVG:")
        layout.addWidget(label)
        
        # Lista dei file SVG con miniature
        self.svg_list = QListWidget()
        self.svg_list.setIconSize(QSize(64, 64))  # Dimensione delle miniature
        self.svg_list.setGridSize(QSize(120, 80))  # Dimensione degli elementi
        self.svg_list.setViewMode(QListWidget.ListMode)
        self.svg_list.setResizeMode(QListWidget.Adjust)
        self.svg_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.svg_list)
        
        # Pulsanti
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setEnabled(False)
        
        cancel_button = QPushButton("Annulla")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        # Connetti selezione
        self.svg_list.itemSelectionChanged.connect(self.on_selection_changed)
    
    def load_svg_files(self):
        """Carica i file SVG dalla cartella baloons con miniature"""
        if not os.path.exists(self.baloons_folder):
            QMessageBox.warning(self, "Errore", f"Cartella baloons non trovata: {self.baloons_folder}")
            return
        
        svg_files = [f for f in os.listdir(self.baloons_folder) if f.lower().endswith('.svg')]
        
        if not svg_files:
            QMessageBox.information(self, "Info", "Nessun file SVG trovato nella cartella baloons")
            return
        
        for svg_file in sorted(svg_files):
            file_path = os.path.join(self.baloons_folder, svg_file)
            
            # Crea miniatura SVG
            thumbnail = self.create_svg_thumbnail(file_path)
            
            # Crea elemento della lista
            item = QListWidgetItem(svg_file)
            item.setData(Qt.UserRole, file_path)
            
            # Imposta la miniatura come icona
            if thumbnail:
                item.setIcon(QIcon(thumbnail))
            
            self.svg_list.addItem(item)
    
    def on_selection_changed(self):
        """Gestisce il cambio di selezione"""
        current_item = self.svg_list.currentItem()
        if current_item:
            self.selected_svg_path = current_item.data(Qt.UserRole)
            # Calcola dimensione originale
            if self.selected_svg_path and os.path.exists(self.selected_svg_path):
                renderer = QSvgRenderer(self.selected_svg_path)
                if renderer.isValid():
                    self.selected_svg_size = renderer.defaultSize()
            
            self.ok_button.setEnabled(True)
        else:
            self.selected_svg_path = None
            self.selected_svg_size = None
            self.ok_button.setEnabled(False)
    
    def on_item_double_clicked(self, item):
        """Gestisce il doppio click su un elemento"""
        self.selected_svg_path = item.data(Qt.UserRole)
        self.accept()
    
    def create_svg_thumbnail(self, file_path):
        """Crea una miniatura del file SVG"""
        try:
            # Crea renderer SVG
            renderer = QSvgRenderer(file_path)
            if not renderer.isValid():
                return None
            
            # Crea pixmap per la miniatura (64x64 pixel)
            thumbnail_size = QSize(64, 64)
            pixmap = QPixmap(thumbnail_size)
            pixmap.fill(QColor(250, 250, 250))  # Sfondo grigio molto chiaro per evidenziare le forme
            
            # Renderizza l'SVG nel pixmap
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            renderer.render(painter)
            painter.end()
            
            return pixmap
            
        except Exception as e:
            print(f"Errore nella creazione della miniatura per {file_path}: {e}")
            return None
    
    def get_selected_svg_path(self):
        """Restituisce il percorso del file SVG selezionato"""
        return self.selected_svg_path


    def get_selected_svg_size(self):
        """Restituisce la dimensione originale del file SVG selezionato"""
        return self.selected_svg_size

class SvgTool(BaseTool):
    """Strumento per inserire file SVG direttamente sul canvas"""
    
    svg_added = Signal(object)  # Segnale emesso quando viene aggiunto un SVG
    
    def __init__(self, canvas):
        super().__init__(canvas)
        self.name = "SVG"
        self.cursor = Qt.CrossCursor
        
        # Stato del tool
        self.is_placing = False
        self.svg_path = None
        self.target_size = None # Dimensione target per l'inserimento
        self.preview_svg = None
    
    def activate(self):
        """Attiva il tool e mostra il dialog di selezione SVG"""
        super().activate()
        
        # Mostra dialog di selezione
        dialog = SvgSelectionDialog(self.canvas)
        if dialog.exec_() == QDialog.Accepted:
            self.svg_path = dialog.get_selected_svg_path()
            if self.svg_path:
                self.is_placing = True
                
                # Imposta dimensione target iniziale
                self.target_size = dialog.get_selected_svg_size()
                
                # Notifica MainWindow per aggiornare i campi W/H
                main_window = self.canvas.window()
                if main_window and hasattr(main_window, 'update_size_inputs_from_tool'):
                    if self.target_size:
                        main_window.update_size_inputs_from_tool(self.target_size.width(), self.target_size.height())
                
                self.canvas.setCursor(self.cursor)
                # Crea preview per il mouse
                self.create_preview()
            else:
                self.deactivate()
        else:
            self.deactivate()
            
    def set_target_width(self, width):
        """Imposta la larghezza target (mantenendo aspect ratio se possibile, o no)"""
        if self.target_size and width > 0:
            ratio = self.target_size.height() / self.target_size.width()
            new_height = width * ratio
            self.target_size = QSize(int(width), int(new_height))
            self.create_preview()
            
    def set_target_height(self, height):
        """Imposta l'altezza target"""
        if self.target_size and height > 0:
            ratio = self.target_size.width() / self.target_size.height()
            new_width = height * ratio
            self.target_size = QSize(int(new_width), int(height))
            self.create_preview()
            
    def create_preview(self):
        """Crea un'anteprima dell'SVG per il posizionamento"""
        if not self.svg_path:
            return
        
        # Crea renderer SVG
        renderer = QSvgRenderer(self.svg_path)
        if not renderer.isValid():
            QMessageBox.warning(self.canvas, "Errore", "File SVG non valido")
            self.deactivate()
            return
        
        # Crea pixmap di anteprima
        if self.target_size:
            preview_size = self.target_size
        else:
            size = renderer.defaultSize()
            preview_size = size.scaled(100, 100, Qt.KeepAspectRatio)
            self.target_size = preview_size # Inizializza se mancante
        
        pixmap = QPixmap(preview_size)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        self.preview_svg = pixmap
    
    def deactivate(self):
        """Disattiva il tool"""
        super().deactivate()
        self.is_placing = False
        self.svg_path = None
        self.target_size = None
        self.preview_svg = None
        self.canvas.setCursor(Qt.ArrowCursor)
    
    def handle_click(self, scene_pos):
        """Gestisce il click del mouse per inserire un SVG"""
        # Mostra il dialog per selezionare il file SVG
        dialog = SvgSelectionDialog(self.canvas)
        if dialog.exec_() == QDialog.Accepted:
            svg_path = dialog.get_selected_svg_path()
            if svg_path:
                # Determina se è un fumetto e usa la classe appropriata
                if self.is_balloon_svg(svg_path):
                    svg_item = BalloonSvgItem(svg_path)
                else:
                    svg_item = SvgItem(svg_path)
                
                # Controlla e ridimensiona se necessario
                self._check_and_resize_svg(svg_item)
                
                svg_item.setPos(scene_pos)
                self.canvas.scene().addItem(svg_item)
                svg_item.setZValue(IMPORTED_SHAPE_LAYER_DEFAULT)
                svg_item.setSelected(True)
                
                # Emetti segnale
                self.svg_added.emit(svg_item)
                
                # Deseleziona il tool SVG dopo l'inserimento
                main_window = self.canvas.window()
                if main_window and hasattr(main_window, 'set_tool'):
                    main_window.set_tool(None)
    
    def mouse_press_event(self, event):
        """Gestisce il click del mouse per posizionare l'SVG"""
        if not self.is_placing or not self.svg_path:
            return
        
        if event.button() == Qt.LeftButton:
            # Posiziona l'SVG nel punto cliccato
            position = self.canvas.mapToScene(event.pos())
            self.place_svg(position)
            
            # Disattiva il tool dopo il posizionamento
            self.deactivate()
    
    def place_svg(self, position):
        """Posiziona l'SVG nella posizione specificata"""
        if not self.svg_path:
            return
        
        # Determina se è un fumetto e usa la classe appropriata
        if self.is_balloon_svg(self.svg_path):
            svg_item = BalloonSvgItem(self.svg_path)
        else:
            svg_item = SvgItem(self.svg_path)
        
        # Controlla e ridimensiona se necessario
        self._check_and_resize_svg(svg_item)
        
        # Posiziona l'SVG
        svg_item.setPos(position)
        
        # Aggiungi al canvas
        self.canvas.scene().addItem(svg_item)
        svg_item.setZValue(IMPORTED_SHAPE_LAYER_DEFAULT)
        svg_item.setSelected(True)
        
        # Emetti segnale
        self.svg_added.emit(svg_item)
    
    def is_balloon_svg(self, svg_path):
        """Determina se un file SVG è un fumetto analizzando il nome del file e il contenuto"""
        if not svg_path or not os.path.exists(svg_path):
            return False
        
        # Controlla il nome del file per parole chiave tipiche dei fumetti
        filename = os.path.basename(svg_path).lower()
        balloon_keywords = ['parlato', 'pensiero', 'fulmine', 'grido', 'sussurro', 'balloon', 'bubble', 'speech']
        
        # Se il nome contiene parole chiave dei fumetti
        for keyword in balloon_keywords:
            if keyword in filename:
                return True
        
        # Se è nella cartella baloons, probabilmente è un fumetto
        if 'baloons' in svg_path.lower() or 'balloon' in svg_path.lower():
            return True
        
        # Analisi del contenuto SVG per identificare forme tipiche dei fumetti
        try:
            with open(svg_path, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                
                # Cerca pattern tipici dei fumetti (path complessi, curve, ecc.)
                balloon_patterns = [
                    'path d="m',  # Path complessi tipici dei fumetti
                    'ellipse',    # Forme ellittiche
                    'curve',      # Curve
                    'bezier'      # Curve di Bezier
                ]
                
                pattern_count = sum(1 for pattern in balloon_patterns if pattern in content)
                
                # Se contiene molti pattern tipici dei fumetti
                if pattern_count >= 2:
                    return True
                    
        except Exception as e:
            pass
        
        return False
    
    def _check_and_resize_svg(self, svg_item):
        """Controlla le dimensioni dell'SVG e lo ridimensiona se supera il 50% delle dimensioni dell'immagine di sfondo"""
        try:
            # Ottieni le dimensioni dell'immagine di sfondo
            if not hasattr(self.canvas, 'photo') or not self.canvas.photo:
                return  # Nessuna immagine di sfondo caricata
            
            background_pixmap = self.canvas.photo.pixmap()
            if not background_pixmap:
                return
            
            background_size = background_pixmap.size()
            bg_width = background_size.width()
            bg_height = background_size.height()
            
            # Calcola i limiti massimi (50% delle dimensioni dell'immagine di sfondo)
            max_width = bg_width * 0.5
            max_height = bg_height * 0.5
            
            # Ottieni le dimensioni attuali dell'SVG
            svg_rect = svg_item.boundingRect()
            current_width = svg_rect.width()
            current_height = svg_rect.height()
            
            # Verifica se l'SVG supera i limiti
            if current_width > max_width or current_height > max_height:
                # Calcola il fattore di scala per rispettare entrambi i limiti
                width_scale = max_width / current_width if current_width > max_width else 1.0
                height_scale = max_height / current_height if current_height > max_height else 1.0
                
                # Usa il fattore di scala più restrittivo per mantenere le proporzioni
                scale_factor = min(width_scale, height_scale)
                
                # Calcola le nuove dimensioni
                new_width = current_width * scale_factor
                new_height = current_height * scale_factor
                
                # Ridimensiona l'SVG usando il metodo set_size se disponibile
                if hasattr(svg_item, 'set_size'):
                    svg_item.set_size(new_width, new_height, maintain_aspect_ratio=True)
                elif hasattr(svg_item, 'set_scale'):
                    # Fallback: usa set_scale con scala proporzionale
                    svg_item.set_scale(scale=scale_factor)
                
                print(f"SVG ridimensionato da {current_width:.1f}x{current_height:.1f} a {new_width:.1f}x{new_height:.1f} (fattore: {scale_factor:.2f})")
                
        except Exception as e:
            print(f"Errore durante il controllo delle dimensioni SVG: {e}")
    
    def paint_preview(self, painter, event):
        """Disegna l'anteprima dell'SVG sotto il cursore"""
        if not self.is_placing or not self.preview_svg:
            return
        
        # Ottieni posizione del mouse
        mouse_pos = self.canvas.mapFromGlobal(self.canvas.cursor().pos())
        
        # Disegna l'anteprima centrata sul cursore
        preview_rect = self.preview_svg.rect()
        preview_rect.moveCenter(mouse_pos)
        
        painter.setOpacity(0.7)
        painter.drawPixmap(preview_rect, self.preview_svg)
        painter.setOpacity(1.0)
