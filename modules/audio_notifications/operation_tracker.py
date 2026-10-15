import logging
from typing import Optional, Dict, Any
from PySide6.QtCore import QObject, QTimer

class OperationTracker(QObject):
    """Traccia le operazioni in corso e completate"""
    
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.current_operation = None
        self.operation_start_time = None
        
        # Mappatura indici pulsanti -> operazioni
        self.button_operations = {
            0: 'detect',      # Rilevazione Caselle di Testo
            1: 'ocr',         # OCR
            2: 'ocr_color',   # OCR+C
            3: 'translate',   # Ottieni Traduzioni
            4: 'segment',     # Segmenta Testo
            5: 'inpaint',     # Pulisci Immagine
            6: 'render'       # Render
        }
    
    def detect_current_operation(self) -> Optional[str]:
        """Rileva l'operazione corrente basandosi sui pulsanti evidenziati"""
        try:
            # Controlla i pulsanti del gruppo principale
            buttons = self.controller.hbutton_group.get_button_group().buttons()
            
            for i, button in enumerate(buttons):
                # Verifica se il pulsante ha il bordo giallo (evidenziato)
                style = button.styleSheet()
                if 'border: 3px solid #FFD700' in style:
                    operation = self.button_operations.get(i)
                    if operation:
                        logging.debug(f"Operazione rilevata: {operation} (pulsante {i})")
                        return operation
            
            # Fallback: controlla se è in corso un processo batch
            if hasattr(self.controller, 'translate_button'):
                if not self.controller.translate_button.isEnabled():
                    return 'batch_translate'
            
            return None
            
        except Exception as e:
            logging.error(f"Errore rilevamento operazione: {e}")
            return None
    
    def start_operation(self, operation: str):
        """Registra l'inizio di un'operazione"""
        self.current_operation = operation
        self.operation_start_time = QTimer()
        self.operation_start_time.start()
        logging.debug(f"Iniziata operazione: {operation}")
    
    def complete_operation(self) -> Optional[str]:
        """Registra il completamento dell'operazione corrente"""
        if self.current_operation:
            completed_op = self.current_operation
            elapsed = 0
            
            if self.operation_start_time:
                elapsed = self.operation_start_time.elapsed()
                self.operation_start_time = None
            
            self.current_operation = None
            logging.info(f"Completata operazione: {completed_op} in {elapsed}ms")
            return completed_op
        
        # Se non abbiamo tracciato l'inizio, prova a rilevare dall'UI
        return self.detect_current_operation()