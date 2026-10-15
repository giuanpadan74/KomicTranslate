import os
import uuid

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from app.ui.canvas.balloon_svg_item import BalloonSvgItem
from app.ui.canvas.svg_item import SvgItem


def _color_name(color, default="#00000000"):
    if isinstance(color, QColor):
        return color.name(QColor.HexArgb)
    if isinstance(color, str) and color:
        return color
    return default


def _tail_to_data(tail):
    return {
        "points": [[float(point.x()), float(point.y())] for point in getattr(tail, "points", [])],
        "original_points": [
            [float(point.x()), float(point.y())]
            for point in getattr(tail, "original_points", [])
        ],
    }


def _apply_tail_data(item, tail_data):
    if not isinstance(item, BalloonSvgItem):
        return
    for index, tail in enumerate(item.tails):
        if index >= len(tail_data):
            break
        data = tail_data[index]
        tail.points = [QPointF(point[0], point[1]) for point in data.get("points", [])]
        tail.original_points = [
            QPointF(point[0], point[1]) for point in data.get("original_points", [])
        ]


def clear_svg_items(viewer):
    scene = getattr(viewer, "_scene", None)
    if scene is None:
        return
    for item in list(scene.items()):
        if isinstance(item, SvgItem):
            scene.removeItem(item)


def serialize_svg_items(viewer):
    scene = getattr(viewer, "_scene", None)
    if scene is None:
        return []
    svg_items = []
    for item in scene.items():
        if not isinstance(item, SvgItem):
            continue
        svg_items.append(
            {
                "class_name": item.__class__.__name__,
                "item_id": getattr(item, "ctpr_item_id", None) or str(uuid.uuid4()),
                "filename": item.get_filename(),
                "svg_content": item._get_svg_content_for_save(),
                "position": [float(item.pos().x()), float(item.pos().y())],
                "scale": [float(item.scale_x), float(item.scale_y)],
                "rotation": float(item.rotation()),
                "current_rotation": float(getattr(item, "_current_rotation", 0.0)),
                "z_value": float(item.zValue()),
                "visible": bool(item.isVisible()),
                "enabled": bool(item.isEnabled()),
                "border_color": _color_name(item.border_color()),
                "border_width": float(item.border_width()),
                "show_border": bool(item.show_border()),
                "fill_color": _color_name(item.fill_color()),
                "show_fill": bool(item.show_fill()),
                "tails": [_tail_to_data(tail) for tail in getattr(item, "tails", [])],
                "selected_tail_index": int(getattr(item, "selected_tail_index", -1)),
            }
        )
    return list(reversed(svg_items))


def restore_svg_items(viewer, svg_items_data, storage_dir):
    clear_svg_items(viewer)
    scene = getattr(viewer, "_scene", None)
    if scene is None:
        return
    os.makedirs(storage_dir, exist_ok=True)
    for index, item_data in enumerate(svg_items_data or []):
        filename = item_data.get("filename") or f"svg_{index}.svg"
        svg_path = os.path.join(storage_dir, f"{index:03d}_{filename}")
        with open(svg_path, "w", encoding="utf-8") as handle:
            handle.write(item_data.get("svg_content", ""))
        item_class = BalloonSvgItem if item_data.get("class_name") == "BalloonSvgItem" else SvgItem
        svg_item = item_class(svg_path)
        svg_item.ctpr_item_id = item_data.get("item_id") or str(uuid.uuid4())
        scale = item_data.get("scale", [1.0, 1.0])
        svg_item.set_scale(scale_x=scale[0], scale_y=scale[1])
        svg_item.setPos(item_data.get("position", [0, 0])[0], item_data.get("position", [0, 0])[1])
        svg_item.setRotation(float(item_data.get("rotation", 0.0)))
        svg_item._current_rotation = float(item_data.get("current_rotation", 0.0))
        svg_item.setZValue(float(item_data.get("z_value", svg_item.zValue())))
        svg_item.setVisible(bool(item_data.get("visible", True)))
        svg_item.setEnabled(bool(item_data.get("enabled", True)))
        svg_item.set_border_color(item_data.get("border_color", "#00000000"))
        svg_item.set_border_width(float(item_data.get("border_width", 0.0)))
        svg_item.set_show_border(bool(item_data.get("show_border", False)))
        svg_item.set_fill_color(item_data.get("fill_color", "#00000000"))
        svg_item.set_show_fill(bool(item_data.get("show_fill", False)))
        _apply_tail_data(svg_item, item_data.get("tails", []))
        if isinstance(svg_item, BalloonSvgItem):
            svg_item.selected_tail_index = int(item_data.get("selected_tail_index", -1))
        scene.addItem(svg_item)
