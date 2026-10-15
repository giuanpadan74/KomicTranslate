from pathlib import Path
import os
import sys
import unittest

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.canvas.image_viewer import ImageViewer
from app.ui.commands.bucket import BucketFillCommand


class _ControllerStub(QWidget):
    def __init__(self):
        super().__init__()
        self.image_files = ["page_001"]
        self.curr_img_idx = 0
        self.image_data = {}


class TestBucketFillStateSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_viewer(self):
        parent = _ControllerStub()
        viewer = ImageViewer(parent)
        pixmap = QPixmap(8, 8)
        pixmap.fill(QColor("white"))
        viewer.setPhoto(pixmap)
        parent.image_data["page_001"] = np.full((8, 8, 3), 255, dtype=np.uint8)
        return parent, viewer

    def test_bucket_fill_syncs_image_data_immediately(self):
        parent, viewer = self._make_viewer()
        viewer.set_painting_color(QColor("#ff0000"))

        viewer.flood_fill_at(QPointF(1, 1), async_exec=False)

        stored = parent.image_data["page_001"]
        self.assertEqual((8, 8, 3), stored.shape)
        self.assertTrue(np.array_equal(stored[1, 1], np.array([255, 0, 0], dtype=np.uint8)))

    def test_bucket_command_undo_redo_syncs_image_data(self):
        parent, viewer = self._make_viewer()
        old_pixmap = viewer.photo.pixmap().copy()
        new_pixmap = QPixmap(8, 8)
        new_pixmap.fill(QColor("#00ff00"))

        viewer.photo.setPixmap(new_pixmap)
        parent.image_data["page_001"] = np.full((8, 8, 3), [0, 255, 0], dtype=np.uint8)

        command = BucketFillCommand(viewer, old_pixmap, new_pixmap)
        command.redo()

        command.undo()
        self.assertTrue(
            np.array_equal(
                parent.image_data["page_001"][1, 1],
                np.array([255, 255, 255], dtype=np.uint8),
            )
        )

        command.redo()
        self.assertTrue(
            np.array_equal(
                parent.image_data["page_001"][1, 1],
                np.array([0, 255, 0], dtype=np.uint8),
            )
        )


if __name__ == "__main__":
    unittest.main()
