"""Cleanup obbligatorio per operazioni di salvataggio ed esportazione.

Prima di ogni salvataggio o esportazione, il sistema deve rimuovere
temporaneamente dal viewer gli elementi grafici proibiti:

  * Marcatori (text_item_markers, rect_item_markers)
  * Caselle di testo aggiuntive (rectangles / MoveableRectItem)
  * Poligoni disegnati sull'immagine (polygon_overlays)

Gli elementi che DEVONO essere conservati nell'output sono esclusivamente:

  * L'immagine originale (photo / QGraphicsPixmapItem)
  * Le scritte vettoriali (text_items / TextBlockItem)

Questo modulo espone:
  * ``find_prohibited_elements(viewer)`` - conteggio per categoria
  * ``prohibited_elements_hidden(viewer)`` - context manager
  * ``verify_prohibited_count(viewer, op_name)`` - log diagnostico
"""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional


# Costanti che identificano ciascuna categoria di elemento vietato.
PROHIBITED_MARKERS = "markers"
PROHIBITED_TEXT_BOXES = "text_boxes"
PROHIBITED_POLYGONS = "polygons"

ALL_PROHIBITED_CATEGORIES = (
    PROHIBITED_MARKERS,
    PROHIBITED_TEXT_BOXES,
    PROHIBITED_POLYGONS,
)


def _safe_set_visible(item: Any, visible: bool) -> bool:
    """Imposta ``visible`` su un item grafico, gestendo C++ gia' deleti."""
    if item is None:
        return False
    try:
        scene = item.scene()
    except RuntimeError:
        return False
    if scene is None:
        return False
    try:
        item.setVisible(visible)
        return True
    except (RuntimeError, AttributeError):
        return False


def _safe_is_visible(item: Any) -> bool:
    """Legge ``isVisible()`` gestendo item con C++ gia' deleti."""
    if item is None:
        return False
    try:
        return bool(item.isVisible())
    except (RuntimeError, AttributeError):
        return False


def _hide_and_record(item: Any, bucket: List[Any]) -> None:
    """Nasconde l'item e registra (item, visibilita' precedents) per il ripristino."""
    previous = _safe_is_visible(item)
    if _safe_set_visible(item, False):
        bucket.append((item, previous))


def _collect_text_markers(viewer: Any) -> List[Any]:
    return list(getattr(viewer, "text_item_markers", []) or [])


def _collect_rect_markers(viewer: Any) -> List[Any]:
    return list(getattr(viewer, "rect_item_markers", []) or [])


def _collect_text_boxes(viewer: Any) -> List[Any]:
    return list(getattr(viewer, "rectangles", []) or [])


def _collect_polygons(viewer: Any) -> List[Any]:
    return list(getattr(viewer, "polygon_overlays", []) or [])


def find_prohibited_elements(viewer: Optional[Any]) -> Dict[str, int]:
    """Conta gli elementi proibiti attualmente presenti nel viewer.

    Restituisce un dizionario con il numero di elementi per ciascuna
    categoria vietata. Se ``viewer`` e' ``None`` viene restituito un
    dizionario di zeri.
    """
    if viewer is None:
        return {cat: 0 for cat in ALL_PROHIBITED_CATEGORIES}

    return {
        PROHIBITED_MARKERS: (
            len(_collect_text_markers(viewer))
            + len(_collect_rect_markers(viewer))
        ),
        PROHIBITED_TEXT_BOXES: len(_collect_text_boxes(viewer)),
        PROHIBITED_POLYGONS: len(_collect_polygons(viewer)),
    }


def has_prohibited_elements(viewer: Optional[Any]) -> bool:
    """Ritorna ``True`` se nel viewer e' presente almeno un elemento vietato."""
    return any(find_prohibited_elements(viewer).values())


@contextmanager
def prohibited_elements_hidden(viewer: Optional[Any]) -> Iterator[Dict[str, List[Any]]]:
    """Context manager: nasconde tutti gli elementi proibiti durante save/export.

    Tutti gli elementi vietati vengono marcati come ``setVisible(False)``;
    al termine del blocco ``with`` la visibilita' viene ripristinata.

    L'output contiene cosi' ESCLUSIVAMENTE l'immagine originale
    (``viewer.photo``) e le scritte vettoriali (``viewer.text_items``).
    """
    snapshot: Dict[str, List[Any]] = {
        "text_markers": [],
        "rect_markers": [],
        "text_boxes": [],
        "polygons": [],
    }

    try:
        if viewer is None:
            yield snapshot
            return

        for marker in _collect_text_markers(viewer):
            _hide_and_record(marker, snapshot["text_markers"])

        for marker in _collect_rect_markers(viewer):
            _hide_and_record(marker, snapshot["rect_markers"])

        for rect in _collect_text_boxes(viewer):
            _hide_and_record(rect, snapshot["text_boxes"])

        for polygon in _collect_polygons(viewer):
            _hide_and_record(polygon, snapshot["polygons"])

        scene = getattr(viewer, "_scene", None)
        if scene is not None:
            try:
                scene.update()
            except RuntimeError:
                pass

        yield snapshot

    finally:
        # Ripristina la visibilita' PRECEDENTE, non sempre True: un item già
        # nascosto prima del blocco with tornava erroneamente visibile.
        for bucket in ("text_markers", "rect_markers", "text_boxes", "polygons"):
            for entry in snapshot[bucket]:
                if isinstance(entry, tuple):
                    item, was_visible = entry
                    _safe_set_visible(item, was_visible)
                else:
                    _safe_set_visible(entry, True)

        if viewer is not None:
            scene = getattr(viewer, "_scene", None)
            if scene is not None:
                try:
                    scene.update()
                except RuntimeError:
                    pass


def verify_prohibited_count(
    viewer: Optional[Any], operation_name: str
) -> Dict[str, int]:
    """Controllo preventivo: logga il numero di elementi vietati rilevati.

    Da usare PRIMA di ogni operazione di salvataggio / esportazione.
    Restituisce il conteggio per consentire al chiamante di prendere
    decisioni (warning, abort, ecc.).
    """
    counts = find_prohibited_elements(viewer)
    print(
        f"[SAVE_CLEANUP] {operation_name} -> elementi proibiti rilevati: "
        f"markers={counts[PROHIBITED_MARKERS]}, "
        f"text_boxes={counts[PROHIBITED_TEXT_BOXES]}, "
        f"polygons={counts[PROHIBITED_POLYGONS]}"
    )
    return counts
