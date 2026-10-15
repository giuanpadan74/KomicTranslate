from .dayu_widgets.message import MMessage
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QCoreApplication

class Messages:
    @staticmethod
    def show_api_key_translator_error(parent):
        # Non piu' rimandare a Settings > Credentials: la pagina e' stata
        # rimossa con lo strato LLM. Ora l'unico provider online rimasto e'
        # Geminiamo, che usa i cookie di Firefox e non ha API key.
        MMessage.error(
            text=QCoreApplication.translate(
                "Messages",
                "Il traduttore selezionato richiede una API key, ma la gestione "
                "delle credenziali non e' piu' disponibile.\n"
                "Scegli Gemini o Dola (traduzione via browser) oppure Geminiamo."
            ),
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_api_key_ocr_error(parent):
        MMessage.error(
            text=QCoreApplication.translate(
                "Messages",
                "L'OCR selezionato richiede una API key, ma la gestione delle "
                "credenziali non e' piu' disponibile.\n"
                "Scegli PP-OCRv5 o MangaOCR (locali) oppure Geminiamo."
            ),
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_api_key_ocr_gpt4v_error(parent):
        # Controllo ormai irraggiungibile (l'OCR per il russo usa DocTR,
        # locale) e comunque non rimandiamo piu' a Credentials.
        MMessage.error(
            text=QCoreApplication.translate(
                "Messages",
                "L'OCR predefinito per la lingua selezionate richiederebbe una "
                "API key. Scegli un OCR locale (PP-OCRv5, MangaOCR) oppure "
                "Geminiamo."
            ),
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_endpoint_url_error(parent):
        MMessage.error(
    
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_deepl_ch_error(parent):
        MMessage.error(
            text=QCoreApplication.translate("Messages", "DeepL does not translate to Traditional Chinese"),
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_googlet_ptbr_error(parent):
        MMessage.error(
            text=QCoreApplication.translate("Messages", "Google Translate does not support Brazillian Portuguese"),
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_deepl_th_error(parent):
        MMessage.error(
            text=QCoreApplication.translate("Messages", "DeepL does not translate to Thai"),
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_deepl_vi_error(parent):
        MMessage.error(
            text=QCoreApplication.translate("Messages", "DeepL does not translate to Vietnamese"),
            parent=parent,
            duration=None,
            closable=True
        )

    @staticmethod
    def show_translation_complete(parent):
        MMessage.success(
            text=QCoreApplication.translate("Messages", "Comic has been Translated!"),
            parent=parent,
            duration=5,
            closable=True
        )

    @staticmethod
    def select_font_error(parent):
        MMessage.error(
            text=QCoreApplication.translate("Messages", "No Font selected.\nGo to Settings > Text Rendering > Font to select or import one "),
            parent=parent,
            duration=None,
            closable=True
        )
    
    @staticmethod
    def show_info(parent, title: str, message: str, duration: int = 3):
        """Mostra un messaggio informativo"""
        MMessage.info(
            text=message,
            parent=parent,
            duration=duration,
            closable=True
        )

    @staticmethod
    def show_temp_cleanup(parent):
        """Popup 'file temporanei _translated rimossi': DISATTIVATO.

        L'applicazione non salva piu' in automatico i file
        '<nome>_translated.<ext>' accanto agli originali, quindi il messaggio
        non descriveva piu' nulla di reale. La pulizia dei file obsoleti
        (_cleanup_stray_translated_files) continua a funzionare, ma senza
        notificare l'utente. Metodo mantenuto come no-op per non reintrodurre
        il popup da altri percorsi.
        """
        return

    @staticmethod
    def show_error(parent, title: str, message: str):
        """Mostra un messaggio di errore"""
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec()

    @staticmethod
    def show_warning(parent, title: str, message: str) -> bool:
        """Mostra un messaggio di avviso con Yes/No"""
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        return msg_box.exec() == QMessageBox.StandardButton.Yes

    @staticmethod
    def show_firefox_not_found_error(parent):
        """Firefox mancante: serve a GEMINIAMO, che legge i cookie da lì.

        Prima questo messaggio diceva "traduzione TXT", sbagliato: TXT e
        Dola girano in una webview propria (pywebview) e non usano Firefox.
        Firefox e' obbligatorio solo per Geminiamo, che legge i cookie
        direttamente dal profilo del browser.
        """
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Firefox non trovato")
        msg_box.setText(
            "Per usare Geminiamo è necessario avere Firefox installato: i "
            "cookie di accesso a gemini.google.com vengono letti dal suo profilo."
        )
        msg_box.setInformativeText(
            "1. Installa Firefox se non presente\n"
            "2. Apri Firefox e accedi a gemini.google.com\n"
            "3. Torna qui e scegli un altro traduttore (Gemini o Dola), "
            "che non richiedono Firefox"
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    @staticmethod
    def show_gemini_not_logged_error(parent):
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Accesso Gemini richiesto")
        msg_box.setText(
            "I cookie di Gemini non sono stati trovati in Firefox."
        )
        msg_box.setInformativeText(
            "Per risolvere:\n"
            "1. Apri Firefox\n"
            "2. Vai su gemini.google.com\n"
            "3. Effettua l'accesso con il tuo account Google\n"
            "4. Torna a KomicTranslate e riprova"
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    @staticmethod
    def show_gemini_session_expired(parent):
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Sessione Gemini scaduta")
        msg_box.setText(
            "La sessione di Gemini è scaduta."
        )
        msg_box.setInformativeText(
            "Apri Firefox, vai su gemini.google.com e effettua di nuovo l'accesso, poi riprova."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    @staticmethod
    def show_success(parent, title: str, message: str):
        """Mostra un messaggio di successo"""
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec()


def show_error(title: str, message: str, parent=None):
    """Wrapper per compatibilità"""
    Messages.show_error(parent, title, message)

def show_warning(title: str, message: str, parent=None) -> bool:
    """Wrapper per compatibilità"""
    return Messages.show_warning(parent, title, message)

def show_success(title: str, message: str, parent=None):
    """Wrapper per compatibilità"""
    Messages.show_success(parent, title, message)
