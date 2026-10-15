from pathlib import Path
import os
import sys
import tempfile
import unittest

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.canvas.svg_item import SvgItem


class TestSvgStyleImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.marvel_path = os.path.join(PROJECT_ROOT, "baloons", "marvel.svg")

    def test_svg_with_style_keeps_original_fill_color(self):
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60" viewBox="0 0 100 60">
  <rect x="0" y="0" width="100" height="60" style="fill:#ff0000;stroke:none;" />
</svg>
"""
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".svg",
                delete=False,
                encoding="utf-8",
            ) as temp_file:
                temp_file.write(svg_content)
                temp_path = temp_file.name

            item = SvgItem(temp_path)

            self.assertTrue(item.svg_renderer.isValid())
            self.assertIsNone(item._native_shape)

            image = QImage(100, 60, QImage.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            item.paint(painter, None)
            painter.end()

            center = image.pixelColor(50, 30)
            self.assertGreater(center.alpha(), 0)
            self.assertGreater(center.red(), 200)
            self.assertLess(center.green(), 80)
            self.assertLess(center.blue(), 80)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_svg_with_text_is_not_downgraded_to_native_rect(self):
        item = SvgItem(self.marvel_path)

        self.assertTrue(item.svg_renderer.isValid())
        self.assertIsNone(item._native_shape)


if __name__ == "__main__":
    unittest.main()
