"""Gestore delle scorciatoie da tastiera dell'applicazione.

Permette di definire scorciatoie di default e caricarne di personalizzate da
QSettings, usando un formato canonico per evitare ambiguita' tra layout tastiera.
"""

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence


DELETE_SHORTCUT_TOKEN = "StandardKey.Delete"
_DELETE_ALIASES = {"del", "delete", "canc"}
DELETE_SHAPE_CANDIDATES = ("Shift+Delete", "Alt+Delete", "Ctrl+Shift+Delete")


def normalize_shortcut_text(shortcut_text: str) -> str:
    """Normalizza una scorciatoia in un formato stabile e salvabile."""
    text = (shortcut_text or "").strip()
    if not text:
        return ""
    if text == DELETE_SHORTCUT_TOKEN:
        return text

    parts = [part.strip() for part in text.split("+") if part.strip()]
    normalized_parts = []
    for part in parts:
        normalized_parts.append("Delete" if part.casefold() in _DELETE_ALIASES else part)

    normalized_text = "+".join(normalized_parts)
    if normalized_text == "Delete":
        return DELETE_SHORTCUT_TOKEN
    return normalized_text


def format_shortcut_for_display(shortcut_text: str) -> str:
    """Converte una scorciatoia canonica in un testo leggibile per la UI."""
    normalized_text = normalize_shortcut_text(shortcut_text)
    if normalized_text == DELETE_SHORTCUT_TOKEN:
        return "Delete"
    return normalized_text


# Definizione delle scorciatoie di default
DEFAULT_SHORTCUTS = {
    # --- File ---
    "open_file": "Ctrl+O",
    "save_image": "Ctrl+S",
    "save_project": "Ctrl+Shift+S",
    "export_pdf": "Ctrl+E",
    "save_all": "Ctrl+Alt+S",
    
    # --- Generale ---
    "undo": "Ctrl+Z",
    "redo": "Ctrl+Y",
    
    # --- Navigazione ---
    "page_up": "PageUp",
    "page_down": "PageDown",
    
    # --- Operazioni Core ---
    "detect_text": "Ctrl+Shift+D",
    "ocr_text": "Ctrl+Shift+O",
    "translate_text": "Ctrl+Shift+T",
    "render_text": "Ctrl+Shift+R",
    "original_view": "Ctrl+0",
    "detect_font": "Ctrl+Shift+F",
    "auto_center": "Ctrl+Shift+C",
    
    # --- Batch ---
    "detect_all": "Ctrl+Alt+D",
    "translate_all": "Ctrl+Alt+T",
    "toggle_markers": "Ctrl+M",
    "toggle_polygons": "",
    "toggle_rect_boxes": "",
    
    # --- Box ---
    "toggle_box": "B",
    "delete_box": DELETE_SHORTCUT_TOKEN,
    "clear_boxes": "Ctrl+Delete",
    "pan_tool": "Space",
    "move_box": "Ins",
    
    # --- Inpainting ---
    "inpaint_brush": "I",
    "inpaint_eraser": "E",
    "clear_inpaint": "Ctrl+Alt+I",
    
    # --- Painting ---
    "paint_pen": "P",
    "paint_bucket": "G",
    "color_picker": "C",
    
    # --- Canvas & SVG ---
    "svg_tool": "S",
    "delete_shape": "Shift+Delete",
    "bring_to_front": "Ctrl+F",
    "send_to_back": "Ctrl+B",
    
    # --- Vista ---
    "fit_width": "Ctrl+1",
    "fit_height": "Ctrl+2",
    
    # --- File extra ---
    "save_as_project": "Ctrl+Shift+A",
    "comic_info": "Ctrl+I",
}

# Gruppi per la UI delle impostazioni
SHORTCUT_GROUPS = {
    "Generale": ["undo"],
    "Navigazione": ["page_up", "page_down"],
    "Operazioni Core": ["detect_text", "ocr_text", "translate_text", "render_text", "original_view", "detect_font", "auto_center"],
    "Batch": ["detect_all", "translate_all", "toggle_markers", "toggle_polygons", "toggle_rect_boxes"],
    "Selezione & Box": ["toggle_box", "pan_tool", "delete_box", "clear_boxes", "move_box"],
    "Inpainting": ["inpaint_brush", "inpaint_eraser", "clear_inpaint"],
    "Painting": ["paint_pen", "paint_bucket", "color_picker"],
    "Canvas & SVG": ["svg_tool", "delete_shape", "bring_to_front", "send_to_back"],
    "Scheda fumetto": ["comic_info"],
}

class ShortcutManager:
    """Gestisce le scorciatoie da tastiera personalizzate."""

    SETTINGS_GROUP = "KeyboardShortcuts"

    def __init__(self):
        self._custom: dict[str, str] = {}
        self.load()

    def _get_raw(self, key: str) -> str:
        return self._custom.get(key, DEFAULT_SHORTCUTS.get(key, ""))

    def _pick_delete_shape_shortcut(self, delete_box_shortcut: str) -> str:
        normalized_box = normalize_shortcut_text(delete_box_shortcut)
        for candidate in DELETE_SHAPE_CANDIDATES:
            normalized_candidate = normalize_shortcut_text(candidate)
            if normalized_candidate != normalized_box:
                return normalized_candidate
        return normalize_shortcut_text(DEFAULT_SHORTCUTS["delete_shape"])

    def _ensure_distinct_delete_shortcuts(self) -> None:
        delete_box_shortcut = normalize_shortcut_text(self._get_raw("delete_box"))
        delete_shape_shortcut = normalize_shortcut_text(self._get_raw("delete_shape"))
        if not delete_box_shortcut or not delete_shape_shortcut:
            return
        if delete_box_shortcut == delete_shape_shortcut:
            self._custom["delete_shape"] = self._pick_delete_shape_shortcut(
                delete_box_shortcut
            )

    def get(self, key: str) -> str:
        """Restituisce la scorciatoia in formato leggibile per la UI."""
        return format_shortcut_for_display(self._get_raw(key))

    def get_sequence(self, key: str) -> QKeySequence:
        """Restituisce un oggetto QKeySequence per la chiave data."""
        shortcut_text = self._get_raw(key)
        if shortcut_text == DELETE_SHORTCUT_TOKEN:
            return QKeySequence(QKeySequence.StandardKey.Delete)
        return QKeySequence(shortcut_text)

    def set(self, key: str, shortcut_text: str):
        """Imposta una scorciatoia personalizzata."""
        self._custom[key] = normalize_shortcut_text(shortcut_text)
        self._ensure_distinct_delete_shortcuts()

    def reset(self, key: str):
        """Ripristina una scorciatoia al suo valore di default."""
        self._custom.pop(key, None)

    def reset_all(self):
        """Ripristina tutte le scorciatoie ai valori default."""
        self._custom.clear()

    def save(self):
        """Salva le scorciatoie personalizzate in QSettings."""
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        settings.remove("")  # Pulisce il gruppo prima di salvare
        for key, text in self._custom.items():
            if text:
                settings.setValue(key, text)
        settings.endGroup()

    def load(self):
        """Carica le scorciatoie personalizzate da QSettings."""
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        self._custom.clear()
        for key in settings.childKeys():
            val = settings.value(key, "")
            if val:
                self._custom[key] = normalize_shortcut_text(str(val))
        settings.endGroup()
        self._ensure_distinct_delete_shortcuts()

    @staticmethod
    def get_default(key: str) -> str:
        """Restituisce la scorciatoia di default per una chiave."""
        return format_shortcut_for_display(DEFAULT_SHORTCUTS.get(key, ""))
