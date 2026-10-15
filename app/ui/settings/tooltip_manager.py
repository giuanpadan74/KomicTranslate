"""Gestore centralizzato dei tooltip dell'applicazione.

Carica/salva tooltip personalizzati tramite QSettings.
Ogni tooltip ha una chiave univoca, un testo default e opzionalmente un testo personalizzato.
"""

from PySide6.QtCore import QSettings


# Dizionario dei tooltip di default, organizzati per gruppo.
# Chiave: identificativo univoco del widget
# Valore: testo default del tooltip
DEFAULT_TOOLTIPS = {
    # --- Navigazione / File ---
    "tool_browser": "Import Images, PDFs, Epubs or Comic Book Archive Files(cbr, cbz, etc)",
    "save_browser": "Save Currently Loaded Image",
    "export_pdf": "Export to PDF",
    "undo": "Annulla l'ultima azione",
    "save_project": "Save Project",
    "save_as_project": "Save as",
    "join_ctpr": "Join CTPR Files",
    "comic_info": "Scheda fumetto (ComicInfo.xml)",
    "save_all_browser": "Export all Images",
    "polygons": "Mostra/nascondi i poligoni (nascosti non sono cliccabili)",
    "rect_boxes": "Mostra/nascondi le caselle di testo dell'OCR (nascoste non sono cliccabili)",
    "drag_browser": "Import Images, PDFs, Epubs or Comic Book Archive Files(cbr, cbz, etc)",

    # --- Text Rendering ---
    "detect_font": "Analyze and detect fonts in text blocks",
    "auto_center": "Center text automatically in speech bubbles",
    "s_combo": "Source Language",
    "t_combo": "Target Language",
    "font_dropdown": "Font",
    "font_size_dropdown": "Font Size",
    "line_spacing_dropdown": "Line Spacing",
    "remove_newlines": "Rimuovi caratteri di a capo dal testo TARGET",
    "polygon_text": "Attiva o disattiva il layout pentagonale per il testo selezionato",
    "block_font_color": "Font Color",
    "bold": "Bold",
    "italic": "Italic",
    "underline": "Underline",
    "outline_font_color": "Outline Color",
    "outline_width": "Outline Width",
    "save_model": "Salva le impostazioni font correnti come modello",
    "model_selector": "Seleziona modello font salvato",
    "delete_model": "Cancella modello selezionato",
    "default_model": "Carica il modello font di default",
    "copy_to_target": "Copia tutto il testo da Source a Target",

    # --- Selezione & Box ---
    "box_button": "Draw or Select Text Boxes",
    "delete_button": "Delete Selected Box",
    "clear_rectangles": "Remove all the Boxes on the Image",
    "toggle_shape": "Toggle Rectangle/Ellipse Shape",
    "draw_blklist_blks": "Draws all the Text Blocks in the existing Text Block List\nback on the Image (for further editing)",
    "change_all_blocks_size_dec": "Reduce the size of all blocks",
    "change_all_blocks_size_inc": "Increase the size of all blocks",
    "pan_button": "Pan Image",
    "move_box": "Sposta casella di testo",
    "set_all_button": "Sets the Source and Target Language on the current page for all pages",

    # --- Inpainting ---
    "brush_button": "Pulisci Immagine (Inpainting Brush)",
    "eraser_button": "Erase Brush Strokes",
    "clear_brush_strokes": "Remove all the brush strokes on the Image",
    "tool_sbianchetta": "Pulisce i balloon di testo da tutte le immagini senza tradurli",

    # --- Painting ---
    "pen_button": "Penna",
    "bucket_button": "Secchiello",

    # --- Canvas & SVG ---
    "svg_button": "Inserisci file SVG",
    "delete_shape": "Elimina Forma",
    "border_width_selector": "Spessore bordo (0 per nascondere)",
    "reset_styles": "Ripristina stili originali",
    "save_svg": "Salva SVG modificato",
    "bring_front": "Porta in primo piano",
    "send_back": "Porta in secondo piano",
    "opacity_slider": "Opacità pennello (1-100%)",
    "inpainter_model": "Seleziona il modello di inpainting da utilizzare",
}

# Nomi leggibili per i gruppi (per la UI delle impostazioni)
TOOLTIP_GROUPS = {
    "Navigazione / File": [
        "tool_browser", "save_browser", "export_pdf", "save_project",
        "save_as_project", "join_ctpr", "comic_info", "save_all_browser", "drag_browser",
        "polygons", "rect_boxes",
    ],
    "Text Rendering": [
        "detect_font", "auto_center", "s_combo", "t_combo",
        "font_dropdown", "font_size_dropdown", "line_spacing_dropdown",
        "remove_newlines", "block_font_color", "bold", "italic", "underline",
        "outline_font_color", "outline_width", "save_model", "model_selector",
        "delete_model", "default_model", "copy_to_target",
    ],
    "Selezione & Box": [
        "box_button", "delete_button", "clear_rectangles", "toggle_shape", "draw_blklist_blks",
        "change_all_blocks_size_dec", "change_all_blocks_size_inc",
        "pan_button", "set_all_button",
    ],
    "Inpainting": [
        "brush_button", "eraser_button", "clear_brush_strokes",
        "tool_sbianchetta",
    ],
    "Painting": [
        "pen_button", "bucket_button",
    ],
    "Canvas & SVG": [
        "svg_button", "delete_shape", "border_width_selector",
        "reset_styles", "save_svg", "bring_front", "send_back",
        "opacity_slider", "inpainter_model",
    ],
}


class TooltipManager:
    """Gestisce i tooltip personalizzati dell'applicazione."""

    SETTINGS_GROUP = "CustomTooltips"

    def __init__(self):
        self._custom: dict[str, str] = {}
        self.load()

    def get(self, key: str, shortcut: str = None) -> str:
        """Restituisce il tooltip personalizzato oppure il default, con scorciatoia opzionale."""
        text = self._custom.get(key, DEFAULT_TOOLTIPS.get(key, ""))
        if shortcut:
            return f"{text} ({shortcut})"
        return text

    def set(self, key: str, text: str):
        """Imposta un tooltip personalizzato."""
        self._custom[key] = text

    def reset(self, key: str):
        """Ripristina un tooltip al suo valore di default."""
        self._custom.pop(key, None)

    def reset_all(self):
        """Ripristina tutti i tooltip ai valori default."""
        self._custom.clear()

    def is_custom(self, key: str) -> bool:
        """Verifica se un tooltip è stato personalizzato."""
        return key in self._custom

    def get_default(self, key: str) -> str:
        """Restituisce il tooltip di default per una chiave."""
        return DEFAULT_TOOLTIPS.get(key, "")

    def save(self):
        """Salva i tooltip personalizzati in QSettings."""
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        settings.remove("")  # Pulisce il gruppo
        for key, text in self._custom.items():
            settings.setValue(key, text)
        settings.endGroup()

    def load(self):
        """Carica i tooltip personalizzati da QSettings."""
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        self._custom.clear()
        for key in settings.childKeys():
            self._custom[key] = settings.value(key, "")
        settings.endGroup()

    @staticmethod
    def all_keys():
        """Restituisce tutte le chiavi di tooltip disponibili."""
        return list(DEFAULT_TOOLTIPS.keys())
