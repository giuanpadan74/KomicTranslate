from __future__ import annotations

from typing import List

import numpy as np

from .text_color_detector import detect_text_color_from_bbox, detected_text_color_from_hex
from .text_color_models import DetectedTextColor


def enrich_blocks_with_text_color(
    image: np.ndarray,
    blk_list: List,
    *,
    image_is_bgr: bool = True,
    set_font_color_if_missing: bool = True,
) -> List:
    if not blk_list or image is None:
        return blk_list

    for blk in blk_list:
        if not hasattr(blk, "xyxy") or blk.xyxy is None or len(blk.xyxy) < 4:
            continue

        existing_hex = getattr(blk, "font_color", "") or ""
        if existing_hex.strip():
            detected = detected_text_color_from_hex(existing_hex)
        else:
            detected = detect_text_color_from_bbox(
                image,
                tuple(int(v) for v in blk.xyxy),
                image_is_bgr=image_is_bgr,
            )

        setattr(blk, "detected_text_color", detected.hex)
        setattr(blk, "detected_text_color_data", detected.to_dict())

        if set_font_color_if_missing and not (getattr(blk, "font_color", "") or "").strip():
            blk.font_color = detected.hex

    return blk_list
