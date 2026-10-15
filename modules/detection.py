from __future__ import annotations
from .utils.polygon_region import (
    extract_polygon_from_mask,
    filter_bboxes_by_polygon,
    normalize_polygon_points,
    polygon_to_bbox,
)
from .utils.textblock import TextBlock, adjust_text_line_coordinates
import numpy as np
import cv2


class TextBlockDetector:
    def __init__(self, bubble_model_path: str, text_seg_model_path: str, text_detect_model_path: str, device: str):
        from ultralytics import YOLO
        self.bubble_detection = YOLO(bubble_model_path)
        self.text_segmentation = YOLO(text_seg_model_path)
        self.text_detection = YOLO(text_detect_model_path)
        self.device = device

    def detect(self, img):
        self.image = img

        h, w, _ = img.shape
        size = (h, w) if h >= w * 5 else 1024
        det_size = (h, w) if h >= w * 5 else 640

        # Store results to prevent memory leaks from YOLO internals
        bble_detec_result = self.bubble_detection(img, device=self.device, imgsz=size, conf=0.1, verbose=False)[0]
        txt_seg_result = self.text_segmentation(img, device=self.device, imgsz=size, conf=0.1, verbose=False)[0]
        txt_detect_result = self.text_detection(img, device=self.device, imgsz=det_size, conf=0.2, verbose=False)[0]

        combined = self.combine_results(bble_detec_result, txt_seg_result, txt_detect_result, self.image)

        # Explicitly delete result objects to free memory after processing
        del bble_detec_result, txt_seg_result, txt_detect_result

        blk_list = [
            TextBlock(
                txt_bbox,
                bble_bbox,
                txt_class,
                inp_bboxes,
                text_segm_points=bble_polygon,
            )
            for txt_bbox, bble_bbox, bble_polygon, inp_bboxes, txt_class in combined
        ]

        for blk in blk_list:
            polygon = getattr(blk, "polygon_points", None)
            blk._original_polygon_points = None if polygon is None else np.array(polygon, copy=True)
            blk.use_polygon_inpaint = True
        
        return blk_list
    
    def combine_results(self, bubble_detec_results: YOLO, text_seg_results: YOLO, text_detect_results: YOLO, image: np.ndarray):
        bubble_bounding_boxes = np.array(bubble_detec_results.boxes.xyxy.cpu(), dtype="int")

        seg_text_bounding_boxes = np.array(text_seg_results.boxes.xyxy.cpu(), dtype="int")
        detect_text_bounding_boxes = np.array(text_detect_results.boxes.xyxy.cpu(), dtype="int")

        # Abbina OGNI box (seg e detect) al suo bubble PRIMA di fondere:
        # si fondono solo box dello stesso balloon, mai attraverso due
        # balloon diversi (es. la codina del 9 non deve tirare il box dell'11).
        seg_bubble_idx = [
            _match_bubble_index(box, bubble_bounding_boxes)
            for box in seg_text_bounding_boxes
        ]
        detect_bubble_idx = [
            _match_bubble_index(box, bubble_bounding_boxes)
            for box in detect_text_bounding_boxes
        ]

        merged_pairs = merge_bounding_boxes(
            seg_text_bounding_boxes, seg_bubble_idx,
            detect_text_bounding_boxes, detect_bubble_idx,
        )
        # Stesso filtro di prima (box degeneri), preservando l'indice bubble.
        merged_pairs = [
            (box, bidx) for box, bidx in merged_pairs
            if not _is_degenerate_box(box)
        ]

        raw_results = []
        for txt_box, bidx in merged_pairs:
            matched_bubble = bubble_bounding_boxes[bidx] if bidx is not None else None

            # Semi su piu' bande verticali del testo: le righe a tutta
            # larghezza sigillano il balloon in bande, un seme solo ne
            # riempie una (casi 1, 2, 11, 13).
            tx1, ty1, tx2, ty2 = (int(txt_box[0]), int(txt_box[1]),
                                  int(txt_box[2]), int(txt_box[3]))
            tcx = (tx1 + tx2) / 2
            seeds = [(tcx, ty1 + (ty2 - ty1) * f)
                     for f in (0.12, 0.32, 0.5, 0.68, 0.88)]
            bubble_polygon = extract_bubble_polygon(
                image, matched_bubble, seeds=seeds)
            # Il text box resta quello di YOLO: il balloon NON deve mai
            # riscriverlo, altrimenti un abbinamento sbagliato trascina il
            # rettangolo fuori dal testo. Il balloon guida solo l'inpaint.
            if matched_bubble is not None:
                text_class = 'text_bubble' if does_rectangle_fit(matched_bubble, txt_box) else 'text_free'
            else:
                text_class = 'text_free'
            adjusted_bboxes = get_inpaint_bboxes(
                txt_box,
                image,
                matched_bubble,
                bubble_polygon,
            )
            raw_results.append((txt_box, matched_bubble, bubble_polygon, adjusted_bboxes, text_class))

        return raw_results
    
def get_inpaint_bboxes(text_bbox, image, bubble_bbox=None, bubble_polygon=None):
    # Expansion parameters: 0% width, 10% height
    x1, y1, x2, y2 = adjust_text_line_coordinates(text_bbox, 0, 10, image)

    # Convert coordinates to integers for array slicing
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

    if x1 >= x2 or y1 >= y2:
        return []

    # Area consentita = unione del box testo con il bubble rilevato.
    # Prima il crop veniva clippato AL bubble: se il bubble era
    # sotto-rilevato, un allargamento manuale del rettangolo veniva
    # annullato qui e le righe perse non venivano mai riscoperte.
    if bubble_bbox is not None:
        bx1, by1, bx2, by2 = [int(v) for v in bubble_bbox]
        ax1, ay1 = min(x1, bx1), min(y1, by1)
        ax2, ay2 = max(x2, bx2), max(y2, by2)
    else:
        ax1, ay1, ax2, ay2 = x1, y1, x2, y2

    # Crop the image to the text bounding box (intero, non clippato al bubble)
    crop = image[y1:y2, x1:x2]

    # Detect content in the cropped bubble
    content_bboxes = detect_content_in_bbox(crop)

    # Adjusting coordinates to the full image
    adjusted_bboxes = []
    for bbox in content_bboxes:
        lx1, ly1, lx2, ly2 = bbox
        adjusted_bbox = (x1 + lx1, y1 + ly1, x1 + lx2, y1 + ly2)

        if bubble_polygon is not None or bubble_bbox is not None:
            clx1, cly1, clx2, cly2 = adjusted_bbox
            clx1, cly1 = max(clx1, ax1), max(cly1, ay1)
            clx2, cly2 = min(clx2, ax2), min(cly2, ay2)
            if clx1 < clx2 and cly1 < cly2:
                adjusted_bboxes.append((clx1, cly1, clx2, cly2))
        else:
            adjusted_bboxes.append(adjusted_bbox)

    if bubble_polygon is not None:
        # Se il box testo esce dal vecchio poligono (allargamento manuale
        # oltre un bubble sotto-rilevato), il filtro poligonale scarterebbe
        # proprio le righe che l'utente vuole pulire: lo si applica solo
        # quando il box resta dentro il bubble.
        poly_bbox = polygon_to_bbox(bubble_polygon)
        if poly_bbox is not None and does_rectangle_fit(tuple(int(v) for v in poly_bbox), (x1, y1, x2, y2)):
            filtered = filter_bboxes_by_polygon(adjusted_bboxes, bubble_polygon, min_overlap=0.2)
            return filtered.tolist() if isinstance(filtered, np.ndarray) else filtered

    return adjusted_bboxes


def _photo_flood_regions(gray, seed, tone, lo=14, up=14):
    """Regioni fotometriche attorno al seme, range ancorato al tono-carta.

    Il range e' [tone-lo, tone+up] per TUTTI i candidati (ancorato, non al
    valore del singolo pixel): un candidato su un tratto scuro inonda solo
    lo stroke (micro-regione scartata) invece di avvelenare l'unione con
    toni dell'artwork. Nessuna barriera binaria: ci si ferma dove la
    luminosita' cambia (inchiostro, texture, altri colori).
    """
    h, w = gray.shape[:2]
    sx, sy = int(seed[0]), int(seed[1])
    if not (0 <= sx < w and 0 <= sy < h):
        return []
    step = max(2, min(h, w) // 40)
    candidates = [(sx, sy)]
    for radius in range(step, max(h, w) // 3 + 1, step):
        for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius),
                       (radius, radius), (-radius, -radius),
                       (radius, -radius), (-radius, radius)):
            nx, ny = sx + dx, sy + dy
            if 0 <= nx < w and 0 <= ny < h:
                candidates.append((nx, ny))
        if len(candidates) >= 13:
            break
    regions = []
    covered = np.zeros((h, w), dtype=bool)
    for cx, cy in candidates:
        if covered[cy, cx]:
            continue  # Banda gia' coperta da un flood precedente.
        c = int(gray[cy, cx])
        # Fuori banda-tonale -> solo lo stroke (verra' scartato per area).
        if c < tone - lo or c > tone + up:
            clo, cup = 0, 0
        else:
            clo, cup = c - (tone - lo), (tone + up) - c
        flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        cv2.floodFill(gray, flood_mask, (cx, cy), 255,
                      loDiff=clo, upDiff=cup,
                      flags=4 | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY)
        region = flood_mask[1:-1, 1:-1] != 0
        if np.count_nonzero(region) < 200:
            continue
        regions.append(region)
        covered |= region
    return regions


def _canny_frame(frame):
    """Edge Canny con soglie adattive alla mediana (bordi sottili/chiari)."""
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    med = float(np.median(gray))
    if med < 5 or med > 250:
        lo, hi = 50, 150
    else:
        lo = int(max(10, min(150, 0.66 * med)))
        hi = int(max(50, min(250, 1.33 * med)))
        if hi <= lo:
            lo, hi = 50, 150
    return cv2.Canny(blurred, lo, hi)


def _edge_support_ratio(poly_frame, edges):
    """Frazione del perimetro entro 3px da un edge (muri veri vs cielo)."""
    try:
        pts = np.asarray(poly_frame, dtype=np.float32).reshape(-1, 2)
        if len(pts) < 3:
            return 0.0
        inv = np.zeros_like(edges)
        inv[edges == 0] = 255
        dist = cv2.distanceTransform(inv, cv2.DIST_L2, 3)
        h, w = dist.shape[:2]
        # Fast-path Rust per il walk perimetrale (parita bit-exact su fuzz).
        # distanceTransform resta in cv2; fallback Python invariato.
        try:
            from modules._rs_bridge import rs_edge_support_ratio
            r = rs_edge_support_ratio(dist, pts)
            if r is not None:
                return r
        except Exception:
            pass
        ok, tot = 0, 0
        n = len(pts)
        for i in range(n):
            p0, p1 = pts[i], pts[(i + 1) % n]
            steps = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
            for k in range(steps):
                x = int(round(p0[0] + (p1[0] - p0[0]) * k / steps))
                y = int(round(p0[1] + (p1[1] - p0[1]) * k / steps))
                if 0 <= x < w and 0 <= y < h:
                    tot += 1
                    if dist[y, x] <= 3.0:
                        ok += 1
        return ok / max(1, tot)
    except Exception:
        return 1.0


def _touch_ratio(region, allow_touch):
    """Massimo rapporto di contatto coi bordi proibiti (0..1)."""
    h, w = region.shape[:2]
    worst = 0.0
    if not allow_touch[0]:
        worst = max(worst, float(np.count_nonzero(region[0, :])) / max(1, w))
    if not allow_touch[1]:
        worst = max(worst, float(np.count_nonzero(region[-1, :])) / max(1, w))
    if not allow_touch[2]:
        worst = max(worst, float(np.count_nonzero(region[:, 0])) / max(1, h))
    if not allow_touch[3]:
        worst = max(worst, float(np.count_nonzero(region[:, -1])) / max(1, h))
    return worst


def _polygon_from_union(umask, ox, oy):
    """Poligono da maschera multi-componente: contorno dominante se basta,
    altrimenti hull di tutti i pixel (le bande di testo non restano fuori).
    Preserva le concavita' quando possibile (code, forme irregolari)."""
    from .utils.polygon_region import simplify_outer_border_polygon
    contours, _ = cv2.findContours(umask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= 50]
    if not contours:
        return None
    areas = [float(cv2.contourArea(c)) for c in contours]
    if max(areas) >= 0.7 * sum(areas):
        base = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(base, True)
        eps = max(1.0, peri * (0.005 if peri < 400 else 0.01))
        approx = cv2.approxPolyDP(base, eps, True).reshape(-1, 2)
    else:
        pts = np.vstack([c.reshape(-1, 2) for c in contours]).astype(np.int32)
        hull = cv2.convexHull(pts)
        peri = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, max(1.0, peri * 0.01), True).reshape(-1, 2)
    approx = simplify_outer_border_polygon(approx)
    if approx is None or len(approx) < 3:
        return None
    approx = np.asarray(approx, dtype=np.int32)
    approx[:, 0] += int(ox)
    approx[:, 1] += int(oy)
    return normalize_polygon_points(approx)


def extract_bubble_polygon(image, bubble_bbox, seed=None, seeds=None,
                          pad_ratio=0.25, tone=None):
    if bubble_bbox is None:
        return None
    bx1, by1, bx2, by2 = [int(v) for v in bubble_bbox]
    if bx1 >= bx2 or by1 >= by2:
        return None
    h, w = image.shape[:2]
    if seeds is None:
        if seed is None:
            seed = ((bx1 + bx2) / 2, (by1 + by2) / 2)
        seeds = [seed]
    bbox_area = float(max(1, (bx2 - bx1) * (by2 - by1)))
    # Semi su piu' bande verticali se il chiamante passa il solo centro:
    # le righe a tutta larghezza sigillano il balloon in bande.
    if len(seeds) == 1 and seed is not None:
        (scx, scy) = seeds[0]
        seeds = [(scx, scy + d) for d in (0, -12, 12, -24, 24)]
    gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if tone is None:
        # Tono-carta vicino al testo (p90: i tratti scuri sono minoranza).
        mcx, mcy = seeds[len(seeds) // 2]
        x0, x1 = max(0, int(mcx) - 15), min(w, int(mcx) + 15)
        y0, y1 = max(0, int(mcy) - 10), min(h, int(mcy) + 10)
        try:
            tone = float(np.percentile(gray_full[y0:y1, x0:x1], 90)) \
                if x1 > x0 and y1 > y0 else 242.0
        except Exception:
            tone = 242.0
    tone = min(255.0, max(100.0, tone))
    for ratio in (pad_ratio, 0.6, 1.2):
        pad = max(4, int(max(bx2 - bx1, by2 - by1) * ratio))
        px1, py1 = max(0, bx1 - pad), max(0, by1 - pad)
        px2, py2 = min(w, bx2 + pad), min(h, by2 + pad)
        fw, fh = px2 - px1, py2 - py1
        if fw <= 0 or fh <= 0:
            continue
        gray = gray_full[py1:py2, px1:px2]
        bubble_frame = image[py1:py2, px1:px2]
        allow_touch = (py1 == 0, py2 >= h, px1 == 0, px2 >= w)
        max_region = 6.0 * bbox_area
        union = None
        for s in seeds:
            for region in _photo_flood_regions(
                    gray, (s[0] - px1, s[1] - py1), tone):
                area = float(np.count_nonzero(region))
                if area > max_region:
                    continue  # Stanza/vicino inglobato.
                if _touch_ratio(region, allow_touch) > 0.25:
                    continue  # Colato fuori dai muri.
                union = region if union is None else (union | region)
        if union is None or not np.any(union):
            continue
        uarea = float(np.count_nonzero(union))
        if uarea < 0.25 * bbox_area or uarea > max_region:
            continue
        umask = np.zeros(union.shape, dtype=np.uint8)
        umask[union] = 255
        # Il testo deve stare dentro il poligono (tolleranza 3px).
        poly = _polygon_from_union(umask, px1, py1)
        if poly is None:
            continue
        try:
            contour = np.asarray(poly, dtype=np.float32).reshape(-1, 1, 2)
            inside = all(
                cv2.pointPolygonTest(contour, (float(s[0]), float(s[1])), False) >= -3.0
                for s in seeds
            )
        except Exception:
            inside = True
        if not inside:
            continue
        # Supporto-edge: il perimetro deve appoggiare ai muri (>=40% entro
        # 3px da un edge). Blob su cielo/grondaia liscia vengono scartati.
        edges = _canny_frame(bubble_frame)
        poly_frame = np.asarray(poly, dtype=np.float32).copy()
        poly_frame[:, 0] -= px1
        poly_frame[:, 1] -= py1
        if _edge_support_ratio(poly_frame, edges) < 0.40:
            continue
        return poly
    # Fallback garantito: mai un blob sull'artwork, solo la bbox.
    return normalize_polygon_points(np.array(
        [[bx1, by1], [bx2, by1], [bx2, by2], [bx1, by2]], dtype=np.int32))

def calculate_iou(rect1, rect2) -> float:
    """
    Calculate the Intersection over Union (IoU) of two rectangles.
    
    Parameters:
    rect1, rect2: The coordinates of the rectangles in the format
    [x1, y1, x2, y2], where (x1, y1) is the top-left coordinate and (x2, y2) is the bottom-right coordinate.
    
    Returns:
    iou: the Intersection over Union (IoU) metric as a float.
    """
    # Fast-path Rust (parita 5000/5000). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_calculate_iou
        r = rs_calculate_iou(rect1, rect2)
        if r is not None:
            return r
    except Exception:
        pass
    x1 = max(rect1[0], rect2[0])
    y1 = max(rect1[1], rect2[1])
    x2 = min(rect1[2], rect2[2])
    y2 = min(rect1[3], rect2[3])
    
    intersection_area = max(0, x2 - x1) * max(0, y2 - y1)
    
    rect1_area = (rect1[2] - rect1[0]) * (rect1[3] - rect1[1])
    rect2_area = (rect2[2] - rect2[0]) * (rect2[3] - rect2[1])
    
    union_area = rect1_area + rect2_area - intersection_area
    
    iou = intersection_area / union_area if union_area != 0 else 0
    
    return iou

def do_rectangles_overlap(rect1, rect2, iou_threshold: float = 0.2) -> bool:
    """
    Determines whether two rectangles refer to the same object based on an IoU threshold.
    
    Parameters:
    rect1, rect2: as described in the calculate_iou function.
    iou_threshold: float value representing the threshold above which the rectangles are
    considered to be referring to the same object.
    
    Returns:
    overlap: a boolean indicating whether the two rectangles refer to the same object.
    """
    # Fast-path Rust (parita verificata). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_do_rectangles_overlap
        r = rs_do_rectangles_overlap(rect1, rect2, iou_threshold)
        if r is not None:
            return r
    except Exception:
        pass
    iou = calculate_iou(rect1, rect2)
    overlap = iou >= iou_threshold
    return overlap

def does_rectangle_fit(bigger_rect, smaller_rect):
    # Fast-path Rust (parita 5000/5000). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_does_rectangle_fit
        r = rs_does_rectangle_fit(bigger_rect, smaller_rect)
        if r is not None:
            return r
    except Exception:
        pass
    x1, y1, x2, y2 = bigger_rect
    px1, py1, px2, py2 = smaller_rect
    
    # Ensure the coordinates are properly ordered
    # first rectangle
    left1, top1, right1, bottom1 = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    # second rectangle
    left2, top2, right2, bottom2 = min(px1, px2), min(py1, py2), max(px1, px2), max(py1, py2)
    
    # Check if the second rectangle fits within the first
    fits_horizontally = left1 <= left2 and right1 >= right2
    fits_vertically = top1 <= top2 and bottom1 >= bottom2
    
    return fits_horizontally and fits_vertically

def is_mostly_contained(outer_box, inner_box, threshold):
    """
    Check if inner_box is mostly contained within outer_box.
    
    :param outer_box: The larger bounding box (x1, y1, x2, y2)
    :param inner_box: The smaller bounding box (x1, y1, x2, y2)
    :param threshold: The proportion of inner_box that must be inside outer_box
    :return: Boolean indicating if inner_box is mostly contained in outer_box
    """
    # Fast-path Rust (parita 5000/5000). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_is_mostly_contained
        r = rs_is_mostly_contained(outer_box, inner_box, threshold)
        if r is not None:
            return r
    except Exception:
        pass
    ix1, iy1, ix2, iy2 = inner_box
    ox1, oy1, ox2, oy2 = outer_box
    
    # Calculate the area of the inner and outer boxes
    inner_area = (ix2 - ix1) * (iy2 - iy1)
    outer_area = (ox2 - ox1) * (oy2 - oy1)
    
    # Return False if the outer box is smaller than the inner box
    if outer_area < inner_area or inner_area == 0:
        return False
    
    # Calculate the area of intersection
    intersection_area = max(0, min(ix2, ox2) - max(ix1, ox1)) * max(0, min(iy2, oy2) - max(iy1, oy1))
    
    # Check if the proportion of intersection to inner area is greater than the threshold
    return intersection_area / inner_area >= threshold

def _match_bubble_index(txt_box, bubble_boxes):
    """Restituisce l'indice del bubble a cui appartiene il box, o None.

    Best-fit (prima era primo-fit/ultimo-overlap): tra i contenimenti vince
    il bubble piu' stretto, tra le sovrapposizioni la IoU massima (>= 0.2).
    """
    # Fast-path Rust (parita 300/300). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_match_bubble_index, _MISS
        r = rs_match_bubble_index(txt_box, bubble_boxes)
        if r is not _MISS:
            return r
    except Exception:
        pass
    if bubble_boxes is None or len(bubble_boxes) == 0:
        return None
    best_fit = None
    best_fit_area = None
    for idx, bble_box in enumerate(bubble_boxes):
        if does_rectangle_fit(bble_box, txt_box):
            area = int(bble_box[2] - bble_box[0]) * int(bble_box[3] - bble_box[1])
            if best_fit_area is None or area < best_fit_area:
                best_fit, best_fit_area = idx, area
    if best_fit is not None:
        return best_fit
    best_overlap = None
    best_iou = 0.2
    for idx, bble_box in enumerate(bubble_boxes):
        iou = calculate_iou(bble_box, txt_box)
        if iou >= 0.2 and iou > best_iou:
            best_overlap, best_iou = idx, iou
    return best_overlap


def _bubbles_compatible(a, b):
    """Due box si fondono solo se stesso balloon (o almeno uno senza)."""
    return a is None or b is None or a == b


def _is_degenerate_box(box, width_tolerance=5, height_tolerance=5):
    try:
        return (abs(int(box[0]) - int(box[2])) <= width_tolerance
                or abs(int(box[1]) - int(box[3])) <= height_tolerance)
    except (TypeError, ValueError, IndexError):
        return True


def _snap_box_to_content(txt_box, content_bboxes):
    """Allarga il box visibile a coprire le righe di contenuto trovate."""
    try:
        boxes = list(content_bboxes) if content_bboxes is not None else []
    except TypeError:
        return txt_box
    if not len(boxes):
        return txt_box
    try:
        x1 = min(int(txt_box[0]), min(int(b[0]) for b in boxes))
        y1 = min(int(txt_box[1]), min(int(b[1]) for b in boxes))
        x2 = max(int(txt_box[2]), max(int(b[2]) for b in boxes))
        y2 = max(int(txt_box[3]), max(int(b[3]) for b in boxes))
    except (TypeError, ValueError, IndexError):
        return txt_box
    if x1 >= x2 or y1 >= y2:
        return txt_box
    return np.array([x1, y1, x2, y2], dtype="int")

def merge_boxes(box1, box2):
    """Merge two bounding boxes"""
    return [
        min(box1[0], box2[0]),
        min(box1[1], box2[1]),
        max(box1[2], box2[2]),
        max(box1[3], box2[3])
    ]

def merge_bounding_boxes(seg_boxes, seg_idx, detect_boxes, detect_idx):
    """Fonde i box testo portandosi dietro l'indice bubble.

    Rispetto a prima, due box di balloon DIVERSI non si fondono mai.
    Restituisce una lista di coppie (box, bubble_idx).
    """
    # Fast-path Rust (parita 60/60). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_merge_bounding_boxes
        r = rs_merge_bounding_boxes(seg_boxes, seg_idx, detect_boxes, detect_idx)
        if r is not None:
            return [(np.asarray(b, dtype=int), i) for b, i in r]
    except Exception:
        pass
    merged_pairs = []

    # First step: Merge seg_boxes with detect_boxes
    # When the text has no bubbles, The Segmentatio Model tends to predict large boxes that aim to cover most of the text,
    # but the detection model tends to predict each line as a separate box
    for seg_pos, seg_box in enumerate(seg_boxes):
        running_box = seg_box
        running_idx = seg_idx[seg_pos] if seg_pos < len(seg_idx) else None
        for det_pos, detect_box in enumerate(detect_boxes):
            det_bidx = detect_idx[det_pos] if det_pos < len(detect_idx) else None
            if not _bubbles_compatible(running_idx, det_bidx):
                continue  # Balloon diversi: mai fondere
            if does_rectangle_fit(running_box, detect_box):
                if running_idx is None:
                    running_idx = det_bidx
                continue  # Detect box fits entirely within the running box
            if do_rectangles_overlap(running_box, detect_box, 0.02):
                # Merge running_box with the detect_box and update the running_box
                running_box = merge_boxes(running_box, detect_box)
                if running_idx is None:
                    running_idx = det_bidx

        merged_pairs.append((running_box, running_idx))  # Add the final running box for this seg box

    # Now add any detect boxes that weren't merged
    for det_pos, detect_box in enumerate(detect_boxes):
        det_bidx = detect_idx[det_pos] if det_pos < len(detect_idx) else None
        add_box = True
        for merged_box, merged_idx in merged_pairs:
            if not _bubbles_compatible(det_bidx, merged_idx):
                continue
            if do_rectangles_overlap(detect_box, merged_box, 0.1) or does_rectangle_fit(merged_box, detect_box):
                add_box = False
                break
        if add_box:
            merged_pairs.append((detect_box, det_bidx))

    # Second step: Re-process merged_boxes to handle overlaps that should be merged into a bigger box
    final_pairs = []
    for i, (box, bidx) in enumerate(merged_pairs):
        running_box = box
        running_idx = bidx
        for j, (other_box, other_idx) in enumerate(merged_pairs):
            if i == j:
                continue  # Skip comparing the box with itself
            if not _bubbles_compatible(running_idx, other_idx):
                continue  # Balloon diversi: mai fondere
            if do_rectangles_overlap(running_box, other_box, 0.1) and not does_rectangle_fit(running_box, other_box):
                # Re-merge running_box with the overlapping other_box
                running_box = merge_boxes(running_box, other_box)
                if running_idx is None:
                    running_idx = other_idx

        final_pairs.append((running_box, running_idx))  # Add the final running box after second pass

    # Remove duplicates and high-overlap boxes
    unique_pairs = []
    seen_boxes = []
    for box, bidx in final_pairs:
        duplicate = False
        for seen_box in seen_boxes:
            if (np.array_equal(box, seen_box) or do_rectangles_overlap(box, seen_box, 0.6)):
                duplicate = True
                break
        if not duplicate:
            unique_pairs.append((box, bidx))
            seen_boxes.append(box)  # Track the box that we've added to the final list

    return unique_pairs


def detect_content_in_bbox(image):
    if image is None or image.size == 0:
        return []
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Adaptive Thresholding to handle varying illumination
    binary_white_text = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    binary_black_text = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )
    
    # Perform connected component labeling for both cases
    num_labels_white, labels_white, stats_white, centroids_white = cv2.connectedComponentsWithStats(binary_white_text, connectivity=8)
    num_labels_black, labels_black, stats_black, centroids_black = cv2.connectedComponentsWithStats(binary_black_text, connectivity=8)
    
    # Filter out small components (likely to be noise)
    min_area = 10 
    content_bboxes = []
    
    height, width = image.shape[:2]
    
    # Process white text on black background
    for i in range(1, num_labels_white):  # Start from 1 to skip the background
        area = stats_white[i, cv2.CC_STAT_AREA]
        if area > min_area:
            x1 = stats_white[i, cv2.CC_STAT_LEFT]
            y1 = stats_white[i, cv2.CC_STAT_TOP]
            w = stats_white[i, cv2.CC_STAT_WIDTH]
            h = stats_white[i, cv2.CC_STAT_HEIGHT]
            x2 = x1 + w
            y2 = y1 + h
            
            # Check if the bounding box touches the edges of the image
            if x1 > 0 and y1 > 0 and x1 + w < width and y1 + h < height:
                content_bboxes.append((x1, y1, x2, y2))
    
    # Process black text on white background
    for i in range(1, num_labels_black):  # Start from 1 to skip the background
        area = stats_black[i, cv2.CC_STAT_AREA]
        if area > min_area:
            x1 = stats_black[i, cv2.CC_STAT_LEFT]
            y1 = stats_black[i, cv2.CC_STAT_TOP]
            w = stats_black[i, cv2.CC_STAT_WIDTH]
            h = stats_black[i, cv2.CC_STAT_HEIGHT]
            x2 = x1 + w
            y2 = y1 + h
            
            # Check if the bounding box touches the edges of the image
            if x1 > 0 and y1 > 0 and x1 + w < width and y1 + h < height:
                content_bboxes.append((x1, y1, x2, y2))
    
    return content_bboxes

def filter_bounding_boxes(bboxes, width_tolerance=5, height_tolerance=5):
    def is_close(value1, value2, tolerance):
        return abs(value1 - value2) <= tolerance

    return [
        bbox for bbox in bboxes
        if not (is_close(bbox[0], bbox[2], width_tolerance) or is_close(bbox[1], bbox[3], height_tolerance))
    ]

# From https://github.com/TareHimself/manga-translator/blob/master/translator/utils.py

def adjust_contrast_brightness(img: np.ndarray, contrast: float = 1.0, brightness: int = 0):
    """
    Adjusts contrast and brightness of an uint8 image.
    contrast:   (0.0,  inf) with 1.0 leaving the contrast as is
    brightness: [-255, 255] with 0 leaving the brightness as is
    """
    brightness += int(round(255 * (1 - contrast) / 2))
    return cv2.addWeighted(img, contrast, img, 0, brightness)

def ensure_gray(img: np.ndarray):
    if len(img.shape) > 2:
        return cv2.cvtColor(img.copy(), cv2.COLOR_BGR2GRAY)
    return img.copy()

def make_bubble_mask(frame: np.ndarray):
    image = frame.copy()
    # Apply a Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(image, (5, 5), 0)

    # Soglie Canny adattive sulla mediana del crop: quelle fisse (50, 150)
    # perdevano i bordi sottili/chiari dei balloon di piccolo taglio.
    gray_med = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    med = float(np.median(gray_med))
    if med < 5 or med > 250:
        lo, hi = 50, 150
    else:
        lo = int(max(10, min(150, 0.66 * med)))
        hi = int(max(50, min(250, 1.33 * med)))
        if hi <= lo:
            lo, hi = 50, 150

    # Use the Canny edge detection algorithm
    edges = cv2.Canny(blurred, lo, hi)

    # Find contours in the image
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    # Create a black image with the same size as the original
    stage_1 = cv2.drawContours(np.zeros_like(image), contours, -1, (255, 255, 255), thickness=2)
    stage_1 = cv2.bitwise_not(stage_1)
    stage_1 = cv2.cvtColor(stage_1, cv2.COLOR_BGR2GRAY)
    _, binary_image = cv2.threshold(stage_1, 200, 255, cv2.THRESH_BINARY)

    # Find connected components in the binary image
    num_labels, labels = cv2.connectedComponents(binary_image)
    largest_island_label = np.argmax(np.bincount(labels.flat)[1:]) + 1
    mask = np.zeros_like(image)
    mask[labels == largest_island_label] = 255

    _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)

    # Apply morphological operations to remove black spots
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    return adjust_contrast_brightness(mask, 100)

def bubble_contour(frame_mask: np.ndarray):
    gray = ensure_gray(frame_mask)
    # Threshold the image
    ret, thresh = cv2.threshold(gray, 200, 255, 0)
    
    # Find contours
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    largest_contour = max(contours, key=cv2.contourArea) 
    return largest_contour

def bubble_interior_bounds(frame_mask: np.ndarray):
    import largestinteriorrectangle as lir
    bble_contour = bubble_contour(frame_mask)

    polygon = np.array([bble_contour[:, 0, :]])
    rect = lir.lir(polygon)

    x1, y1 = lir.pt1(rect)
    x2, y2 = lir.pt2(rect)

    return x1, y1, x2, y2

