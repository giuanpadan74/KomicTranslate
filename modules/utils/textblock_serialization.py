import uuid

import numpy as np

from .textblock import TextBlock


def _to_list(value):
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, (list, tuple)):
        return [float(v) if not isinstance(v, (list, tuple)) else v for v in value]
    return value


def serialize_text_block(block):
    if block is None or getattr(block, "xyxy", None) is None:
        return None
    block_id = getattr(block, "block_id", None) or str(uuid.uuid4())
    block.block_id = block_id
    return {
        "block_id": block_id,
        "xyxy": [float(x) for x in block.xyxy],
        "text": str(getattr(block, "text", "")),
        "translation": str(getattr(block, "translation", "")),
        "angle": float(getattr(block, "angle", 0.0)),
        "text_class": str(getattr(block, "text_class", "")),
        "font_size": float(getattr(block, "font_size", 12)),
        "bubble_xyxy": _to_list(getattr(block, "bubble_xyxy", None)),
        "polygon_points": _to_list(getattr(block, "polygon_points", None)),
        "original_polygon_points": _to_list(getattr(block, "_original_polygon_points", None)),
        "inpaint_bboxes": _to_list(getattr(block, "_all_inpaint_bboxes", None)),
        "shape_type": getattr(block, "shape_type", None),
        "use_polygon_inpaint": bool(getattr(block, "use_polygon_inpaint", True)),
        # use_polygon_layout indica che il blocco e' stato riadattato al
        # layout su poligono (impostato da text_polygon_mixin). Va salvato
        # insieme a use_polygon_inpaint, altrimenti salva/riapri un progetto
        # e il testo torna al layout rettangolare.
        "use_polygon_layout": bool(getattr(block, "use_polygon_layout", False)),
        "width": int(getattr(block, "width", 0) or 0),
        "height": int(getattr(block, "height", 0) or 0),
    }


def deserialize_text_block(data):
    xyxy = np.array(data.get("xyxy", [0, 0, 0, 0]), dtype=np.int32)
    bubble_xyxy = data.get("bubble_xyxy")
    polygon_points = data.get("polygon_points")
    original_polygon_points = data.get("original_polygon_points")
    block = TextBlock(
        text_bbox=xyxy,
        bubble_bbox=np.array(bubble_xyxy, dtype=np.int32) if bubble_xyxy else None,
        text_class=data.get("text_class", ""),
        inpaint_bboxes=data.get("inpaint_bboxes"),
        text_segm_points=np.array(polygon_points, dtype=np.int32) if polygon_points else None,
        angle=data.get("angle", 0.0),
        text=data.get("text", ""),
        translation=data.get("translation", ""),
        shape_type=data.get("shape_type"),
        width=data.get("width", int(xyxy[2] - xyxy[0])),
        height=data.get("height", int(xyxy[3] - xyxy[1])),
    )
    block.block_id = data.get("block_id") or str(uuid.uuid4())
    block.font_size = data.get("font_size", 12)
    if original_polygon_points:
        block._original_polygon_points = np.array(original_polygon_points, dtype=np.int32)
    else:
        polygon = getattr(block, "polygon_points", None)
        block._original_polygon_points = None if polygon is None else np.array(polygon, copy=True)
    block.use_polygon_inpaint = data.get("use_polygon_inpaint", True)
    block.use_polygon_layout = data.get("use_polygon_layout", False)
    return block
