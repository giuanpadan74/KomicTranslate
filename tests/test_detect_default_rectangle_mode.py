from pathlib import Path
import sys
import unittest

import numpy as np

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.detection import TextBlockDetector
from modules.utils.textblock_serialization import (
    deserialize_text_block,
    serialize_text_block,
)


class TestDetectDefaultPolygonMode(unittest.TestCase):
    def test_detected_blocks_start_in_polygon_mode(self):
        detector = TextBlockDetector.__new__(TextBlockDetector)
        detector.device = "cpu"
        detector.bubble_detection = lambda *args, **kwargs: [object()]
        detector.text_segmentation = lambda *args, **kwargs: [object()]
        detector.text_detection = lambda *args, **kwargs: [object()]
        detector.combine_results = lambda *args, **kwargs: [
            (
                np.array([10, 10, 100, 50], dtype=np.int32),
                np.array([5, 5, 110, 60], dtype=np.int32),
                np.array([[8, 8], [108, 10], [104, 58], [6, 54]], dtype=np.int32),
                [(20, 20, 30, 30)],
                "text_bubble",
            )
        ]

        blk_list = detector.detect(np.zeros((80, 140, 3), dtype=np.uint8))

        self.assertEqual(len(blk_list), 1)
        blk = blk_list[0]
        self.assertTrue(blk.use_polygon_inpaint)
        np.testing.assert_array_equal(blk._original_polygon_points, blk.polygon_points)

    def test_polygon_mode_persists_after_serialization(self):
        detector = TextBlockDetector.__new__(TextBlockDetector)
        detector.device = "cpu"
        detector.bubble_detection = lambda *args, **kwargs: [object()]
        detector.text_segmentation = lambda *args, **kwargs: [object()]
        detector.text_detection = lambda *args, **kwargs: [object()]
        original_polygon = np.array([[8, 8], [108, 10], [104, 58], [6, 54]], dtype=np.int32)
        detector.combine_results = lambda *args, **kwargs: [
            (
                np.array([10, 10, 100, 50], dtype=np.int32),
                np.array([5, 5, 110, 60], dtype=np.int32),
                original_polygon,
                [(20, 20, 30, 30)],
                "text_bubble",
            )
        ]

        blk = detector.detect(np.zeros((80, 140, 3), dtype=np.uint8))[0]
        restored = deserialize_text_block(serialize_text_block(blk))

        self.assertTrue(restored.use_polygon_inpaint)
        np.testing.assert_array_equal(restored._original_polygon_points, original_polygon)


if __name__ == "__main__":
    unittest.main()
