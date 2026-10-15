from __future__ import annotations

import colorsys
from typing import Tuple


RGBColor = Tuple[int, int, int]
HSLColor = Tuple[float, float, float]


def normalize_hex_color(color: str, fallback: str = "#000000") -> str:
    if not color or not isinstance(color, str):
        return fallback
    value = color.strip()
    if not value:
        return fallback
    if not value.startswith("#"):
        value = f"#{value}"
    if len(value) != 7:
        return fallback
    try:
        int(value[1:], 16)
    except ValueError:
        return fallback
    return value.upper()


def rgb_to_hex(rgb: RGBColor) -> str:
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_rgb(hex_color: str) -> RGBColor:
    value = normalize_hex_color(hex_color)
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def rgb_to_hsl(rgb: RGBColor) -> HSLColor:
    r, g, b = rgb
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return (h * 360.0, s, l)


def hsl_to_rgb(hsl: HSLColor) -> RGBColor:
    h_deg, s, l = hsl
    r, g, b = colorsys.hls_to_rgb((h_deg % 360.0) / 360.0, l, s)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

