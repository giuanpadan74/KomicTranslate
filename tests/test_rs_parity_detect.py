"""Parita RS vs Python per detection box-math (non-regression)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

import komic_core_rs as rs
from modules.detection import (
    calculate_iou,
    does_rectangle_fit,
    do_rectangles_overlap,
    is_mostly_contained,
    merge_bounding_boxes,
    _match_bubble_index,
)

NEED = ["calculate_iou_rs", "do_rectangles_overlap_rs",
        "does_rectangle_fit_rs", "is_mostly_contained_rs",
        "match_bubble_index_rs", "merge_bounding_boxes_rs",
        "edge_support_ratio_rs"]
HAS_DETECT_RS = all(hasattr(rs, f) for f in NEED)


def _boxes(rng, n, lo=0, hi=1200, grow=(20, 120, 15, 60)):
    if n == 0:
        return np.zeros((0, 4), dtype=int)
    b = np.array([[rng.integers(lo, hi), rng.integers(lo, hi),
                   rng.integers(lo, hi), rng.integers(lo, hi)]
                  for _ in range(n)])
    b[:, 2] += rng.integers(grow[0], grow[1], n)
    b[:, 3] += rng.integers(grow[2], grow[3], n)
    return b


@pytest.mark.skipif(not HAS_DETECT_RS, reason="build RS senza modulo detection")
def test_scalars_match_python():
    import random
    rng = random.Random(0)
    for _ in range(1000):
        a = [rng.randint(-50, 1300) for _ in range(4)]
        b = [rng.randint(-50, 1300) for _ in range(4)]
        assert calculate_iou(a, b) == rs.calculate_iou_rs(a, b)
        for thr in (0.02, 0.1, 0.2, 0.6):
            assert do_rectangles_overlap(a, b, thr) == rs.do_rectangles_overlap_rs(a, b, thr)
        assert bool(does_rectangle_fit(a, b)) == bool(rs.does_rectangle_fit_rs(a, b))
        assert bool(is_mostly_contained(a, b, 0.5)) == bool(rs.is_mostly_contained_rs(a, b, 0.5))


@pytest.mark.skipif(not HAS_DETECT_RS, reason="build RS senza modulo detection")
def test_match_and_merge_match_python():
    import random
    rng = random.Random(1)
    for _ in range(30):
        bub = _boxes(np.random.default_rng(rng.randint(0, 9999)), rng.randint(0, 6))
        t = [rng.randint(0, 1200), rng.randint(0, 1600),
             rng.randint(0, 1200) + 60, rng.randint(0, 1600) + 25]
        assert _match_bubble_index(np.array(t), bub) == rs.match_bubble_index_rs(
            t, [[int(v) for v in r] for r in bub.tolist()])
    for _ in range(10):
        seed = rng.randint(0, 9999)
        r0 = np.random.default_rng(seed)
        seg, det, bub = _boxes(r0, 8), _boxes(r0, 8), _boxes(r0, 4)
        si = [_match_bubble_index(b, bub) for b in seg]
        di = [_match_bubble_index(b, bub) for b in det]
        a = sorted((tuple(map(int, box)), bi) for box, bi in merge_bounding_boxes(seg, si, det, di))
        r = rs.merge_bounding_boxes_rs(
            [[int(v) for v in row] for row in seg.tolist()], list(si),
            [[int(v) for v in row] for row in det.tolist()], list(di))
        assert a == sorted((tuple(box), bi) for box, bi in r)


@pytest.mark.skipif(not HAS_DETECT_RS, reason="build RS senza modulo detection")
def test_edge_support_matches_python():
    import cv2
    from modules.detection import _edge_support_ratio
    rng = np.random.default_rng(2)
    for _ in range(20):
        h, w = map(int, rng.integers(80, 300, 2))
        poly = (rng.random((int(rng.integers(3, 8)), 2)) * [w, h]).astype(np.float32)
        edges = np.zeros((h, w), dtype=np.uint8)
        cv2.polylines(edges, [poly.astype(np.int32)], True, 255, 2)
        inv = np.zeros_like(edges)
        inv[edges == 0] = 255
        dist = cv2.distanceTransform(inv, cv2.DIST_L2, 3)
        a = float(_edge_support_ratio(poly, edges))
        b = float(rs.edge_support_ratio_rs(dist.astype(np.float32).ravel().tolist(),
                                           w, h, [[float(v) for v in p] for p in poly.tolist()]))
        assert abs(a - b) < 1e-9
