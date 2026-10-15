from pathlib import Path
import os
import sys
import unittest

from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsScene, QWidget


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.canvas.image_viewer import ImageViewer
from app.ui.canvas.layer_preserve import BrushStrokeSnapshot, LayerPreserveManager
from app.ui.canvas.text_item import TextBlockItem
from app.ui.canvas.z_layers import BRUSH_STROKE_Z, TEXT_BOX_Z
from app.ui.commands.base import PathCommandBase


class _ControllerStub(QWidget):
    def __init__(self):
        super().__init__()
        self.image_files = ["page_001"]
        self.curr_img_idx = 0
        self.image_data = {}


class TestBrushLayerRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_create_path_item_forces_brush_layer(self):
        path = QPainterPath()
        path.moveTo(1, 1)
        path.lineTo(5, 5)
        properties = {
            "path": path,
            "pen": "#80ff0000",
            "brush": "#80ff0000",
            "width": 3,
            "pen_settings": {
                "color": QColor("#80ff0000"),
                "width": 3,
                "style": QPen().style(),
                "cap": QPen().capStyle(),
                "join": QPen().joinStyle(),
            },
        }

        item = PathCommandBase.create_path_item(properties)

        self.assertEqual(BRUSH_STROKE_Z, item.zValue())
        self.assertLess(item.zValue(), TEXT_BOX_Z)

    def test_load_brush_strokes_forces_brush_layer(self):
        parent = _ControllerStub()
        viewer = ImageViewer(parent)
        pixmap = QPixmap(8, 8)
        pixmap.fill(QColor("white"))
        viewer.setPhoto(pixmap)

        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(3, 3)
        viewer.load_brush_strokes(
            [{"path": path, "pen": "#ff000000", "brush": "#00000000", "width": 2}]
        )

        path_items = [item for item in viewer._scene.items() if hasattr(item, "path")]
        self.assertTrue(path_items)
        self.assertEqual(BRUSH_STROKE_Z, path_items[0].zValue())
        self.assertLess(path_items[0].zValue(), TEXT_BOX_Z)

    def test_load_brush_strokes_restores_text_box_layer(self):
        parent = _ControllerStub()
        viewer = ImageViewer(parent)
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor("white"))
        viewer.setPhoto(pixmap)

        text_item = TextBlockItem(text="Ciao", parent_item=viewer.photo)
        viewer._scene.addItem(text_item)
        viewer.text_items.append(text_item)
        text_item.setZValue(BRUSH_STROKE_Z)

        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(5, 5)
        viewer.load_brush_strokes(
            [{"path": path, "pen": "#ff000000", "brush": "#00000000", "width": 2}]
        )

        self.assertEqual(TEXT_BOX_Z, text_item.zValue())

    def test_layer_preserve_restore_ignores_higher_snapshot_z(self):
        scene = QGraphicsScene()
        manager = LayerPreserveManager(scene)
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(4, 4)
        snapshot = BrushStrokeSnapshot(
            path_data=[
                {"type": 0, "x": 0.0, "y": 0.0},
                {"type": 1, "x": 4.0, "y": 4.0},
            ],
            pen={
                "color": QColor("#ff000000").name(QColor.HexArgb),
                "width": 2,
                # .value (non int(...)): le enum PySide6 >= 6.9 non supportano piu' int().
                # Allineato al formato prodotto da app/ui/canvas/layer_preserve.py.
                "style": QPen().style().value,
                "cap": QPen().capStyle().value,
                "join": QPen().joinStyle().value,
            },
            brush={
                "color": QBrush(QColor("#00000000")).color().name(QColor.HexArgb),
                "style": QBrush().style().value,
            },
            z_index=999.0,
            position=QPointF(2, 2),
        )

        manager._restore_brush_strokes([snapshot])

        restored = scene.items()
        self.assertEqual(1, len(restored))
        self.assertEqual(BRUSH_STROKE_Z, restored[0].zValue())
        self.assertLess(restored[0].zValue(), TEXT_BOX_Z)


if __name__ == "__main__":
    unittest.main()
