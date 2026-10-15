"""
Test di regressione per la maschera di inpainting in modalità rettangolo.
"""
from pathlib import Path
import sys
import unittest

import numpy as np

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.utils.pipeline_utils import generate_mask
from modules.utils.textblock import TextBlock


class TestGenerateMaskRectangleMode(unittest.TestCase):
    def test_rectangle_mode_uses_full_active_bbox(self):
        img = np.zeros((100, 160, 3), dtype=np.uint8)
        blk = TextBlock(
            text_bbox=np.array([20, 20, 120, 60], dtype=np.int32),
            bubble_bbox=np.array([20, 20, 120, 60], dtype=np.int32),
            inpaint_bboxes=np.array([[30, 30, 50, 40]], dtype=np.int32),
            text_segm_points=np.array([[20, 20], [40, 20], [40, 35], [20, 35]], dtype=np.int32),
            text_class="text_bubble",
        )
        blk.use_polygon_inpaint = False

        mask = generate_mask(img, [blk])

        self.assertEqual(mask[50, 100], 255)
        self.assertEqual(mask[10, 10], 0)


if __name__ == "__main__":
    unittest.main()
