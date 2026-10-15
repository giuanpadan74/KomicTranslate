"""Classe base per tutti i tool del canvas."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QCursor
from PySide6.QtCore import Qt


class BaseTool(QObject):
    """Classe base per tutti i tool del canvas"""
    
    # Segnali comuni
    tool_activated = Signal()
    tool_deactivated = Signal()
    
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.name = "Base Tool"
        self.cursor = Qt.ArrowCursor
        self.is_active = False
    
    def activate(self):
        """Attiva il tool"""
        self.is_active = True
        self.tool_activated.emit()
    
    def deactivate(self):
        """Disattiva il tool"""
        self.is_active = False
        self.tool_deactivated.emit()
    
    def handle_click(self, scene_pos):
        """Gestisce il click del mouse - da implementare nelle sottoclassi"""
        pass
    
    def handle_mouse_move(self, scene_pos):
        """Gestisce il movimento del mouse - da implementare nelle sottoclassi"""
        pass
    
    def handle_mouse_release(self, scene_pos):
        """Gestisce il rilascio del mouse - da implementare nelle sottoclassi"""
        pass