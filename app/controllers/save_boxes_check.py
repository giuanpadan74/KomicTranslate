"""Controllo preventivo obbligatorio per elementi Boxes prima del salvataggio.

Verifica che non siano presenti elementi grafici di tipo "Boxes"
(MoveableRectItem, MoveableEllipseItem) sovrapposti all'immagine
prima di ogni operazione di salvataggio. Se rilevati, vengono rimossi
automaticamente prima di procedere al salvataggio.

Modulo esposto:
  - ``auto_remove_boxes(viewer)`` -> bool (True = nessun box residuo)
"""

import logging
import os
from datetime import datetime
from typing import Optional
from shiboken6 import isValid

logger = logging.getLogger(__name__)


def count_boxes_on_image(viewer: Optional[object]) -> int:
    """Conta le istanze di MoveableRectItem e MoveableEllipseItem visibili."""
    if viewer is None:
        return 0

    rectangles = list(getattr(viewer, "rectangles", []) or [])
    stale_refs = []
    count = 0
    for rect in rectangles:
        try:
            if not rect or not isValid(rect):
                stale_refs.append(rect)
                continue
            if rect.isVisible() and rect.scene() is not None:
                count += 1
        except RuntimeError:
            stale_refs.append(rect)
            continue

    if stale_refs and hasattr(viewer, "rectangles"):
        viewer.rectangles = [
            rect for rect in viewer.rectangles
            if rect not in stale_refs
        ]
    return count


def _remove_all_boxes(viewer: object) -> int:
    """Rimuove tutti i boxes visibili dal viewer. Restituisce il numero rimosso."""
    from ..ui.canvas.rectangle import MoveableRectItem, MoveableEllipseItem
    from ..ui.canvas.polygon_overlay import remove_polygon_overlay

    scene = getattr(viewer, "_scene", None)
    if scene is None:
        return 0

    removed = 0
    stale_refs = []
    for rect in list(getattr(viewer, "rectangles", []) or []):
        try:
            if not rect or not isValid(rect):
                stale_refs.append(rect)
                continue
            if rect.isVisible() and rect.scene() is not None:
                remove_polygon_overlay(rect, viewer)
                scene.removeItem(rect)
                removed += 1
        except RuntimeError:
            stale_refs.append(rect)
            continue

    viewer.rectangles = [
        rect for rect in viewer.rectangles
        if rect not in stale_refs and isValid(rect) and rect.scene() is not None
    ]
    viewer.selected_rect = None
    viewer.clear_rect_item_markers()
    scene.update()
    return removed


def auto_remove_boxes(
    viewer: Optional[object],
    operation_name: str = "salvataggio",
) -> bool:
    """Rimuove automaticamente tutti i boxes rilevati. Ritorna True se
    il flusso di salvataggio può procedere (boxes rimossi o assenti)."""
    box_count = count_boxes_on_image(viewer)
    if box_count == 0:
        return True

    logger.info(
        "[BOXES_CHECK] Rilevati %d boxes per %s - rimozione automatica",
        box_count, operation_name,
    )
    removed = _remove_all_boxes(viewer)
    logger.info(
        "[BOXES_CHECK] Rimossi %d boxes prima di %s",
        removed, operation_name,
    )
    remaining = count_boxes_on_image(viewer)
    if remaining > 0:
        logger.warning(
            "[BOXES_CHECK] Ancora %d boxes dopo rimozione!", remaining
        )
    return remaining == 0


def log_save_operation(
    operation_name: str,
    file_path: str,
    success: bool,
    boxes_removed: int = 0,
    extra_info: str = "",
) -> None:
    """Registra un log dettagliato dell'operazione di salvataggio."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if success else "FALLITO"
    basename = os.path.basename(file_path) if file_path else "N/A"

    msg = (
        f"[SAVE_LOG] {timestamp} | {operation_name} | "
        f"file={basename} | stato={status}"
    )
    if boxes_removed > 0:
        msg += f" | boxes_rimossi={boxes_removed}"
    if extra_info:
        msg += f" | {extra_info}"

    if success:
        logger.info(msg)
    else:
        logger.error(msg)


def verify_image_integrity(file_path: str) -> bool:
    """Verifica che il file immagine salvato sia leggibile e non corrotto."""
    if not os.path.exists(file_path):
        logger.error("[SAVE_VERIFY] File non trovato: %s", file_path)
        return False

    if os.path.getsize(file_path) == 0:
        logger.error("[SAVE_VERIFY] File vuoto: %s", file_path)
        return False

    try:
        import cv2
        img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            logger.error("[SAVE_VERIFY] cv2.imread ha restituito None: %s", file_path)
            return False
        if img.size == 0:
            logger.error("[SAVE_VERIFY] Immagine con dimensione zero: %s", file_path)
            return False
        logger.info(
            "[SAVE_VERIFY] Integrità OK: %s (%dx%d, %d canali)",
            os.path.basename(file_path),
            img.shape[1], img.shape[0], img.shape[2] if len(img.shape) > 2 else 1,
        )
        return True
    except Exception as e:
        logger.error("[SAVE_VERIFY] Errore verifica integrità: %s -> %s", file_path, e)
        return False
