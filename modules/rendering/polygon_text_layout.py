import html
import math
import re

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetricsF

from ..utils.polygon_region import normalize_polygon_points, polygon_to_bbox
def build_polygon_text_layout(
    text,
    polygon_points,
    font_family,
    line_spacing,
    outline_width,
    bold,
    italic,
    underline,
    alignment,
    direction,
    init_font_size,
    min_font_size=10,
):
    polygon = normalize_polygon_points(polygon_points)
    if polygon is None or not text or not str(text).strip():
        return None
    bbox = polygon_to_bbox(polygon)
    x1, y1, x2, y2 = [int(v) for v in bbox]
    bbox_width = max(1, x2 - x1)
    bbox_height = max(1, y2 - y1)
    padding = max(1.0, float(outline_width) * 2.0)
    available_height = bbox_height - (padding * 2.0)
    if available_height <= 0:
        return None

    for font_size in range(int(init_font_size), int(min_font_size) - 1, -1):
        metrics = _build_metrics(font_family, font_size, bold, italic, underline)
        line_height = max(1.0, metrics.height() * float(line_spacing) + (float(outline_width) * 2.0))
        max_lines = max(1, int(available_height // line_height))
        for line_count in range(1, max_lines + 1):
            spans, top_y = _compute_spans(polygon, x1, y1, y2, line_count, line_height, padding)
            if not spans:
                continue
            lines = _wrap_text(text, spans, metrics)
            if lines is None:
                continue
            return {
                "text": _build_html(lines, spans, bbox_width, line_spacing, alignment, direction),
                "plain_text": "\n".join(lines),
                "font_size": font_size,
                "position": (float(x1), float(top_y)),
                "width": float(bbox_width),
                "polygon_layout": True,
            }
    return None
def _build_metrics(font_family, font_size, bold, italic, underline):
    font = QFont(font_family, int(font_size))
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    font.setUnderline(bool(underline))
    return QFontMetricsF(font)
def _compute_spans(polygon, bbox_x1, bbox_y1, bbox_y2, line_count, line_height, padding):
    total_height = line_count * line_height
    available_height = max(1.0, float(bbox_y2 - bbox_y1) - (padding * 2.0))
    if total_height > available_height + 0.5:
        return None, None
    top_y = float(bbox_y1) + padding + max(0.0, (available_height - total_height) / 2.0)
    spans = []
    min_width = max(8.0, line_height * 1.1)
    for index in range(line_count):
        center_y = top_y + (index * line_height) + (line_height / 2.0)
        span = _span_at_y(polygon, center_y)
        if span is None:
            return None, None
        left, right = span
        left += padding
        right -= padding
        width = right - left
        if width < min_width:
            return None, None
        spans.append({
            "left": float(left - bbox_x1),
            "width": float(width),
        })
    return spans, top_y
def _span_at_y(polygon, y_value):
    # Fast-path Rust (parita 51/51 verificata). Fallback Python invariato.
    try:
        from modules._rs_bridge import rs_span_at_y

        rs_result = rs_span_at_y(np.asarray(polygon, dtype=np.float64), y_value)
        if rs_result is not None:
            return rs_result
    except Exception:
        pass
    intersections = []
    points = np.asarray(polygon, dtype=np.float64)
    total = len(points)
    for index in range(total):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % total]
        if y1 == y2:
            continue
        if (y1 <= y_value < y2) or (y2 <= y_value < y1):
            ratio = (y_value - y1) / (y2 - y1)
            intersections.append(x1 + ratio * (x2 - x1))
    if len(intersections) < 2:
        return None
    intersections.sort()
    segments = [
        (intersections[i], intersections[i + 1])
        for i in range(0, len(intersections) - 1, 2)
    ]
    if not segments:
        return None
    return max(segments, key=lambda item: item[1] - item[0])
def _wrap_text(text, spans, metrics):
    cleaned = re.sub(r"\s+", " ", str(text).replace("\n", " ")).strip()
    if not cleaned:
        return None
    tokens = _tokenize(cleaned)
    lines = []
    token_index = 0
    for span in spans:
        if token_index >= len(tokens):
            break
        line, token_index = _fit_line(tokens, token_index, span["width"], metrics)
        if not line:
            return None
        lines.append(line)
    if token_index < len(tokens):
        return None
    return lines
def _tokenize(text):
    if " " not in text:
        return list(text)
    return text.split(" ")


def _fit_line(tokens, start_index, max_width, metrics):
    line = ""
    index = start_index
    while index < len(tokens):
        token = tokens[index]
        candidate = token if not line else f"{line} {token}"
        if metrics.horizontalAdvance(candidate) <= max_width:
            line = candidate
            index += 1
            continue
        if line:
            return line, index
        fragment, consumed = _split_token(token, max_width, metrics)
        if not fragment:
            return None, start_index
        tokens[index:index + 1] = consumed
        line = tokens[index]
        index += 1
        return line, index
    return line, index


def _split_token(token, max_width, metrics):
    pieces = []
    current = ""
    for char in token:
        candidate = current + char
        if current and metrics.horizontalAdvance(candidate) > max_width:
            pieces.append(current)
            current = char
        else:
            current = candidate
    if current:
        pieces.append(current)
    if not pieces or metrics.horizontalAdvance(pieces[0]) > max_width:
        return None, [token]
    return pieces[0], pieces


def _build_html(lines, spans, bbox_width, line_spacing, alignment, direction):
    align_css = _alignment_css(alignment)
    direction_css = "rtl" if direction == Qt.LayoutDirection.RightToLeft else "ltr"
    line_height_css = max(100, int(math.ceil(float(line_spacing) * 100)))
    html_lines = []
    for line, span in zip(lines, spans):
        escaped = html.escape(line)
        html_lines.append(
            f"<div style=\"margin-left:{span['left']:.1f}px;width:{span['width']:.1f}px;"
            f"text-align:{align_css};line-height:{line_height_css}%;\">{escaped}</div>"
        )
    return (
        f"<div style=\"margin:0;padding:0;width:{bbox_width:.1f}px;direction:{direction_css};\">"
        + "".join(html_lines)
        + "</div>"
    )


def _alignment_css(alignment):
    if alignment == Qt.AlignmentFlag.AlignLeft:
        return "left"
    if alignment == Qt.AlignmentFlag.AlignRight:
        return "right"
    return "center"
