"""
Test di regressione: verifica che ``clear_rectangles_all_pages`` NON azzeri
più ``image_states[image_path]['blk_list']``.

Prima del fix, la funzione impostava esplicitamente
``state['blk_list'] = []`` per ogni immagine. Questo causava la perdita dei
blocchi tradotti dalla pipeline batch: al termine del batch, quando
``on_batch_process_finished`` provava a rileggere
``image_states[current_image]['blk_list']``, trovava una lista vuota, e le
caselle source/target restavano vuote.

Il test controlla il sorgente della funzione per garantire che l'azzeramento
non venga reintrodotto da regressioni future, e che continui invece ad
azzerare solo i rettangoli (``viewer_state['rectangles']``).
"""
from pathlib import Path
import os
import unittest

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
PROGRESS_TRACKING = os.path.join(
    PROJECT_ROOT, 'app', 'controllers', 'batch_controller',
    'progress_tracking.py',
)


class TestClearRectanglesRegression(unittest.TestCase):
    """Garantisce che clear_rectangles_all_pages preservi blk_list."""

    def _get_function_body(self):
        with open(PROGRESS_TRACKING, 'r', encoding='utf-8') as f:
            source = f.read()
        start = source.find("def clear_rectangles_all_pages")
        self.assertGreater(start, -1, "Funzione non trovata")
        end = source.find("\n    def ", start + 1)
        if end == -1:
            end = len(source)
        return source[start:end]

    def test_does_not_reset_state_blk_list(self):
        body = self._get_function_body()
        # L'azzeramento esplicito di state['blk_list'] è stato rimosso dal
        # fix: NON deve essere reintrodotto.
        self.assertNotIn(
            "state['blk_list'] = []",
            body,
            "clear_rectangles_all_pages NON deve azzerare state['blk_list']: "
            "questo causa la perdita dei blocchi tradotti e quindi il mancato "
            "popolamento delle caselle source/target in caso di più immagini."
        )

    def test_does_not_reset_self_blk_list(self):
        body = self._get_function_body()
        # Anche self.blk_list NON deve essere azzerato: serve per ripopolare
        # le caselle source/target al termine del batch tramite
        # _refresh_text_edits_for_current_block.
        self.assertNotIn(
            "self.blk_list = []",
            body,
            "clear_rectangles_all_pages NON deve azzerare self.blk_list: "
            "è necessario per il refresh delle caselle source/target."
        )

    def test_does_still_reset_rectangles(self):
        body = self._get_function_body()
        # Deve continuare ad azzerare i rettangoli del viewer_state.
        self.assertIn("'rectangles'] = []", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
