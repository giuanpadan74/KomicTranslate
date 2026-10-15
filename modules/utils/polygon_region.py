import cv2
import numpy as np

OUTER_BORDER_CLOSE_KERNEL = (7, 7)
OUTER_BORDER_POINT_TOLERANCE_PX = 2.0
OUTER_BORDER_COLLINEAR_TOLERANCE_PX = 1.5


def normalize_polygon_points(points):
    if points is None:
        return None
    polygon = np.asarray(points, dtype=np.int32)
    if polygon.size == 0:
        return None
    if polygon.ndim == 3 and polygon.shape[1] == 1:
        polygon = polygon.squeeze(1)
    if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3:
        return None
    return polygon


def polygon_to_bbox(points):
    polygon = normalize_polygon_points(points)
    if polygon is None:
        return None
    min_x = int(np.min(polygon[:, 0]))
    min_y = int(np.min(polygon[:, 1]))
    max_x = int(np.max(polygon[:, 0]))
    max_y = int(np.max(polygon[:, 1]))
    return np.array([min_x, min_y, max_x, max_y], dtype=np.int32)


def polygon_to_mask(image_shape, points):
    polygon = normalize_polygon_points(points)
    if polygon is None:
        return None
    height, width = image_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon.astype(np.int32)], 255)
    return mask


def _keep_largest_white_component(mask):
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        return mask
    largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    largest = np.zeros_like(mask)
    largest[labels == largest_label] = 255
    return largest


def _fill_white_mask_holes(mask):
    filled = mask.copy()
    flood_mask = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(filled, flood_mask, (0, 0), 255)
    holes = cv2.bitwise_not(filled)
    return cv2.bitwise_or(mask, holes)


def prepare_outer_polygon_mask(mask):
    if mask is None or np.size(mask) == 0:
        return None
    if len(mask.shape) == 3:
        gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    else:
        gray = mask.copy()
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    largest = _keep_largest_white_component(thresh)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, OUTER_BORDER_CLOSE_KERNEL)
    closed = cv2.morphologyEx(largest, cv2.MORPH_CLOSE, kernel, iterations=1)
    filled = _fill_white_mask_holes(closed)
    return _keep_largest_white_component(filled)


def filter_polygon_points_to_outer_contour(
    points,
    outer_contour,
    max_inside_distance=OUTER_BORDER_POINT_TOLERANCE_PX,
):
    polygon = normalize_polygon_points(points)
    if polygon is None or outer_contour is None or len(outer_contour) < 3:
        return polygon
    filtered = []
    for point in polygon:
        distance = cv2.pointPolygonTest(
            outer_contour,
            (float(point[0]), float(point[1])),
            True,
        )
        if distance <= float(max_inside_distance):
            filtered.append(point)
    if len(filtered) < 3:
        return polygon
    return normalize_polygon_points(np.array(filtered, dtype=np.int32))


def simplify_outer_border_polygon(
    points,
    tolerance_px=OUTER_BORDER_COLLINEAR_TOLERANCE_PX,
):
    # Fast-path Rust (parita esatta verificata). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_simplify_polygon

        rs_result = rs_simplify_polygon(points, tolerance_px)
        if rs_result is not None:
            return normalize_polygon_points(np.array(rs_result, dtype=np.int32))
    except Exception:
        pass
    polygon = normalize_polygon_points(points)
    if polygon is None or len(polygon) <= 3:
        return polygon
    simplified = polygon.copy()
    changed = True
    while changed and len(simplified) > 3:
        changed = False
        next_points = []
        count = len(simplified)
        for index in range(count):
            prev_point = simplified[index - 1].astype(np.float32)
            curr_point = simplified[index].astype(np.float32)
            next_point = simplified[(index + 1) % count].astype(np.float32)
            line = next_point - prev_point
            norm = float(np.linalg.norm(line))
            if norm == 0:
                changed = True
                continue
            rel_point = curr_point - prev_point
            area_twice = (line[0] * rel_point[1]) - (line[1] * rel_point[0])
            distance = abs(area_twice) / norm
            if distance <= float(tolerance_px):
                changed = True
                continue
            next_points.append(simplified[index])
        if len(next_points) < 3:
            break
        simplified = np.array(next_points, dtype=np.int32)
    return normalize_polygon_points(simplified)


def extract_polygon_from_mask(mask, offset_x=0, offset_y=0, epsilon_ratio=None):
    if mask is None or np.size(mask) == 0:
        return None
    prepared_mask = prepare_outer_polygon_mask(mask)
    if prepared_mask is None:
        return None
    contours, _ = cv2.findContours(
        prepared_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) <= 0:
        return None
    # Scarta i frammenti: se il contorno copre solo una scheggia della zona
    # bianca (bordi frammentati), meglio nessun poligono che uno sbagliato
    # (i chiamanti ripiegano sulla bbox).
    white_area = float(np.count_nonzero(prepared_mask))
    if white_area > 0 and cv2.contourArea(contour) < 0.15 * white_area:
        return None
    outer_contour = cv2.convexHull(contour)
    peri = cv2.arcLength(outer_contour, True)
    if epsilon_ratio is None:
        # Balloon piccoli: l'1% leviga troppo i vertici utili.
        epsilon_ratio = 0.005 if peri < 400 else 0.01
    epsilon = max(1.0, peri * epsilon_ratio)
    polygon = cv2.approxPolyDP(outer_contour, epsilon, True).reshape(-1, 2)
    polygon = filter_polygon_points_to_outer_contour(polygon, outer_contour)
    polygon = simplify_outer_border_polygon(polygon)
    if len(polygon) < 3:
        return None
    polygon = polygon.astype(np.int32)
    polygon[:, 0] += int(offset_x)
    polygon[:, 1] += int(offset_y)
    return normalize_polygon_points(polygon)


def bbox_polygon_overlap_ratio(bbox, points):
    polygon = normalize_polygon_points(points)
    if polygon is None:
        return 0.0
    x1, y1, x2, y2 = [int(v) for v in bbox]
    if x1 >= x2 or y1 >= y2:
        return 0.0
    poly_bbox = polygon_to_bbox(polygon)
    lx1 = min(x1, int(poly_bbox[0]))
    ly1 = min(y1, int(poly_bbox[1]))
    lx2 = max(x2, int(poly_bbox[2]))
    ly2 = max(y2, int(poly_bbox[3]))
    width = max(1, lx2 - lx1 + 1)
    height = max(1, ly2 - ly1 + 1)
    poly_mask = np.zeros((height, width), dtype=np.uint8)
    rect_mask = np.zeros((height, width), dtype=np.uint8)
    shifted = polygon.copy()
    shifted[:, 0] -= lx1
    shifted[:, 1] -= ly1
    cv2.fillPoly(poly_mask, [shifted.astype(np.int32)], 255)
    cv2.rectangle(rect_mask, (x1 - lx1, y1 - ly1), (x2 - lx1, y2 - ly1), 255, -1)
    rect_area = float(np.count_nonzero(rect_mask))
    if rect_area == 0:
        return 0.0
    overlap = np.count_nonzero(cv2.bitwise_and(poly_mask, rect_mask))
    return overlap / rect_area


def filter_bboxes_by_polygon(bboxes, points, min_overlap=0.2):
    polygon = normalize_polygon_points(points)
    if polygon is None or bboxes is None:
        return np.array(bboxes, dtype=np.int32) if bboxes is not None else None
    # Fast-path Rust con banda di sicurezza: lo scanline RS differisce da
    # cv2 fino a ~0.06 sui casi limite, quindi i box entro
    # threshold +/- BAND sono rivalutati col Python esatto (parita 100%).
    try:
        from modules._rs_bridge import rs_overlap_ratio

        probe = rs_overlap_ratio([0, 0, 1, 1], polygon)
        if probe is not None:
            BAND = 0.06
            filtered = []
            for bbox in np.asarray(bboxes, dtype=np.int32):
                r = rs_overlap_ratio(bbox, polygon)
                if r is None:
                    r = bbox_polygon_overlap_ratio(bbox, polygon)
                elif abs(r - min_overlap) <= BAND:
                    r = bbox_polygon_overlap_ratio(bbox, polygon)
                if r >= min_overlap:
                    filtered.append(bbox)
            if not filtered:
                return np.array([], dtype=np.int32).reshape(0, 4)
            return np.array(filtered, dtype=np.int32)
    except Exception:
        pass
    filtered = []
    for bbox in np.asarray(bboxes, dtype=np.int32):
        if bbox_polygon_overlap_ratio(bbox, polygon) >= min_overlap:
            filtered.append(bbox)
    if not filtered:
        return np.array([], dtype=np.int32).reshape(0, 4)
    return np.array(filtered, dtype=np.int32)
