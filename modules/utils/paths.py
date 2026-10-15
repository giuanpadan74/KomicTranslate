import os
import sys

# Get the directory of the current file (modules/utils/)
current_file_dir = os.path.dirname(os.path.abspath(__file__))

# Navigate up two levels to reach the project root
PROJECT_ROOT = os.path.abspath(os.path.join(current_file_dir, '..', '..'))


def get_project_root() -> str:
    """Returns the absolute path to the project root."""
    return PROJECT_ROOT


def get_app_data_dir() -> str:
    r"""
    Returns the user data directory for KomicTranslate.
    On Windows: %APPDATA%\KomicTranslate
    Falls back to a temp directory if APPDATA is not available.
    """
    if sys.platform == "win32":
        appdata = os.environ.get('APPDATA')
        if appdata:
            return os.path.join(appdata, 'KomicTranslate')
    home = os.path.expanduser('~')
    if home:
        return os.path.join(home, '.komictranslate')
    import tempfile
    return os.path.join(tempfile.gettempdir(), 'KomicTranslate')


def get_log_dir(create: bool = True) -> str:
    r"""
    Returns the log directory for KomicTranslate.
    On Windows: %APPDATA%\KomicTranslate\logs
    Creates the directory if it doesn't exist (create=True).
    """
    log_dir = os.path.join(get_app_data_dir(), 'logs')
    if create:
        os.makedirs(log_dir, exist_ok=True)
    return log_dir


def _get_install_root() -> str:
    prog_files = os.environ.get('ProgramFiles', r'C:\Program Files')
    return os.path.join(prog_files, 'KomicTranslate')


def resource_path(relative_path: str) -> str:
    r"""
    Resolves a relative resource path for both development and installed environments.
    In development: returns path relative to project root.
    In installed environment (%ProgramFiles%):
      - If file exists in versions/X.Y.Z/, returns that.
      - Otherwise returns in Program Files root.
    """
    normalized = relative_path.replace('\\', '/')
    parts = [p for p in normalized.split('/') if p not in ('', '.')]
    dev_path = os.path.join(PROJECT_ROOT, *parts) if parts else PROJECT_ROOT
    if os.path.exists(dev_path):
        return dev_path
    if sys.platform == "win32":
        install_root = _get_install_root()
        current_txt = os.path.join(install_root, 'current.txt')
        version = None
        try:
            if os.path.isfile(current_txt):
                with open(current_txt, 'r', encoding='utf-8') as f:
                    version = f.read().strip()
        except OSError:
            version = None
        candidates = []
        if version:
            candidates.append(os.path.join(install_root, 'versions', version))
        try:
            if os.path.isdir(os.path.join(install_root, 'versions')):
                for d in sorted(os.listdir(os.path.join(install_root, 'versions')), reverse=True):
                    if d.startswith('v'):
                        p = os.path.join(install_root, 'versions', d)
                        if p not in candidates:
                            candidates.append(p)
        except OSError:
            pass
        for v_path in candidates:
            candidate = os.path.join(v_path, *parts) if parts else v_path
            if os.path.exists(candidate):
                return candidate
        return os.path.join(install_root, *parts) if parts else install_root
    return dev_path


def is_installed_environment() -> bool:
    r"""
    Checks if the application is running from an installed location.
    Returns True if running from %ProgramFiles%\KomicTranslate.
    """
    if os.environ.get('KOMIC_TRANSLATE_INSTALLED') == '1':
        return True
    if sys.platform != "win32":
        return False
    try:
        this_file = os.path.abspath(__file__)
        install_root = os.path.abspath(_get_install_root())
        if this_file.lower().startswith(install_root.lower() + os.sep):
            return True
    except Exception:
        pass
    return False


def is_bootstrap_gated() -> bool:
    r"""
    Returns True if bootstrap should be skipped.
    Skip when:
      - Running from installed environment
      - Environment variable KOMIC_TRANSLATE_INSTALLED is set to 1
      - Marker file exists at %APPDATA%\KomicTranslate\.installed
    """
    if os.environ.get('KOMIC_TRANSLATE_INSTALLED') == '1':
        return True
    try:
        marker = os.path.join(get_app_data_dir(), '.installed')
        if os.path.exists(marker):
            return True
    except Exception:
        pass
    return is_installed_environment()


def get_models_base_dir() -> str:
    r"""
    Returns the base directory for AI models.
    - Installed (%ProgramFiles%\KomicTranslate): %APPDATA%\KomicTranslate\models
      (Program Files non e' scrivibile, i pesi si scaricano al primo avvio).
    - Development: 'models' sotto project root (comportamento storico).
    Creates the directory if it doesn't exist.
    """
    if is_installed_environment():
        base = os.path.join(get_app_data_dir(), 'models')
        os.makedirs(base, exist_ok=True)
        return base
    dev_models_dir = os.path.join(PROJECT_ROOT, 'models')
    # Comportamento storico: usa la cartella dev se esiste, altrimenti creala.
    try:
        os.makedirs(dev_models_dir, exist_ok=True)
    except OSError:
        pass
    return dev_models_dir


def get_model_path(relative_path: str) -> str:
    """
    Resolves a relative model path to an absolute path.
    Example: 'detection/comic-speech-bubble-detector.pt' -> '.../models/detection/...'
    Strips a leading 'models/' prefix to avoid duplication (compatibilita'
    con le chiamate storiche tipo get_model_path('models/detection/...')).
    """
    base_dir = get_models_base_dir()
    normalized = relative_path.replace('\\', '/')
    if normalized.startswith('models/'):
        normalized = normalized[7:]
    parts = [p for p in normalized.split('/') if p not in ('', '.')]
    return os.path.abspath(os.path.join(base_dir, *parts) if parts else base_dir)
