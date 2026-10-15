import time
from typing import Dict

from PySide6.QtWidgets import QApplication

from modules.gemini_translation_payload import parse_translation_payload


def extract_translations_from_clipboard(expected_count: int) -> Dict[str, str]:
    app = QApplication.instance()
    if app is None:
        return {}
    for _ in range(5):
        clipboard_text = app.clipboard().text().strip()
        parsed, report = parse_translation_payload(clipboard_text, expected_count)
        if report.get("is_valid"):
            return parsed
        time.sleep(0.25)
    return {}


def extract_keyed_json_from_clipboard() -> Dict[str, object]:
    app = QApplication.instance()
    if app is None:
        return {}
    for _ in range(5):
        clipboard_text = app.clipboard().text().strip()
        parsed, _ = parse_translation_payload(clipboard_text, expected_count=0)
        if isinstance(parsed, dict) and "block_1" in parsed:
            return parsed
        time.sleep(0.25)
    return {}
