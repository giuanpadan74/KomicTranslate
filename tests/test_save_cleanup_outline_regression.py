from pathlib import Path
import os
import sys
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.controllers.save_cleanup import deactivate_viewer_selections
from app.ui.canvas.image_viewer import ImageViewer
from app.ui.canvas.text_item import TextBlockItem


class TestSaveCleanupOutlineRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_viewer(self):
        parent = QWidget()
        viewer = ImageViewer(parent)
        pixmap = QPixmap(200, 120)
        pixmap.fill(QColor("white"))
        viewer.setPhoto(pixmap)
        return parent, viewer

    def test_deactivate_keeps_full_document_outline(self):
        _parent, viewer = self._make_viewer()
        text_item = TextBlockItem(
            text="Ciao",
            parent_item=viewer.photo,
            render_color=QColor("#000000"),
            alignment=Qt.AlignmentFlag.AlignCenter,
            outline_color=QColor("#ffffff"),
            outline_width=1.5,
            outline_enabled=True,
        )
        text_item.set_plain_text("Ciao")
        viewer._scene.addItem(text_item)
        viewer.text_items.append(text_item)

        self.assertTrue(text_item.selection_outlines)

        deactivate_viewer_selections(viewer)

        self.assertTrue(text_item.outline)
        self.assertTrue(text_item.selection_outlines)
        self.assertEqual(text_item.selection_outlines[0].type.value, "full_document")
        self.assertEqual(text_item.selection_outlines[0].width, 1.5)

    def test_deactivate_keeps_outline_disabled(self):
        _parent, viewer = self._make_viewer()
        text_item = TextBlockItem(
            text="Ciao",
            parent_item=viewer.photo,
            render_color=QColor("#000000"),
            alignment=Qt.AlignmentFlag.AlignCenter,
            outline_color=None,
            outline_width=0,
            outline_enabled=False,
        )
        text_item.set_plain_text("Ciao")
        viewer._scene.addItem(text_item)
        viewer.text_items.append(text_item)

        deactivate_viewer_selections(viewer)

        self.assertFalse(text_item.outline)
        self.assertEqual(text_item.selection_outlines, [])


if __name__ == "__main__":
    unittest.main()
