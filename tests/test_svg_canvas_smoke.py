from pathlib import Path
import os
import sys
import unittest

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.canvas.image_viewer import ImageViewer
from app.ui.canvas.svg_item import SvgItem
from app.ui.canvas.z_layers import (
    IMPORTED_SHAPE_LAYER_DEFAULT,
    IMPORTED_SHAPE_LAYER_MAX,
    IMPORTED_SHAPE_LAYER_MIN,
)


class TestSvgCanvasSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.svg_path = os.path.join(PROJECT_ROOT, "baloons", "rettangolo_piccolo.svg")

    def setUp(self):
        self.viewer = ImageViewer(None)
        self.svg_item = SvgItem(self.svg_path)
        self.viewer._scene.addItem(self.svg_item)
        self.svg_item.setZValue(IMPORTED_SHAPE_LAYER_DEFAULT)
        self.svg_item.setSelected(True)

    def test_svg_basic_flow(self):
        self.viewer.set_svg_border_color(QColor("#123456"))
        self.assertEqual(self.svg_item.border_color().name(), "#123456")
        self.assertTrue(self.svg_item.show_border())

        self.viewer.set_svg_fill_color(QColor("#abcdef"))
        self.assertEqual(self.svg_item.fill_color().name(), "#abcdef")
        self.assertTrue(self.svg_item.show_fill())

        self.viewer.set_svg_border_width(5)
        self.assertEqual(self.svg_item.border_width(), 5.0)

        self.viewer.bring_shape_to_front()
        self.assertGreaterEqual(self.svg_item.zValue(), IMPORTED_SHAPE_LAYER_MIN)
        self.assertLessEqual(self.svg_item.zValue(), IMPORTED_SHAPE_LAYER_MAX)

        self.viewer.send_shape_to_back()
        self.assertGreaterEqual(self.svg_item.zValue(), IMPORTED_SHAPE_LAYER_MIN)
        self.assertLessEqual(self.svg_item.zValue(), IMPORTED_SHAPE_LAYER_MAX)

        self.viewer.delete_selected_svgs()
        self.assertIsNone(self.svg_item.scene())
        self.assertEqual(self.viewer.get_selected_svg_items(), [])


if __name__ == "__main__":
    unittest.main()
