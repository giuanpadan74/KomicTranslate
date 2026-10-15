from pathlib import Path
import os
import sys
import unittest

from PySide6.QtGui import QPainterPath


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.projects.ctpr_state_support import deserialize_brush_strokes, serialize_brush_strokes


class TestCtprBrushStrokeSerialization(unittest.TestCase):
    def test_serialize_brush_stroke_path_element_type(self):
        path = QPainterPath()
        path.moveTo(10, 20)
        path.lineTo(30, 40)

        data = serialize_brush_strokes(
            [{"path": path, "pen": "#ff000000", "brush": "#00000000", "width": 3}]
        )

        self.assertEqual(2, len(data[0]["path"]))
        self.assertIsInstance(data[0]["path"][0]["type"], int)
        self.assertEqual(0, data[0]["path"][0]["type"])
        self.assertEqual(1, data[0]["path"][1]["type"])

    def test_deserialize_brush_stroke_roundtrip(self):
        path = QPainterPath()
        path.moveTo(1, 2)
        path.lineTo(3, 4)

        serialized = serialize_brush_strokes(
            [{"path": path, "pen": "#ff000000", "brush": "#00000000", "width": 2}]
        )
        restored = deserialize_brush_strokes(serialized)

        self.assertEqual(1, len(restored))
        self.assertEqual(2, restored[0]["path"].elementCount())
        self.assertEqual(2, restored[0]["width"])


if __name__ == "__main__":
    unittest.main()
