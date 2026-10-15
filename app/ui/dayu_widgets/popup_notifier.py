from PySide6 import QtWidgets, QtCore, QtGui  # QtGui usato per QPixmap in show_message
from PySide6.QtCore import Qt, Signal

class PopupNotifier(QtCore.QObject):
    """
    Una classe per mostrare notifiche popup con chiusura automatica.
    Sostituto più affidabile per MToast.
    """
    sig_closed = Signal()  # Segnale emesso quando la notifica viene chiusa
    
    # Definizione dei tipi di messaggio
    Info = "info"
    Success = "success"
    Warning = "warning"
    Error = "error"
    
    # Mappatura dei tipi di messaggio agli stili
    STYLES = {
        Info: """
            QMessageBox {
                background-color: #f0f9ff;
                color: #0369a1;
                border: 1px solid #bae6fd;
                border-radius: 4px;
            }
            QLabel {
                color: #0369a1;
            }
        """,
        Success: """
            QMessageBox {
                background-color: #f0fdf4;
                color: #15803d;
                border: 1px solid #bbf7d0;
                border-radius: 4px;
            }
            QLabel {
                color: #15803d;
            }
        """,
        Warning: """
            QMessageBox {
                background-color: #fffbeb;
                color: #b45309;
                border: 1px solid #fde68a;
                border-radius: 4px;
            }
            QLabel {
                color: #b45309;
            }
        """,
        Error: """
            QMessageBox {
                background-color: #fef2f2;
                color: #b91c1c;
                border: 1px solid #fecaca;
                border-radius: 4px;
            }
            QLabel {
                color: #b91c1c;
            }
        """
    }
    
    @classmethod
    def show_message(cls, title, message, message_type=Info, duration=5000, parent=None):
        """
        Mostra un messaggio popup con chiusura automatica.
        
        Args:
            title (str): Titolo del messaggio
            message (str): Testo del messaggio
            message_type (str): Tipo di messaggio (Info, Success, Warning, Error)
            duration (int): Durata in millisecondi prima della chiusura automatica
            parent (QWidget, optional): Widget genitore
        """
        # Crea un QMessageBox personalizzato
        msg_box = QtWidgets.QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        
        # Imposta l'icona in base al tipo di messaggio
        if message_type == cls.Info:
            msg_box.setIcon(QtWidgets.QMessageBox.Information)
        elif message_type == cls.Success:
            msg_box.setIcon(QtWidgets.QMessageBox.Information)
            msg_box.setIconPixmap(QtGui.QPixmap(":/icons/success.svg"))
        elif message_type == cls.Warning:
            msg_box.setIcon(QtWidgets.QMessageBox.Warning)
        elif message_type == cls.Error:
            msg_box.setIcon(QtWidgets.QMessageBox.Critical)
        
        # Applica lo stile appropriato
        if message_type in cls.STYLES:
            msg_box.setStyleSheet(cls.STYLES[message_type])
        
        # Rimuovi i pulsanti standard e aggiungi solo OK
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        ok_button = msg_box.button(QtWidgets.QMessageBox.Ok)
        ok_button.setText("Chiudi")
        
        # Imposta il flag per la chiusura automatica
        msg_box.setWindowFlags(
            Qt.Window | 
            Qt.WindowStaysOnTopHint | 
            Qt.FramelessWindowHint | 
            Qt.WindowDoesNotAcceptFocus
        )
        
        # Mostra il messaggio
        msg_box.show()
        
        # Centra il messaggio rispetto al genitore o allo schermo
        if parent:
            msg_box.move(
                parent.x() + (parent.width() - msg_box.width()) // 2,
                parent.y() + 50  # 50px dal bordo superiore del genitore
            )
        else:
            screen = QtWidgets.QApplication.primaryScreen().geometry()
            msg_box.move(
                (screen.width() - msg_box.width()) // 2,
                50  # 50px dal bordo superiore dello schermo
            )
        
        # Timer per la chiusura automatica
        if duration > 0:
            timer = QtCore.QTimer(msg_box)
            timer.setSingleShot(True)
            timer.timeout.connect(msg_box.accept)
            timer.start(duration)
        
        return msg_box
    
    # Metodi di convenienza
    @classmethod
    def info(cls, title, message, duration=5000, parent=None):
        return cls.show_message(title, message, cls.Info, duration, parent)
    
    @classmethod
    def success(cls, title, message, duration=5000, parent=None):
        return cls.show_message(title, message, cls.Success, duration, parent)
    
    @classmethod
    def warning(cls, title, message, duration=5000, parent=None):
        return cls.show_message(title, message, cls.Warning, duration, parent)
    
    @classmethod
    def error(cls, title, message, duration=5000, parent=None):
        return cls.show_message(title, message, cls.Error, duration, parent)
