"""Regole condivise per i layer del contenuto del canvas."""

from PySide6.QtWidgets import QGraphicsPathItem

from .z_layers import BRUSH_STROKE_Z, TEXT_BOX_Z


def apply_brush_stroke_layer(path_item: QGraphicsPathItem) -> QGraphicsPathItem:
    """Forza il layer canonico dei tratti brush sotto alle text box."""
    path_item.setZValue(BRUSH_STROKE_Z)
    return path_item


def apply_text_box_layer(text_item):
    """Forza il layer canonico delle text box sopra al contenuto disegnato."""
    text_item.setZValue(TEXT_BOX_Z)
    return text_item


def ensure_text_items_layer(text_items) -> None:
    """Riporta tutti i text item validi sul layer testo canonico."""
    for text_item in text_items:
        if text_item is None:
            continue
        try:
            apply_text_box_layer(text_item)
        except RuntimeError:
            continue
