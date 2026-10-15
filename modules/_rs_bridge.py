"""Bridge verso l'estensione Rust opzionale (komic_core_rs).

Architettura invariata: il codice Python resta la reference.
Se l'estensione manca o fallisce, si usa il fallback Python.
Attivazione: env KOMICTRANSLATE_NO_RS=1 per forzare il Python puro.
"""
import os

try:
    if os.environ.get("KOMICTRANSLATE_NO_RS") == "1":
        raise ImportError("RS disabled by env")
    import komic_core_rs as _rs
    HAS_RS = True
except ImportError:
    _rs = None
    HAS_RS = False


def rs_parse_translation_payload(raw_text: str, expected_count: int):
    """Ritorna (payload, report) dal Rust, o None se non disponibile/fallito."""
    if not HAS_RS:
        return None
    try:
        payload, report = _rs.parse_translation_payload_rs(raw_text or "", int(expected_count))
        return dict(payload), dict(report)
    except Exception:
        return None


def _to_list2d(arr):
    try:
        return [[int(v) for v in row] for row in arr]
    except Exception:
        return None


def rs_simplify_polygon(points, tolerance_px):
    """Simplify esatto (parita verificata). Ritorna lista o None."""
    if not HAS_RS:
        return None
    try:
        pts = _to_list2d(points)
        if pts is None:
            return None
        return _rs.simplify_outer_border_polygon_rs(pts, float(tolerance_px))
    except Exception:
        return None


def rs_is_point_in_ellipse(point, center, axes, angle=0, exponent=2.5, scale=1.1):
    """Test ellisse esatto (parita 2000/2000). Ritorna bool o None."""
    if not HAS_RS:
        return None
    try:
        return bool(_rs.is_point_in_ellipse_rs(
            [float(point[0]), float(point[1])],
            [float(center[0]), float(center[1])],
            [float(axes[0]), float(axes[1])],
            float(angle), float(exponent), float(scale),
        ))
    except Exception:
        return None


def rs_span_at_y(polygon, y_value):
    """Span orizzontale esatto (parita 51/51). Ritorna (l, r) o None."""
    if not HAS_RS:
        return None
    try:
        pts = [[float(v) for v in row] for row in polygon]
        r = _rs.span_at_y_rs(pts, float(y_value))
        return None if r is None else (float(r[0]), float(r[1]))
    except Exception:
        return None


def rs_hyphen_wrap(text, width, **kwargs):
    """Wrap testo (parita 600/600 su break_on_hyphens=False). Ritorna lista o None.

    Per break_on_hyphens=True il Rust e' best-effort: in quel caso resta
    il Python (i chiamanti render usano sempre False).
    """
    if not HAS_RS:
        return None
    if kwargs.get("break_on_hyphens", True):
        return None
    try:
        return list(_rs.hyphen_wrap_rs(
            text,
            int(width),
            initial_indent=kwargs.get("initial_indent", ""),
            subsequent_indent=kwargs.get("subsequent_indent", ""),
            expand_tabs=kwargs.get("expand_tabs", True),
            replace_whitespace=kwargs.get("replace_whitespace", True),
            fix_sentence_endings=kwargs.get("fix_sentence_endings", False),
            break_long_words=kwargs.get("break_long_words", True),
            drop_whitespace=kwargs.get("drop_whitespace", True),
            break_on_hyphens=False,
            hyphenate_broken_words=kwargs.get("hyphenate_broken_words", True),
            tabsize=int(kwargs.get("tabsize", 8)),
            max_lines=kwargs.get("max_lines", None),
            placeholder=kwargs.get("placeholder", " [...]"),
        ))
    except Exception:
        return None


def rs_overlap_ratio(bbox, polygon):
    """Overlap scanline (~0.05 max diff vs cv2). Ritorna float o None."""
    if not HAS_RS:
        return None
    try:
        b = [int(v) for v in bbox]
        pts = _to_list2d(polygon)
        if pts is None:
            return None
        return float(_rs.bbox_polygon_overlap_ratio_rs(b, pts))
    except Exception:
        return None


def _to_list1d_i64(box):
    try:
        return [int(v) for v in box]
    except Exception:
        return None


def rs_calculate_iou(rect1, rect2):
    """IoU esatta. Ritorna float o None."""
    if not HAS_RS:
        return None
    try:
        a = _to_list1d_i64(rect1)
        b = _to_list1d_i64(rect2)
        if a is None or b is None:
            return None
        return float(_rs.calculate_iou_rs(a, b))
    except Exception:
        return None


def rs_do_rectangles_overlap(rect1, rect2, iou_threshold=0.2):
    """Overlap booleano esatto. Ritorna bool o None."""
    if not HAS_RS:
        return None
    try:
        a = _to_list1d_i64(rect1)
        b = _to_list1d_i64(rect2)
        if a is None or b is None:
            return None
        return bool(_rs.do_rectangles_overlap_rs(a, b, float(iou_threshold)))
    except Exception:
        return None


def rs_does_rectangle_fit(bigger_rect, smaller_rect):
    """Contenimento esatto. Ritorna bool o None."""
    if not HAS_RS:
        return None
    try:
        a = _to_list1d_i64(bigger_rect)
        b = _to_list1d_i64(smaller_rect)
        if a is None or b is None:
            return None
        return bool(_rs.does_rectangle_fit_rs(a, b))
    except Exception:
        return None


def rs_is_mostly_contained(outer_box, inner_box, threshold):
    """Contenimento proporzionale esatto. Ritorna bool o None."""
    if not HAS_RS:
        return None
    try:
        o = _to_list1d_i64(outer_box)
        i = _to_list1d_i64(inner_box)
        if o is None or i is None:
            return None
        return bool(_rs.is_mostly_contained_rs(o, i, float(threshold)))
    except Exception:
        return None


_MISS = object()
"""Sentinella: RS non disponibile o fallito (None e' invece un risultato valido)."""


def rs_match_bubble_index(txt_box, bubble_boxes):
    """Indice bubble esatto (parita 300/300). Ritorna int/None, o _MISS se RS manca/fallisce."""
    if not HAS_RS:
        return _MISS
    try:
        import numpy as np
        t = _to_list1d_i64(txt_box)
        if t is None:
            return _MISS
        if bubble_boxes is None or len(bubble_boxes) == 0:
            return None
        bub = [[int(v) for v in row] for row in np.asarray(bubble_boxes)]
        return _rs.match_bubble_index_rs(t, bub)
    except Exception:
        return _MISS


def rs_merge_bounding_boxes(seg_boxes, seg_idx, detect_boxes, detect_idx):
    """Merge esatto (parita 60/60). Ritorna lista di (box, idx) o None."""
    if not HAS_RS:
        return None
    try:
        import numpy as np

        def conv(boxes):
            if boxes is None or len(boxes) == 0:
                return []
            return [[int(v) for v in row] for row in np.asarray(boxes).tolist()]

        out = _rs.merge_bounding_boxes_rs(conv(seg_boxes), list(seg_idx or []),
                                          conv(detect_boxes), list(detect_idx or []))
        return [([int(v) for v in box], idx) for box, idx in out]
    except Exception:
        return None


def rs_edge_support_ratio(dist, poly_frame):
    """Walk perimetrale esatto (parita bit-exact su fuzz). Ritorna float o None.

    dist: matrice distanceTransform (np.ndarray float32); poly_frame: poligono
    in coordinate frame (np.ndarray Nx2).
    """
    if not HAS_RS:
        return None
    try:
        import numpy as np
        d = np.asarray(dist, dtype=np.float32)
        if d.ndim != 2 or d.size == 0:
            return None
        h, w = int(d.shape[0]), int(d.shape[1])
        p = np.asarray(poly_frame, dtype=np.float64).reshape(-1, 2)
        if len(p) < 3:
            return 0.0
        return float(_rs.edge_support_ratio_rs(
            d.ravel().tolist(), w, h,
            [[float(v) for v in row] for row in p.tolist()]))
    except Exception:
        return None
