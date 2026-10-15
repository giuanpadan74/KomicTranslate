import uuid

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath

from app.ui.canvas.text_item import OutlineInfo, OutlineType, TextBlockItem
from app.ui.canvas.brush_layer_rules import apply_text_box_layer
from app.ui.canvas.text_outline_utils import (
    outline_color_for_loading,
    outline_enabled_from_data,
)


def ensure_block_id(block):
    block_id = getattr(block, "block_id", None) or str(uuid.uuid4())
    block.block_id = block_id
    return block_id


def ensure_text_item_id(item):
    item_id = getattr(item, "ctpr_item_id", None) or str(uuid.uuid4())
    item.ctpr_item_id = item_id
    return item_id


def _color_name(color, default="#000000"):
    if isinstance(color, QColor):
        return color.name(QColor.HexArgb)
    if isinstance(color, str) and color:
        return color
    return default


def _outline_to_data(outline):
    return {
        "start": int(getattr(outline, "start", 0)),
        "end": int(getattr(outline, "end", 0)),
        "color": _color_name(getattr(outline, "color", None), "#ffffffff"),
        "width": float(getattr(outline, "width", 0.0)),
        "type": getattr(getattr(outline, "type", None), "value", None),
    }


def _outline_type(value):
    try:
        return OutlineType(value)
    except Exception:
        return OutlineType.Full_Document


def _outline_from_data(outline):
    if isinstance(outline, OutlineInfo):
        return OutlineInfo(outline.start, outline.end, QColor(outline.color), outline.width, outline.type)
    return OutlineInfo(
        start=int(outline.get("start", 0)),
        end=int(outline.get("end", 0)),
        color=QColor(outline.get("color", "#ffffffff")),
        width=float(outline.get("width", 0.0)),
        type=_outline_type(outline.get("type", OutlineType.Full_Document.value)),
    )


def serialize_text_item(item):
    linked_block_id = None
    blk = getattr(item, "blk", None)
    if blk is not None:
        linked_block_id = ensure_block_id(blk)
    return {
        "item_id": ensure_text_item_id(item),
        "linked_block_id": linked_block_id,
        "text": str(item.toHtml()),
        "position": [float(item.pos().x()), float(item.pos().y())],
        "rotation": float(item.rotation()),
        "scale": float(item.scale()),
        "transform_origin": [
            float(item.transformOriginPoint().x()),
            float(item.transformOriginPoint().y()),
        ],
        "font_family": str(getattr(item, "font_family", "")),
        "font_size": float(getattr(item, "font_size", 12)),
        "text_color": _color_name(getattr(item, "text_color", None)),
        "alignment": int(getattr(item, "alignment", Qt.AlignmentFlag.AlignCenter)),
        "line_spacing": float(getattr(item, "line_spacing", 1.0)),
        "outline": bool(getattr(item, "outline", False)),
        "outline_color": _color_name(getattr(item, "outline_color", None), "#ffffffff"),
        "outline_width": float(getattr(item, "outline_width", 0.0)),
        "bold": bool(getattr(item, "bold", False)),
        "italic": bool(getattr(item, "italic", False)),
        "underline": bool(getattr(item, "underline", False)),
        "direction": "rtl"
        if getattr(item, "direction", Qt.LayoutDirection.LeftToRight)
        == Qt.LayoutDirection.RightToLeft
        else "ltr",
        "width": float(item.boundingRect().width()),
        "height": float(item.boundingRect().height()),
        "visible": bool(item.isVisible()),
        "enabled": bool(item.isEnabled()),
        "opacity": float(item.opacity()),
        "z_value": float(item.zValue()),
        "selection_outlines": [
            _outline_to_data(outline)
            for outline in getattr(item, "selection_outlines", [])
        ],
    }


def create_text_item_from_data(item_data, parent_item):
    qt_direction = Qt.LayoutDirection.RightToLeft
    if str(item_data.get("direction", "ltr")).lower() not in ("rtl", "righttoleft"):
        qt_direction = Qt.LayoutDirection.LeftToRight
    outline_enabled = outline_enabled_from_data(item_data)
    text_item = TextBlockItem(
        text=item_data.get("text", ""),
        parent_item=parent_item,
        font_family=item_data.get("font_family", "Arial"),
        font_size=item_data.get("font_size", 12),
        render_color=item_data.get("text_color", "#000000"),
        alignment=item_data.get("alignment", int(Qt.AlignmentFlag.AlignCenter)),
        line_spacing=item_data.get("line_spacing", 1.0),
        outline_color=outline_color_for_loading(item_data, "#ffffffff"),
        outline_width=item_data.get("outline_width", 0) if outline_enabled else 0,
        bold=item_data.get("bold", False),
        italic=item_data.get("italic", False),
        underline=item_data.get("underline", False),
        direction=qt_direction,
        outline_enabled=outline_enabled,
    )
    if "width" in item_data:
        text_item.set_text(item_data.get("text", ""), item_data.get("width", 0))
    text_item.setPos(item_data.get("position", [0, 0])[0], item_data.get("position", [0, 0])[1])
    text_item.setRotation(item_data.get("rotation", 0.0))
    text_item.setScale(item_data.get("scale", 1.0))
    origin = item_data.get("transform_origin")
    if origin:
        text_item.setTransformOriginPoint(QPointF(origin[0], origin[1]))
    text_item.setVisible(bool(item_data.get("visible", True)))
    text_item.setEnabled(bool(item_data.get("enabled", True)))
    text_item.setOpacity(float(item_data.get("opacity", 1.0)))
    apply_text_box_layer(text_item)
    text_item.selection_outlines = [_outline_from_data(outline) for outline in item_data.get("selection_outlines", [])]
    text_item.ctpr_item_id = item_data.get("item_id") or str(uuid.uuid4())
    text_item.linked_block_id = item_data.get("linked_block_id")
    return text_item


def _path_to_data(path):
    def _element_type_to_int(element_type):
        if hasattr(element_type, "value"):
            return int(element_type.value)
        if hasattr(element_type, "__int__"):
            return int(element_type)
        return int(str(element_type))

    return [
        {
            "type": _element_type_to_int(path.elementAt(i).type),
            "x": float(path.elementAt(i).x),
            "y": float(path.elementAt(i).y),
        }
        for i in range(path.elementCount())
    ]


def _data_to_path(path_data):
    path = QPainterPath()
    for index, element in enumerate(path_data or []):
        elem_type = int(element.get("type", 0))
        x = float(element.get("x", 0.0))
        y = float(element.get("y", 0.0))
        if index == 0 or elem_type == 0:
            path.moveTo(x, y)
        elif elem_type == 1:
            path.lineTo(x, y)
        else:
            path.lineTo(x, y)
    return path


def serialize_brush_strokes(brush_strokes):
    return [
        {
            "path": _path_to_data(stroke["path"]),
            "pen": stroke["pen"],
            "brush": stroke["brush"],
            "width": int(stroke["width"]),
        }
        for stroke in brush_strokes or []
    ]


def deserialize_brush_strokes(brush_strokes):
    return [
        {
            "path": _data_to_path(stroke.get("path", [])),
            "pen": stroke.get("pen", "#ff000000"),
            "brush": stroke.get("brush", "#00000000"),
            "width": int(stroke.get("width", 1)),
        }
        for stroke in brush_strokes or []
    ]
