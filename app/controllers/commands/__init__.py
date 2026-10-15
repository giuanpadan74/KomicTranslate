"""
app.controllers.commands - Comandi estratti da controller.py

Questo package contiene le classi estratte da controller.py per migliorare
la manutenibilità e supportare il vibe coding.

Classi disponibili:
- ImageUpdateHandler: Gestione aggiornamento immagini processate

Nota: la logica di selezione multipla e di formattazione vive in
app.controllers.ui_controller (UIMixin), che ha la precedenza nel MRO.
"""

from .image_update_handler import ImageUpdateHandler

__all__ = [
    'ImageUpdateHandler',
]