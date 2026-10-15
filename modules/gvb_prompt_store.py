from PySide6.QtCore import QSettings

SETTINGS_ORG = "ComicLabs"
SETTINGS_APP = "KomicTranslate"
SETTINGS_GROUP = "gvb"
SETTINGS_KEY_PROMPT_TEXT = "prompt_text"


def load_gvb_prompt_text(default: str = "") -> str:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.beginGroup(SETTINGS_GROUP)
    try:
        value = settings.value(SETTINGS_KEY_PROMPT_TEXT, default, type=str)
        if value is None:
            return default
        return str(value)
    finally:
        settings.endGroup()


def save_gvb_prompt_text(text: str) -> None:
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.beginGroup(SETTINGS_GROUP)
    try:
        settings.setValue(SETTINGS_KEY_PROMPT_TEXT, str(text))
    finally:
        settings.endGroup()
