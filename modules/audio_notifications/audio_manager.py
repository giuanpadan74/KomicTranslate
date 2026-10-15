import os
import logging
from typing import Optional
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtCore import QUrl, QObject

class AudioManager(QObject):
    """Gestisce la riproduzione dei suoni di notifica"""
    
    def __init__(self):
        super().__init__()
        self.sound_effects = {}
        self.enabled = True
        self.volume = 0.7
        self.sounds_dir = os.path.join(os.path.dirname(__file__), 'sounds')
        self._initialize_sounds()
    
    def _initialize_sounds(self):
        """Inizializza tutti gli effetti sonori"""
        sound_files = {
            'detect': 'detect_beep.wav',
            'detect_all': 'rileva_wave.wav',
            'ocr': 'ocr_ding.wav', 
            'ocr_color': 'ocr_color_chime.wav',
            'translate': 'translate_success.wav',
            'segment': 'segmenta.wav',
            'inpaint': 'inpaint_whoosh.wav',
            'render': 'render_completion.wav'
        }
        
        for operation, filename in sound_files.items():
            try:
                sound_path = os.path.join(self.sounds_dir, filename)
                    
                if os.path.exists(sound_path):
                    effect = QSoundEffect()
                    effect.setSource(QUrl.fromLocalFile(sound_path))
                    effect.setVolume(self.volume)
                    self.sound_effects[operation] = effect
                    logging.debug(f"Audio caricato: {operation} -> {filename}")
                else:
                    logging.warning(f"File audio non trovato: modules\\audio_notifications\\sounds\\{filename}")
            except Exception as e:
                logging.error(f"Errore caricamento audio {operation}: {e}")
    
    def play_sound(self, operation: str) -> bool:
        """Riproduce il suono per l'operazione specificata"""
        if not self.enabled:
            return False
            
        try:
            if operation in self.sound_effects:
                self.sound_effects[operation].play()
                logging.debug(f"Riprodotto suono per operazione: {operation}")
                return True
            else:
                logging.warning(f"Suono non trovato per operazione: {operation}")
                return False
        except Exception as e:
            logging.error(f"Errore riproduzione audio {operation}: {e}")
            return False
    
    def set_enabled(self, enabled: bool):
        """Abilita/disabilita le notifiche audio"""
        self.enabled = enabled
        logging.info(f"Notifiche audio {'abilitate' if enabled else 'disabilitate'}")
    
    def set_volume(self, volume: float):
        """Imposta il volume (0.0 - 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        for effect in self.sound_effects.values():
            effect.setVolume(self.volume)
        logging.debug(f"Volume impostato a: {self.volume}")