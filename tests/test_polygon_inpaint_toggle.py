"""
Test per il pulsante di commutazione poligono/rettangolo per inpainting.

Verifica che:
1. Il pulsante sia visibile solo quando ci sono caselle selezionate
2. La modalità rettangolo si applichi correttamente agli elementi selezionati
3. La commutazione sia istantanea e limitata agli elementi selezionati
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.utils.textblock import TextBlock
from app.controllers.polygon_inpaint_mixin import PolygonInpaintMixin


class _StubRectItem:
    """Stub per MoveableRectItem."""
    def __init__(self, text_block=None):
        self.text_block = text_block
        self.polygon_overlay = None


class _StubImageViewer:
    """Stub per ImageViewer."""
    def __init__(self, rectangles=None):
        self.rectangles = rectangles or []

    def get_selected_rectangles(self):
        return [r for r in self.rectangles if getattr(r, 'selected', False)]


class _ControllerHarness(PolygonInpaintMixin):
    """Harness che espone il mixin con le dipendenze minime."""
    
    def __init__(self, rectangles=None):
        self.image_viewer = _StubImageViewer(rectangles or [])
        self._schedule_save_current_image_state = MagicMock()


class TestPolygonInpaintToggle(unittest.TestCase):
    """Test per la commutazione poligono/rettangolo."""

    def _make_block(self, xyxy=None, polygon_points=None):
        """Crea un TextBlock con coordinate specifiche."""
        blk = TextBlock()
        if xyxy is not None:
            blk.xyxy = np.array(xyxy, dtype=np.int32)
        if polygon_points is not None:
            blk.polygon_points = np.array(polygon_points, dtype=np.int32)
            blk.segm_pts = blk.polygon_points
        blk.use_polygon_inpaint = True
        return blk

    def test_button_visible_but_disabled_without_selection(self):
        """Il pulsante deve restare visibile ma disabilitato senza selezione."""
        # Crea controller senza selezione
        controller = _ControllerHarness()
        button = MagicMock()
        controller.polygon_inpaint_button = button
        
        controller.refresh_polygon_inpaint_button_state()
        
        button.setVisible.assert_called_once_with(True)
        button.setEnabled.assert_called_once_with(False)

    def test_button_visible_with_selection(self):
        """Il pulsante deve essere visibile con caselle selezionate."""
        blk = self._make_block(xyxy=[10, 10, 100, 50])
        rect = _StubRectItem(blk)
        rect.selected = True
        
        controller = _ControllerHarness([rect])
        button = MagicMock()
        controller.polygon_inpaint_button = button
        
        controller.refresh_polygon_inpaint_button_state()
        
        button.setVisible.assert_called_once_with(True)
        button.setEnabled.assert_called_once_with(True)

    def test_convert_to_rectangle_mode(self):
        """La conversione in modalità rettangolo deve usare il bounding box."""
        # Poligono irregolare
        polygon = np.array([
            [10, 10],
            [90, 15],
            [85, 60],
            [15, 55],
        ], dtype=np.int32)
        
        blk = self._make_block(xyxy=[10, 10, 100, 60], polygon_points=polygon)
        rect = _StubRectItem(blk)
        rect.selected = True
        
        controller = _ControllerHarness([rect])
        
        # Converti in modalità rettangolo
        controller.toggle_polygon_inpaint_mode(False)
        
        # Verifica che il poligono sia ora un rettangolo
        expected_rect = np.array([
            [10, 10],
            [100, 10],
            [100, 60],
            [10, 60],
        ], dtype=np.int32)
        
        np.testing.assert_array_equal(blk.polygon_points, expected_rect)
        self.assertFalse(blk.use_polygon_inpaint)
        np.testing.assert_array_equal(blk.get_active_inpaint_polygon(), expected_rect)

    def test_restore_polygon_mode(self):
        """Il ripristino della modalità poligono deve recuperare l'originale."""
        # Poligono irregolare
        original_polygon = np.array([
            [10, 10],
            [90, 15],
            [85, 60],
            [15, 55],
        ], dtype=np.int32)
        
        blk = self._make_block(xyxy=[10, 10, 100, 60], polygon_points=original_polygon.copy())
        rect = _StubRectItem(blk)
        rect.selected = True
        
        controller = _ControllerHarness([rect])
        
        # Prima converti in rettangolo
        controller.toggle_polygon_inpaint_mode(False)
        
        # Poi ripristina poligono
        controller.toggle_polygon_inpaint_mode(True)
        
        # Verifica che il poligono originale sia ripristinato
        np.testing.assert_array_equal(blk.polygon_points, original_polygon)
        self.assertTrue(blk.use_polygon_inpaint)

    def test_toggle_applies_only_to_selected(self):
        """La commutazione deve applicarsi solo agli elementi selezionati."""
        # Crea due blocchi
        blk1 = self._make_block(
            xyxy=[10, 10, 100, 50],
            polygon_points=np.array([[10, 10], [100, 10], [100, 50], [10, 50]], dtype=np.int32)
        )
        blk2 = self._make_block(
            xyxy=[110, 10, 200, 50],
            polygon_points=np.array([[110, 10], [200, 10], [200, 50], [110, 50]], dtype=np.int32)
        )
        
        rect1 = _StubRectItem(blk1)
        rect1.selected = True
        rect2 = _StubRectItem(blk2)
        rect2.selected = False  # Non selezionato
        
        controller = _ControllerHarness([rect1, rect2])
        
        # Converti in modalità rettangolo
        controller.toggle_polygon_inpaint_mode(False)
        
        # Solo blk1 deve essere modificato
        self.assertFalse(blk1.use_polygon_inpaint)
        self.assertTrue(blk2.use_polygon_inpaint)  # Invariato

    def test_inpaint_bboxes_filtered_correctly_in_rectangle_mode(self):
        """In modalità rettangolo il filtro deve usare il rettangolo attivo, non il vecchio poligono."""
        blk = self._make_block(
            xyxy=[10, 10, 100, 60],
            polygon_points=np.array([[10, 10], [30, 10], [30, 30], [10, 30]], dtype=np.int32)
        )
        blk._all_inpaint_bboxes = np.array([
            [60, 20, 90, 40],  # Dentro il rettangolo attivo, fuori dal vecchio poligono
            [150, 150, 180, 180],  # Fuori
        ], dtype=np.int32)
        
        rect = _StubRectItem(blk)
        rect.selected = True
        
        controller = _ControllerHarness([rect])
        
        # Converti in modalità rettangolo
        controller.toggle_polygon_inpaint_mode(False)
        
        # Le bbox devono essere filtrate
        blk.filter_inpaint_bboxes()
        
        # Verifica che solo la bbox interna sia presente
        self.assertEqual(len(blk.inpaint_bboxes), 1)
        np.testing.assert_array_equal(blk.inpaint_bboxes[0], [60, 20, 90, 40])


if __name__ == '__main__':
    unittest.main()
