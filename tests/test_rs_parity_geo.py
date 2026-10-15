"""Parita RS vs Python per geometria (non-regression)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import komic_core_rs as rs
from modules.utils.polygon_region import (
    bbox_polygon_overlap_ratio as py_overlap,
    filter_bboxes_by_polygon as py_filter,
    simplify_outer_border_polygon as py_simplify,
)
from modules.utils.ellipse_mask import EllipseMaskGenerator as PyEllipse


def test_simplify_matches_python():
    rng = np.random.default_rng(3)
    cases = [
        np.array([[10, 10], [50, 10], [90, 10], [90, 90], [10, 90]], dtype=np.int32),
        np.array(rng.integers(0, 200, (12, 2)), dtype=np.int32),
    ]
    for c in cases:
        a = np.asarray(py_simplify(c, tolerance_px=1.5))
        b = np.array(rs.simplify_outer_border_polygon_rs(
            [list(map(int, r)) for r in c.tolist()], 1.5), dtype=np.int32)
        np.testing.assert_array_equal(a, b)


def test_ellipse_matches_python():
    rng = np.random.default_rng(5)
    for _ in range(200):
        pt = [float(v) for v in rng.uniform(0, 300, 2)]
        a = bool(PyEllipse.is_point_in_ellipse(pt, [150.0, 150.0], [100.0, 60.0],
                                              angle=15, exponent=2.5, scale=1.1))
        b = bool(rs.is_point_in_ellipse_rs(pt, [150.0, 150.0], [100.0, 60.0],
                                           15.0, 2.5, 1.1))
        assert a == b


def test_filter_band_matches_python_exactly():
    # La banda +/-0.06 nel bridge deve dare parita 100% col Python.
    import os
    os.environ.pop("KOMICTRANSLATE_NO_RS", None)
    from modules.utils.polygon_region import filter_bboxes_by_polygon as bridged
    rng = np.random.default_rng(11)
    poly = np.array([[50, 50], [250, 40], [260, 200], [40, 210]], dtype=np.int32)
    for _ in range(20):
        boxes = np.column_stack([
            rng.integers(0, 300, 30), rng.integers(0, 250, 30),
            rng.integers(0, 300, 30), rng.integers(0, 250, 30),
        ])
        boxes[:, 2] = boxes[:, 0] + np.abs(boxes[:, 2] - boxes[:, 0]) + 5
        boxes[:, 3] = boxes[:, 1] + np.abs(boxes[:, 3] - boxes[:, 1]) + 5
        os.environ["KOMICTRANSLATE_NO_RS"] = "1"
        try:
            expected = py_filter(boxes, poly, min_overlap=0.2)
        finally:
            os.environ.pop("KOMICTRANSLATE_NO_RS", None)
        got = bridged(boxes, poly, min_overlap=0.2)
        np.testing.assert_array_equal(np.asarray(got), np.asarray(expected))
