from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np
from sklearn.cluster import KMeans

from .color_formats import hex_to_rgb, normalize_hex_color, rgb_to_hex, rgb_to_hsl
from .text_color_models import ColorSwatch, DetectedTextColor


def detect_text_color_from_bbox(
    image: np.ndarray,
    bbox_xyxy: Tuple[int, int, int, int],
    *,
    image_is_bgr: bool = True,
    n_clusters: int = 6,
    min_cluster_ratio: float = 0.02,
    gradient_confidence_threshold: float = 0.7,
) -> DetectedTextColor:
    if image is None or image.size == 0:
        return _fallback("image_empty")

    x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
    h, w = image.shape[:2]
    x1 = max(0, min(x1, w - 1))
    y1 = max(0, min(y1, h - 1))
    x2 = max(x1 + 1, min(x2, w))
    y2 = max(y1 + 1, min(y2, h))

    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return _fallback("empty_crop")

    if image_is_bgr:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

    crop = _downscale(crop, max_pixels=50000)
    pixels = crop.reshape(-1, 3).astype(np.float32)
    if pixels.shape[0] < 10:
        return _fallback("too_few_pixels")

    km = KMeans(n_clusters=min(n_clusters, pixels.shape[0]), random_state=42, n_init=10)
    labels = km.fit_predict(pixels)
    centers = km.cluster_centers_.astype(np.float32)

    unique, counts = np.unique(labels, return_counts=True)
    total = float(np.sum(counts))
    if total <= 0:
        return _fallback("no_pixels")

    bg_idx = int(unique[int(np.argmax(counts))])
    bg_center = centers[bg_idx]

    candidates: List[Tuple[int, float, float]] = []
    for idx, count in zip(unique, counts):
        idx = int(idx)
        if idx == bg_idx:
            continue
        ratio = float(count) / total
        if ratio < min_cluster_ratio:
            continue
        dist = float(np.linalg.norm(centers[idx] - bg_center))
        candidates.append((idx, dist, ratio))

    if not candidates:
        bg_rgb = tuple(int(round(v)) for v in bg_center.tolist())
        bg_hex = rgb_to_hex(bg_rgb)
        return DetectedTextColor(
            hex=bg_hex,
            rgb=bg_rgb,
            hsl=rgb_to_hsl(bg_rgb),
            confidence=0.0,
            is_gradient=False,
            palette=[],
            method="background_only",
        )

    candidates.sort(key=lambda x: x[1], reverse=True)
    text_idx = int(candidates[0][0])

    non_bg_counts = sum(float(c) for i, c in zip(unique, counts) if int(i) != bg_idx)
    text_count = float(dict(zip(unique.tolist(), counts.tolist())).get(text_idx, 0.0))
    confidence = (text_count / non_bg_counts) if non_bg_counts > 0 else 0.0

    palette = _build_palette(centers, unique, counts, bg_idx, top_k=3)

    text_rgb = tuple(int(round(v)) for v in centers[text_idx].tolist())
    text_hex = rgb_to_hex(text_rgb)
    is_gradient = bool(confidence < gradient_confidence_threshold and len(palette) > 1)

    return DetectedTextColor(
        hex=text_hex,
        rgb=text_rgb,
        hsl=rgb_to_hsl(text_rgb),
        confidence=float(max(0.0, min(1.0, confidence))),
        is_gradient=is_gradient,
        palette=palette,
        method="image_cluster",
    )


def detected_text_color_from_hex(hex_color: str) -> DetectedTextColor:
    hx = normalize_hex_color(hex_color)
    rgb = hex_to_rgb(hx)
    return DetectedTextColor(
        hex=hx,
        rgb=rgb,
        hsl=rgb_to_hsl(rgb),
        confidence=1.0,
        is_gradient=False,
        palette=[],
        method="provided_hex",
    )


def _build_palette(
    centers: np.ndarray,
    unique: np.ndarray,
    counts: np.ndarray,
    bg_idx: int,
    *,
    top_k: int,
) -> List[ColorSwatch]:
    total = float(np.sum(counts))
    entries: List[Tuple[int, float]] = []
    for idx, count in zip(unique, counts):
        idx = int(idx)
        if idx == bg_idx:
            continue
        entries.append((idx, float(count) / total if total > 0 else 0.0))

    entries.sort(key=lambda x: x[1], reverse=True)
    entries = entries[:top_k]

    palette: List[ColorSwatch] = []
    for idx, ratio in entries:
        rgb = tuple(int(round(v)) for v in centers[idx].tolist())
        palette.append(ColorSwatch(hex=rgb_to_hex(rgb), rgb=rgb, hsl=rgb_to_hsl(rgb), ratio=ratio))
    return palette


def _downscale(img_rgb: np.ndarray, *, max_pixels: int) -> np.ndarray:
    h, w = img_rgb.shape[:2]
    if h * w <= max_pixels:
        return img_rgb
    scale = float(np.sqrt(max_pixels / float(h * w)))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _fallback(reason: str) -> DetectedTextColor:
    rgb = (0, 0, 0)
    return DetectedTextColor(
        hex="#000000",
        rgb=rgb,
        hsl=rgb_to_hsl(rgb),
        confidence=0.0,
        is_gradient=False,
        palette=[],
        method=reason,
    )
