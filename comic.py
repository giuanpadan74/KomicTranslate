import os, sys
import logging
from datetime import datetime
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import QSettings, QTranslator, QLocale, Qt, QSize
from PySide6.QtWidgets import QApplication, QSplashScreen, QLabel, QProgressBar, QVBoxLayout, QWidget
from app import icon_resource

try:
    from modules.utils.paths import is_installed_environment as _is_installed_env
    if _is_installed_env():
        sys.dont_write_bytecode = True
        os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
except Exception:
    pass

def _force_utf8_stdio():
    """Forza stdout/stderr in UTF-8 con errors='replace'.

    Su console Windows (cp1252) qualsiasi print() di testo CJK/emoji/
    box-drawing solleva "UnicodeEncodeError: 'charmap' codec can't encode" e
    fa fallire il worker batch con il dialogo "An error occurred". Con
    UTF-8+replace le stampe non possono piu' sollevare (al massimo mostrano
    caratteri sostituiti). Sotto --noconsole gli stream possono mancare o
    essere dummy: tutto e' protetto.
    """
    for _name in ('stdout', 'stderr'):
        try:
            _stream = getattr(sys, _name, None)
            if _stream is None:
                continue
            _reconfigure = getattr(_stream, 'reconfigure', None)
            if callable(_reconfigure):
                _reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

_force_utf8_stdio()

def setup_logging():
    try:
        from modules.utils.paths import get_log_dir as _get_log_dir
        logs_dir = _get_log_dir(create=True)
    except Exception:
        logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(logs_dir, exist_ok=True)

    # Rotazione: mantieni solo i 10 log più recenti
    existing_logs = sorted(
        [f for f in os.listdir(logs_dir) if f.startswith('komictranslate_debug_') and f.endswith('.log')],
        reverse=True
    )
    for old_log in existing_logs[9:]:
        try:
            os.remove(os.path.join(logs_dir, old_log))
        except OSError:
            pass

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f'komictranslate_debug_{timestamp}.log')
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    stream_handler = logging.StreamHandler(sys.stdout)
    from modules.logging.auto_logger import ColorFormatter
    stream_handler.setFormatter(ColorFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    
    # Suppress matplotlib debug logs
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)
    
    logger = logging.getLogger('KomicTranslate')
    logger.info(f"=== AVVIO KomicTranslate - Log salvato in: {log_file} ===")
    logger.info(f"Versione Python: {sys.version}")
    logger.info(f"Sistema operativo: {sys.platform}")
    return logger


def create_splash_screen(app):
    """Crea uno splash screen con progress bar."""
    try:
        from modules.utils.paths import resource_path as _rp
        splash_path = _rp(os.path.join("assets", "icons", "komictranslate_icon.png"))
    except Exception:
        splash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons", "komictranslate_icon.png")

    if os.path.exists(splash_path):
        pixmap = QPixmap(splash_path)
    else:
        pixmap = QPixmap(400, 300)
        pixmap.fill(QColor("#1a1a2e"))

    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint)

    label = QLabel("Komic Translate", splash)
    
    logo_label = QLabel(splash)
    try:
        from modules.utils.paths import resource_path as _rp2
        logo_path = _rp2("KomicTranslate.png")
    except Exception:
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "KomicTranslate.png")
    logo_pixmap = QPixmap(logo_path)
    if not logo_pixmap.isNull():
        logo_pixmap = logo_pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("background: transparent;")

    label.setStyleSheet("""
        QLabel {
            color: #ffffff;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
        }
    """)
    label.setAlignment(Qt.AlignCenter)

    progress_label = QLabel("Inizializzazione...", splash)
    progress_label.setStyleSheet("""
        QLabel {
            color: #aaaaaa;
            font-size: 12px;
            background: transparent;
        }
    """)
    progress_label.setAlignment(Qt.AlignCenter)

    progress_bar = QProgressBar(splash)
    progress_bar.setMaximum(100)
    progress_bar.setValue(0)
    progress_bar.setMaximumWidth(300)
    progress_bar.setStyleSheet("""
        QProgressBar {
            border: 1px solid #444444;
            border-radius: 5px;
            text-align: center;
            background-color: #2a2a3e;
            color: #ffffff;
        }
        QProgressBar::chunk {
            background-color: #4CAF50;
            border-radius: 4px;
        }
    """)

    layout = QVBoxLayout()
    layout.addStretch()
    layout.addWidget(logo_label)
    layout.addWidget(label)

    layout.addWidget(progress_label)
    layout.addWidget(progress_bar)
    layout.addStretch()

    container = QWidget(splash)
    container.setLayout(layout)
    container.setGeometry(0, pixmap.height() - 320, pixmap.width(), 320)
    container.setAttribute(Qt.WA_TranslucentBackground)

    splash.progress_label = progress_label
    splash.progress_bar = progress_bar

    return splash


def update_splash_progress(splash, message, progress=None):
    """Aggiorna il messaggio e la progress bar dello splash screen."""
    if splash and splash.progress_label:
        splash.progress_label.setText(message)
        splash.progress_label.repaint()
    if splash and splash.progress_bar and progress is not None:
        splash.progress_bar.setValue(progress)
        splash.progress_bar.repaint()
    if splash:
        splash.repaint()


def main():
    global logger
    splash = None

    try:
        app = QApplication(sys.argv)
        splash = create_splash_screen(app)
        splash.show()
        splash.repaint()
        # B4 fix: logging setup (include os.listdir for log rotation) moved AFTER
        # splash.show() so the window is visible before any blocking I/O occurs.
        update_splash_progress(splash, "Configurazione logging...", 10)
        logger = setup_logging()

        if sys.platform == "win32":
            os.environ['QT_LOGGING_RULES'] = 'qt.qpa.fonts.warning=false'
            flags = "--disable-features=WebAuthentication,WebAuth,WebAuthn"
            if "QTWEBENGINE_CHROMIUM_FLAGS" in os.environ:
                os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] += f" {flags}"
            else:
                os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
            QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
            update_splash_progress(splash, "Configurazione Windows...", 20)
            logger.info("Configurazione Windows completata")

        update_splash_progress(splash, "Caricamento icone...", 35)
        icon = QIcon()
        try:
            from modules.utils.paths import resource_path as _rp3
            base_path = _rp3(os.path.join("assets", "icons"))
        except Exception:
            base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")

        ico_path = os.path.join(base_path, "komictranslate_icon.ico")
        if os.path.exists(ico_path):
            icon.addFile(ico_path)
            logger.debug(f"Icona .ico caricata da: {ico_path}")

        png_sizes = [16, 32, 48, 64, 128, 256]
        for size in png_sizes:
            png_path = os.path.join(base_path, f"komictranslate_icon_{size}.png")
            if os.path.exists(png_path):
                icon.addFile(png_path, QSize(size, size))
                logger.debug(f"Icona PNG {size}x{size} aggiunta da: {png_path}")

        if icon.isNull():
            svg_path = os.path.join(base_path, "komictranslate_icon.svg")
            if os.path.exists(svg_path):
                icon.addFile(svg_path)
                logger.debug(f"Icona SVG caricata da: {svg_path}")
            else:
                logger.warning("Nessuna icona trovata")

        if not icon.isNull():
            app.setWindowIcon(icon)
            logger.info("Icona applicazione impostata con successo")
        else:
            logger.error("Impossibile caricare alcuna icona")

        update_splash_progress(splash, "Configurazione barra applicazioni...", 40)

        if sys.platform == "win32":
            try:
                import ctypes
                myappid = u'ComicLabs.KomicTranslate.1.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
                if not icon.isNull():
                    app.setProperty("windowIcon", icon)
                logger.info("Workaround avanzato icona barra delle applicazioni Windows applicato")
            except Exception as e:
                logger.error(f"Errore nell'applicazione del workaround Windows: {e}")

        update_splash_progress(splash, "Caricamento lingua...", 45)
        settings = QSettings("ComicLabs", "KomicTranslate")
        selected_language = settings.value('language', get_system_language())
        logger.info(f"Lingua selezionata: {selected_language}")
        if selected_language != 'English':
            load_translation(app, selected_language)
            logger.info(f"Traduzione caricata per: {selected_language}")

        update_splash_progress(splash, "Inizializzazione ComicTranslate...", 55)
        logger.info("Inizializzazione ComicTranslate...")
        from controller import ComicTranslate
        ct = ComicTranslate()
        logger.info("ComicTranslate inizializzato")

        update_splash_progress(splash, "Attivazione sistema notifiche...", 85)
        from modules.audio_notifications import initialize_audio_notifications
        audio_system = initialize_audio_notifications(ct)
        logger.info("Sistema notifiche audio attivato")

        if len(sys.argv) > 1:
            project_file = sys.argv[1]
            logger.info(f"Argomento file ricevuto: {project_file}")
            if os.path.exists(project_file) and project_file.endswith(".ctpr"):
                logger.info(f"Caricamento progetto: {project_file}")
                ct.thread_load_project(project_file)
            else:
                logger.warning(f"File progetto non valido o non esistente: {project_file}")

        update_splash_progress(splash, "Avvio interfaccia...", 95)
        logger.info("Mostrando interfaccia principale")
        ct.show()

        update_splash_progress(splash, "Completato!", 100)
        splash.finish(ct)

        logger.info("Avvio event loop Qt")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Errore fatale durante l'avvio: {e}", exc_info=True)
        if splash:
            splash.close()
        sys.exit(1)


def get_system_language():
    locale = QLocale.system().name()  # Returns something like "en_US" or "zh_CN"
    
    # Special handling for Chinese
    if locale.startswith('zh_'):
        if locale in ['zh_CN', 'zh_SG']:
            return '简体中文'
        elif locale in ['zh_TW', 'zh_HK']:
            return '繁體中文'
    
    # For other languages, we can still use the first part of the locale
    lang_code = locale.split('_')[0]
    
    # Map the system language code to your application's language names
    lang_map = {
        'en': 'English',
        'ko': '한국어',
        'fr': 'Français',
        'ja': '日本語',
        'ru': 'русский',
        'de': 'Deutsch',
        'nl': 'Nederlands',
        'es': 'Español',
        'it': 'Italiano',
        'tr': 'Türkçe'
    }
    
    return lang_map.get(lang_code, 'English')  # Default to English if not found

def load_translation(app, language: str):
    logger = logging.getLogger('KomicTranslate.Translation')
    logger.debug(f"Caricamento traduzione per lingua: {language}")
    
    translator = QTranslator(app)
    lang_code = {
        'English': 'en',
        '한국어': 'ko',
        'Français': 'fr',
        '日本語': 'ja',
        '简体中文': 'zh_CN',
        '繁體中文': 'zh_TW',
        'русский': 'ru',
        'Deutsch': 'de',
        'Nederlands': 'nl',
        'Español': 'es',
        'Italiano': 'it',
        'Türkçe': 'tr'
    }.get(language, 'en')
    
    logger.debug(f"Codice lingua mappato: {lang_code}")

    # Prova a caricare dalle risorse Qt compilate
    translation_file = f":/translations/ct_{lang_code}.qm"
    logger.debug(f"Tentativo di caricamento file traduzione: {translation_file}")
    
    if translator.load(translation_file):
        app.installTranslator(translator)
        logger.info(f"Traduzione caricata con successo per {language} ({lang_code})")
    else:
        # Fallback: prova a caricare da file .qm separato
        try:
            from modules.utils.paths import resource_path as _rp4
            fallback_path = _rp4(os.path.join("app", "translations", f"ct_{lang_code}.qm"))
        except Exception:
            fallback_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "translations", f"ct_{lang_code}.qm")
        logger.debug(f"Tentativo fallback file traduzione: {fallback_path}")
        
        if translator.load(fallback_path):
            app.installTranslator(translator)
            logger.info(f"Traduzione caricata con fallback per {language} ({lang_code})")
        else:
            logger.error(f"Fallito caricamento traduzione per {language} ({lang_code})")
            print(f"Failed to load translation for {language}")

if __name__ == "__main__":
    main()
