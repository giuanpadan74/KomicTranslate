import os
import sys
import unittest
from pathlib import Path

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT / "_tmp" / "yolo_config"))
os.makedirs(os.environ["YOLO_CONFIG_DIR"], exist_ok=True)

from app.ui.canvas.image_viewer import ImageViewer


class TestPenSizeSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.viewer = ImageViewer(None)
        self.viewer.resize(400, 400)
        pixmap = QtGui.QPixmap(200, 200)
        pixmap.fill(QtGui.QColor("#ffffff"))
        self.viewer.setPhoto(pixmap)
        self.viewer.show()
        self.app.processEvents()

    def _draw_and_get_pen_width(self) -> float:
        scene_pos = QtCore.QPointF(20, 20)
        view_pos = self.viewer.mapFromScene(scene_pos)
        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(float(view_pos.x()), float(view_pos.y())),
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        self.viewer.mousePressEvent(event)
        self.assertIsNotNone(self.viewer.current_path_item)
        return float(self.viewer.current_path_item.pen().widthF())

    def test_pen_stroke_width_matches_after_settings_load(self):
        self.viewer.set_br_er_size(30, 30, tool_type="pen")
        self.viewer.set_tool("pen")
        self.assertEqual(self.viewer.pen_size, 30)
        self.assertEqual(self.viewer.pen_scaled_size, 30)
        self.assertEqual(self._draw_and_get_pen_width(), 30.0)

    def test_pen_tool_switch_repairs_scaled_size(self):
        self.viewer.pen_size = 30
        self.viewer.pen_scaled_size = 5
        self.viewer.pen_cursor = self.viewer.create_inpaint_cursor("pen", 5)
        self.viewer.set_tool("pen")
        self.assertEqual(self.viewer.pen_size, 30)
        self.assertEqual(self.viewer.pen_scaled_size, 30)
        self.assertEqual(self._draw_and_get_pen_width(), 30.0)

    def test_pen_value_change_applies_immediately(self):
        self.viewer.set_tool("pen")
        self.viewer.set_br_er_size(12, 12, tool_type="pen")
        self.assertEqual(self.viewer.pen_size, 12)
        self.assertEqual(self.viewer.pen_scaled_size, 12)
        self.assertEqual(self._draw_and_get_pen_width(), 12.0)


if __name__ == "__main__":
    unittest.main()
