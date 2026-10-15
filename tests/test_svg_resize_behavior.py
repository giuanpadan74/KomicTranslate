from pathlib import Path
import os
import sys
import unittest

from PySide6.QtCore import QPointF
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.canvas.svg_item import SvgItem
from app.ui.canvas.z_layers import (
    ACTIVE_IMPORTED_SHAPE_PREVIEW_Z,
    IMPORTED_SHAPE_LAYER_DEFAULT,
)


class _FakeMouseEvent:
    def __init__(self, button, pos):
        self._button = button
        self._pos = pos
        self.accepted = False

    def button(self):
        return self._button

    def pos(self):
        return self._pos

    def accept(self):
        self.accepted = True


class TestSvgResizeBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.svg_path = os.path.join(PROJECT_ROOT, "baloons", "rettangolo_piccolo.svg")

    def setUp(self):
        self.item = SvgItem(self.svg_path)
        self.item.setPos(100, 50)
        self.start_width = self.item.svg_size.width() * self.item.scale_x
        self.start_height = self.item.svg_size.height() * self.item.scale_y

    def _start_drag(self):
        self.item._drag_start_pos = QPointF(0, 0)
        self.item._drag_start_item_pos = QPointF(self.item.pos())
        self.item._drag_start_scale_x = self.item.scale_x
        self.item._drag_start_scale_y = self.item.scale_y

    def test_left_resize_does_not_accumulate_position_drift(self):
        self._start_drag()

        self.item._resize_by_handle(QPointF(20, 0), "left")
        first_pos = QPointF(self.item.pos())
        first_scale = self.item.scale_x

        self.item._resize_by_handle(QPointF(20, 0), "left")
        second_pos = QPointF(self.item.pos())
        second_scale = self.item.scale_x

        self.assertEqual(first_pos, second_pos)
        self.assertEqual(first_scale, second_scale)
        self.assertAlmostEqual(first_pos.x(), 120.0, places=4)

    def test_top_left_resize_keeps_opposite_corner_fixed(self):
        self._start_drag()
        start_bottom_right = QPointF(
            self.item.pos().x() + self.start_width,
            self.item.pos().y() + self.start_height,
        )

        self.item._resize_by_handle(QPointF(20, 10), "top_left")

        new_size = self.item.get_scaled_size()
        new_bottom_right = QPointF(
            self.item.pos().x() + new_size.width(),
            self.item.pos().y() + new_size.height(),
        )

        self.assertAlmostEqual(start_bottom_right.x(), new_bottom_right.x(), places=4)
        self.assertAlmostEqual(start_bottom_right.y(), new_bottom_right.y(), places=4)

    def test_bounding_rect_includes_resize_handles(self):
        rect = self.item.boundingRect()
        half_handle = self.item._handle_size / 2.0

        self.assertLessEqual(rect.left(), -half_handle)
        self.assertLessEqual(rect.top(), -half_handle)
        self.assertGreaterEqual(rect.right(), self.start_width + half_handle)
        self.assertGreaterEqual(rect.bottom(), self.start_height + half_handle)

    def test_get_current_size_returns_qsize(self):
        size = self.item.get_current_size()
        self.assertEqual(size.width(), int(self.start_width))
        self.assertEqual(size.height(), int(self.start_height))

    def test_resize_temporarily_brings_svg_above_text(self):
        self.item.setZValue(IMPORTED_SHAPE_LAYER_DEFAULT)
        self.item.setSelected(True)
        self.item._update_handles()

        handle_rect = self.item._handles["bottom_right"]
        press_event = _FakeMouseEvent(Qt.LeftButton, handle_rect.center())

        self.item.mousePressEvent(press_event)

        self.assertTrue(press_event.accepted)
        self.assertEqual(self.item.zValue(), ACTIVE_IMPORTED_SHAPE_PREVIEW_Z)

        release_event = _FakeMouseEvent(Qt.LeftButton, handle_rect.center())
        self.item.mouseReleaseEvent(release_event)

        self.assertTrue(release_event.accepted)
        self.assertEqual(self.item.zValue(), IMPORTED_SHAPE_LAYER_DEFAULT)


if __name__ == "__main__":
    unittest.main()
