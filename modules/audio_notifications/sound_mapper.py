import logging
from typing import Dict, Optional

class SoundMapper:
    """Mappa le operazioni ai suoni appropriati"""
    
    def __init__(self):
        # Mappatura operazioni -> identificatori suono
        self.operation_sounds = {
            'detect': 'detect',           # Rilevazione testo
            'detect_all': 'detect_all',    # Rilevazione completa (All)
            'ocr': 'ocr',                # OCR standard
            'ocr_color': 'ocr_color',    # OCR con colore
            'translate': 'translate',     # Traduzione
            'segment': 'segment',        # Segmentazione
            'inpaint': 'inpaint',       # Pulizia immagine
            'render': 'render',         # Rendering
            'batch_translate': 'translate' # Traduzione batch
        }
        
        # Descrizioni per logging
        self.operation_descriptions = {
            'detect': 'Rilevazione Caselle di Testo',
            'detect_all': 'Rilevazione Completa (All)',
            'ocr': 'OCR',
            'ocr_color': 'OCR con Rilevamento Colore',
            'translate': 'Traduzione',
            'segment': 'Segmentazione Testo',
            'inpaint': 'Pulizia Immagine',
            'render': 'Rendering Testo',
            'batch_translate': 'Traduzione Automatica'
        }
    
    def get_sound_for_operation(self, operation: str) -> Optional[str]:
        """Restituisce l'identificatore del suono per l'operazione"""
        sound = self.operation_sounds.get(operation)
        if sound:
            desc = self.operation_descriptions.get(operation, operation)
            logging.debug(f"Mappatura suono: {desc} -> {sound}")
        return sound
    
    def get_operation_description(self, operation: str) -> str:
        """Restituisce la descrizione dell'operazione"""
        return self.operation_descriptions.get(operation, operation)