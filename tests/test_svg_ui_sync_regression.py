from pathlib import Path
import os
import sys
import unittest

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.canvas.svg_item import SvgItem
from app.ui.main_window import ComicTranslateUI
from app.ui.widgets.color_button import MColorToolButton


class _FakeWindow:
    def __init__(self):
        self._current_svg_item = None
        self.width_input = QLineEdit()
        self.height_input = QLineEdit()
        self.fill_color_button = MColorToolButton()
        self.border_color_button = MColorToolButton()
        self.svg_border_width_selector = QComboBox()
        self.svg_border_width_selector.setEditable(True)
        self.svg_border_width_selector.addItems(["1", "2", "5"])

    def _update_size_inputs(self, _width, _height):
        return None


class TestSvgUiSyncRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.svg_path = os.path.join(PROJECT_ROOT, "baloons", "marvel.svg")

    def test_sync_shape_controls_does_not_emit_color_changes(self):
        svg_item = SvgItem(self.svg_path)
        fake_window = _FakeWindow()
        fill_changes = []
        border_changes = []

        fake_window.fill_color_button.colorChanged.connect(fill_changes.append)
        fake_window.border_color_button.colorChanged.connect(border_changes.append)

        ComicTranslateUI.sync_shape_controls(fake_window, svg_item)

        self.assertEqual(fill_changes, [])
        self.assertEqual(border_changes, [])
        self.assertFalse(svg_item.show_fill())
        self.assertFalse(svg_item.show_border())


if __name__ == "__main__":
    unittest.main()
