import os
import sys

import cv2
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from modules.utils.color_formats import hex_to_rgb, normalize_hex_color, rgb_to_hex, rgb_to_hsl
from modules.utils.text_color_detector import detect_text_color_from_bbox


def test_color_format_roundtrip():
    hx = normalize_hex_color("ff00aa")
    assert hx == "#FF00AA"
    rgb = hex_to_rgb(hx)
    assert rgb == (255, 0, 170)
    assert rgb_to_hex(rgb) == "#FF00AA"
    h, s, l = rgb_to_hsl(rgb)
    assert 0.0 <= h <= 360.0
    assert 0.0 <= s <= 1.0
    assert 0.0 <= l <= 1.0


def test_detect_black_text_on_white():
    img = np.full((200, 400, 3), 255, dtype=np.uint8)
    cv2.putText(img, "TEST", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 0, 0), 6, cv2.LINE_AA)
    bbox = (20, 40, 360, 160)
    detected = detect_text_color_from_bbox(img, bbox, image_is_bgr=True)
    assert detected.hex in {"#000000", "#010101", "#020202"}


def test_detect_red_text_on_white():
    img = np.full((200, 400, 3), 255, dtype=np.uint8)
    cv2.putText(img, "RED", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 0, 255), 6, cv2.LINE_AA)
    bbox = (20, 40, 360, 160)
    detected = detect_text_color_from_bbox(img, bbox, image_is_bgr=True)
    assert detected.rgb[0] > 200
    assert detected.rgb[1] < 80
    assert detected.rgb[2] < 80


if __name__ == "__main__":
    test_color_format_roundtrip()
    test_detect_black_text_on_white()
    test_detect_red_text_on_white()
    print("[ALL PASSED] test_text_color_detection")

