from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.utils.polygon_region import (
    extract_polygon_from_mask,
    filter_polygon_points_to_outer_contour,
    polygon_to_bbox,
    simplify_outer_border_polygon,
)


class TestPolygonRegionOuterBorder(unittest.TestCase):
    def test_filter_removes_vertices_inside_main_contour(self):
        outer_contour = np.array(
            [[[10, 10]], [[90, 10]], [[90, 90]], [[10, 90]]],
            dtype=np.int32,
        )
        candidate_points = np.array(
            [[10, 10], [90, 10], [50, 50], [90, 90], [10, 90]],
            dtype=np.int32,
        )

        filtered = filter_polygon_points_to_outer_contour(
            candidate_points,
            outer_contour,
            max_inside_distance=1.0,
        )

        expected = np.array(
            [[10, 10], [90, 10], [90, 90], [10, 90]],
            dtype=np.int32,
        )
        np.testing.assert_array_equal(filtered, expected)

    def test_extract_polygon_ignores_thin_internal_notch(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        cv2.rectangle(mask, (10, 10), (90, 90), 255, -1)
        cv2.rectangle(mask, (48, 60), (52, 90), 0, -1)

        polygon = extract_polygon_from_mask(mask, epsilon_ratio=0.02)

        self.assertIsNotNone(polygon)
        bbox = polygon_to_bbox(polygon)
        np.testing.assert_array_equal(bbox, np.array([10, 10, 90, 90], dtype=np.int32))
        self.assertFalse(
            np.any(
                (polygon[:, 0] >= 45)
                & (polygon[:, 0] <= 55)
                & (polygon[:, 1] >= 55)
                & (polygon[:, 1] <= 70)
            )
        )

    def test_simplify_outer_border_removes_redundant_aligned_points(self):
        polygon = np.array(
            [[10, 10], [50, 10], [90, 10], [90, 90], [10, 90]],
            dtype=np.int32,
        )

        simplified = simplify_outer_border_polygon(polygon, tolerance_px=1.0)

        expected = np.array(
            [[10, 10], [90, 10], [90, 90], [10, 90]],
            dtype=np.int32,
        )
        np.testing.assert_array_equal(simplified, expected)


if __name__ == "__main__":
    unittest.main()
