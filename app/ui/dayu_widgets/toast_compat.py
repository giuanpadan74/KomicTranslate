"""
Wrapper di compatibilità per MToast che utilizza internamente PopupNotifier.
Fornisce la stessa interfaccia di MToast ma con un'implementazione più affidabile.
"""
from PySide6 import QtWidgets
from .popup_notifier import PopupNotifier

class MToast:
    """
    Wrapper per la compatibilità con il codice esistente che usa MToast.
    Utilizza internamente PopupNotifier per una migliore esperienza utente.
    """
    
    InfoType = "info"
    SuccessType = "success"
    WarningType = "warning"
    ErrorType = "error"
    LoadingType = "loading"
    
    default_config = {
        "duration": 3,  # 3 secondi di default
    }
    
    sig_closed = PopupNotifier.sig_closed
    
    @classmethod
    def info(cls, text, duration=None, parent=None):
        """Mostra un messaggio informativo"""
        dur = duration if duration is not None else cls.default_config["duration"]
        return PopupNotifier.info("Informazione", text, dur * 1000, parent)
    
    @classmethod
    def success(cls, text, duration=None, parent=None):
        """Mostra un messaggio di successo"""
        dur = duration if duration is not None else cls.default_config["duration"]
        return PopupNotifier.success("Successo", text, dur * 1000, parent)
    
    @classmethod
    def warning(cls, text, duration=None, parent=None):
        """Mostra un messaggio di avviso"""
        dur = duration if duration is not None else cls.default_config["duration"]
        return PopupNotifier.warning("Attenzione", text, dur * 1000, parent)
    
    @classmethod
    def error(cls, text, duration=0, parent=None):
        """
        Mostra un messaggio di errore
        Di default non si chiude automaticamente (duration=0)
        """
        return PopupNotifier.error("Errore", text, duration * 1000, parent)
    
    @classmethod
    def loading(cls, text, parent=None):
        """
        Mostra un indicatore di caricamento
        Non si chiude automaticamente (duration=0)
        """
        return PopupNotifier.info("Caricamento", text, 0, parent)
    
    @classmethod
    def config(cls, **kwargs):
        """Configura le impostazioni di default"""
        cls.default_config.update(kwargs)
        return cls
    
    def __new__(cls, text, duration=None, dayu_type=None, parent=None):
        """
        Costruttore per compatibilità con il codice esistente che istanzia MToast direttamente.
        Utilizza i metodi di classe appropriati in base al tipo.
        """
        if dayu_type == cls.SuccessType:
            return cls.success(text, duration, parent)
        elif dayu_type == cls.WarningType:
            return cls.warning(text, duration, parent)
        elif dayu_type == cls.ErrorType:
            return cls.error(text, duration, parent)
        elif dayu_type == cls.LoadingType:
            return cls.loading(text, parent)
        else:
            return cls.info(text, duration, parent)
