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

from app.ui.canvas.image_viewer import ImageViewer
from app.ui.canvas.text_item import OutlineInfo, OutlineType, TextBlockItem
from app.ui.canvas.text_outline_utils import outline_enabled_from_data
from app.ui.canvas.z_layers import TEXT_BOX_Z
from app.projects.ctpr_state_support import create_text_item_from_data


class TestTextOutlinePersistence(unittest.TestCase):
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

    def test_viewer_state_preserves_disabled_outline(self):
        parent, viewer = self._make_viewer()
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
        text_item.setPos(10, 20)
        viewer._scene.addItem(text_item)
        viewer.text_items.append(text_item)

        state = viewer.save_state()

        restored_parent, restored_viewer = self._make_viewer()
        restored_viewer.load_state(state)
        self.assertEqual(len(restored_viewer.text_items), 1)

        restored_item = restored_viewer.text_items[0]
        self.assertFalse(restored_item.outline)
        self.assertIsNone(restored_item.outline_color)
        self.assertEqual(restored_item.outline_width, 0)
        self.assertEqual(restored_item.selection_outlines, [])
        self.assertIsNotNone(parent)
        self.assertIsNotNone(restored_parent)

    def test_outline_fallback_uses_width_for_old_payloads(self):
        self.assertTrue(
            outline_enabled_from_data(
                {"outline_color": "#ffffff", "outline_width": 1.2}
            )
        )
        self.assertFalse(
            outline_enabled_from_data(
                {"outline_color": "#ffffff", "outline_width": 0}
            )
        )

    def test_restore_accepts_runtime_outlineinfo_payload(self):
        _parent, viewer = self._make_viewer()
        item_data = {
            "text": "Test batch",
            "font_family": "Arial",
            "font_size": 18,
            "text_color": "#000000",
            "alignment": int(Qt.AlignmentFlag.AlignCenter),
            "line_spacing": 1.2,
            "outline": True,
            "outline_color": "#ffffffff",
            "outline_width": 1.5,
            "position": [12, 24],
            "rotation": 0.0,
            "scale": 1.0,
            "width": 120,
            "selection_outlines": [
                OutlineInfo(0, 10, QColor("#ffffffff"), 1.5, OutlineType.Full_Document)
            ],
        }

        restored_item = create_text_item_from_data(item_data, viewer.photo)

        self.assertEqual(restored_item.toPlainText(), "Test batch")
        self.assertEqual(len(restored_item.selection_outlines), 1)
        self.assertEqual(restored_item.selection_outlines[0].type, OutlineType.Full_Document)
        self.assertEqual(restored_item.selection_outlines[0].width, 1.5)

    def test_restore_forces_text_box_layer(self):
        _parent, viewer = self._make_viewer()
        item_data = {
            "text": "Layer test",
            "position": [0, 0],
            "rotation": 0.0,
            "scale": 1.0,
            "width": 120,
            "z_value": 0.0,
        }

        restored_item = create_text_item_from_data(item_data, viewer.photo)

        self.assertEqual(TEXT_BOX_Z, restored_item.zValue())


if __name__ == "__main__":
    unittest.main()
