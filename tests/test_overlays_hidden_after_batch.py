"""
Test di regressione per il fix: dopo la traduzione batch, navigando tra le
immagini gli overlay (rettangoli, text items, poligoni) NON devono essere
visibili sulle altre immagini.

Prima del fix:
- ``clear_rectangles_all_pages`` azzerava ``state['viewer_state']['rectangles']``
  ma non toccava ``state['viewer_state']['text_items_state']``: al cambio
  pagina, ``load_image_state`` ricostruiva i text items nella scena, che
  risultavano visibili a schermo.
- I rettangoli aggiunti manualmente dopo il batch non venivano nascosti.

Dopo il fix:
- ``clear_rectangles_all_pages`` imposta anche
  ``state['viewer_state']['overlays_hidden'] = True``.
- ``load_image_state`` legge questo flag e passa ``show_overlays=False`` a
  ``image_viewer.load_state`` e ai text items ricreati manualmente.
- ``image_viewer.load_state(state, show_overlays=False)`` chiama
  ``setVisible(False)`` su tutti i rettangoli e text items appena caricati.
- Il flag viene resettato quando l'utente ripristina le caselle
  (es. tramite l'azione “draw_blklist_blks”, che richiama ``show_boxes_overlays``).
"""
from pathlib import Path
import os
import unittest

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
PROGRESS_TRACKING = os.path.join(
    PROJECT_ROOT, 'app', 'controllers', 'batch_controller',
    'progress_tracking.py',
)
PROJECT_CONTROLLER = os.path.join(
    PROJECT_ROOT, 'app', 'controllers', 'project_controller.py',
)
IMAGE_VIEWER = os.path.join(
    PROJECT_ROOT, 'app', 'ui', 'canvas', 'image_viewer.py',
)


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class TestClearRectanglesSetsOverlaysHidden(unittest.TestCase):
    """Il fix: clear_rectangles_all_pages deve impostare overlays_hidden=True."""

    def _get_function_body(self):
        source = _read(PROGRESS_TRACKING)
        start = source.find("def clear_rectangles_all_pages")
        self.assertGreater(start, -1, "Funzione non trovata")
        end = source.find("\n    def ", start + 1)
        if end == -1:
            end = len(source)
        return source[start:end]

    def test_sets_overlays_hidden_flag(self):
        body = self._get_function_body()
        # Il fix deve aver aggiunto l'impostazione del flag overlays_hidden
        # su tutti gli image_states, per indicare a load_image_state che
        # gli overlay (rettangoli, text items) devono restare nascosti
        # al cambio pagina.
        self.assertIn(
            "overlays_hidden",
            body,
            "clear_rectangles_all_pages deve impostare 'overlays_hidden' "
            "per garantire che gli overlay non siano visibili al cambio "
            "pagina dopo la traduzione batch."
        )
        self.assertIn("= True", body)


class TestLoadImageStateRespectsOverlaysHidden(unittest.TestCase):
    """Il fix: load_image_state legge il flag e nasconde gli overlay."""

    def test_load_image_state_signature_has_show_overlays(self):
        source = _read(PROJECT_CONTROLLER)
        # La firma deve accettare un parametro show_overlays
        self.assertRegex(
            source,
            r"def\s+load_image_state\s*\([^)]*show_overlays[^)]*\)",
            "load_image_state deve accettare un parametro show_overlays"
        )

    def test_load_image_state_reads_overlays_hidden(self):
        source = _read(PROJECT_CONTROLLER)
        # Deve leggere il flag overlays_hidden dallo state e forzare
        # show_overlays=False
        self.assertIn("overlays_hidden", source)
        # Deve passare show_overlays a image_viewer.load_state
        self.assertIn("show_overlays=show_overlays", source)
    
    def test_show_boxes_overlays_clears_flag(self):
        source = _read(os.path.join(
            PROJECT_ROOT, 'app', 'controllers', 'ui_controller.py'
        ))
        self.assertIn("def show_boxes_overlays", source)
        self.assertIn("overlays_hidden", source)


class TestImageViewerLoadStateHidesOverlays(unittest.TestCase):
    """Il fix: image_viewer.load_state deve nascondere gli overlay se richiesto."""

    def test_load_state_accepts_show_overlays(self):
        source = _read(IMAGE_VIEWER)
        self.assertRegex(
            source,
            r"def\s+load_state\s*\([^)]*show_overlays[^)]*\)",
            "image_viewer.load_state deve accettare un parametro show_overlays"
        )

    def test_load_state_hides_overlays_when_false(self):
        source = _read(IMAGE_VIEWER)
        # Quando show_overlays=False, deve chiamare setVisible(False)
        # su rettangoli e text items caricati.
        self.assertIn("setVisible(False)", source,
                      "image_viewer.load_state deve chiamare setVisible(False) "
                      "per nascondere gli overlay")


if __name__ == "__main__":
    unittest.main(verbosity=2)
