import logging
import functools
from typing import Optional

from .audio_manager import AudioManager
from .operation_tracker import OperationTracker
from .sound_mapper import SoundMapper

class AudioNotificationSystem:
    """Sistema principale per le notifiche audio"""
    
    def __init__(self, controller):
        self.controller = controller
        self.audio_manager = AudioManager()
        self.operation_tracker = OperationTracker(controller)
        self.sound_mapper = SoundMapper()
        self.enabled = True
        
        # Riferimenti ai metodi originali per il monkey patching
        self._original_on_manual_finished = None
        self._original_on_batch_process_finished = None
        
        logging.info("Sistema notifiche audio inizializzato")
    
    def enable(self, enabled: bool = True):
        """Abilita/disabilita le notifiche audio"""
        self.enabled = enabled
        self.audio_manager.set_enabled(enabled)
        logging.info(f"Notifiche audio {'abilitate' if enabled else 'disabilitate'}")
    
    def set_volume(self, volume: float):
        """Imposta il volume delle notifiche (0.0 - 1.0)"""
        self.audio_manager.set_volume(volume)
        logging.info(f"Volume notifiche impostato a {volume}")
    
    def _play_completion_sound(self, operation: Optional[str]):
        """Riproduce il suono di completamento per l'operazione"""
        if not self.enabled or not operation:
            return
        
        sound_id = self.sound_mapper.get_sound_for_operation(operation)
        if sound_id:
            description = self.sound_mapper.get_operation_description(operation)
            logging.info(f"Riproduzione suono per: {description}")
            self.audio_manager.play_sound(sound_id)
    
    def _wrapped_on_manual_finished(self, original_method):
        """Wrapper per on_manual_finished con notifica audio"""
        @functools.wraps(original_method)
        def wrapper(*args, **kwargs):
            # Rileva l'operazione prima di chiamare il metodo originale
            operation = self.operation_tracker.detect_current_operation()
            
            # Chiama il metodo originale
            result = original_method(*args, **kwargs)
            
            # Riproduce il suono di completamento
            self._play_completion_sound(operation)
            
            return result
        return wrapper
    
    def _wrapped_on_batch_process_finished(self, original_method):
        """Wrapper per on_batch_process_finished con notifica audio"""
        @functools.wraps(original_method)
        def wrapper(*args, **kwargs):
            # Per i processi batch, assumiamo sia traduzione
            operation = 'batch_translate'
            
            # Chiama il metodo originale
            result = original_method(*args, **kwargs)
            
            # Riproduce il suono di completamento
            self._play_completion_sound(operation)
            
            return result
        return wrapper
    
    def apply_monkey_patches(self):
        """Applica i monkey patch ai metodi del controller"""
        try:
            # Salva i metodi originali
            self._original_on_manual_finished = self.controller.on_manual_finished
            self._original_on_batch_process_finished = self.controller.on_batch_process_finished
            
            # Applica i wrapper
            self.controller.on_manual_finished = self._wrapped_on_manual_finished(
                self._original_on_manual_finished
            )
            self.controller.on_batch_process_finished = self._wrapped_on_batch_process_finished(
                self._original_on_batch_process_finished
            )
            
            logging.info("Monkey patches applicati con successo")
            
        except Exception as e:
            logging.error(f"Errore applicazione monkey patches: {e}")
    
    def remove_monkey_patches(self):
        """Rimuove i monkey patch ripristinando i metodi originali"""
        try:
            if self._original_on_manual_finished:
                self.controller.on_manual_finished = self._original_on_manual_finished
            
            if self._original_on_batch_process_finished:
                self.controller.on_batch_process_finished = self._original_on_batch_process_finished
            
            logging.info("Monkey patches rimossi")
            
        except Exception as e:
            logging.error(f"Errore rimozione monkey patches: {e}")

# Istanza globale del sistema
_audio_system = None

def initialize_audio_notifications(controller):
    """Inizializza il sistema di notifiche audio"""
    global _audio_system
    
    if _audio_system is None:
        _audio_system = AudioNotificationSystem(controller)
        _audio_system.apply_monkey_patches()
        logging.info("Sistema notifiche audio attivato")
    
    return _audio_system

def get_audio_system():
    """Restituisce l'istanza del sistema audio"""
    return _audio_system

def cleanup_audio_notifications():
    """Pulisce il sistema di notifiche audio"""
    global _audio_system
    
    if _audio_system:
        _audio_system.remove_monkey_patches()
        _audio_system = None
        logging.info("Sistema notifiche audio disattivato")