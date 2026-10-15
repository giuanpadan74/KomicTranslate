"""
Test di regressione per il fix del popolamento delle caselle source/target
quando si traducono più immagini in batch.

Riproduce il bug originale: con N > 1 immagini aperte, al termine della
traduzione batch le caselle ``s_text_edit`` e ``t_text_edit`` restavano
vuote. Con singola immagine il problema non si manifestava perché
``self.curr_tblock`` rimaneva valido dopo la traduzione.

I test coprono la logica di selezione deterministica introdotta in
``_refresh_text_edits_for_current_block`` simulando le strutture dati
minime (blk_list con TextBlock, mock delle QTextEdit) senza richiedere
un QApplication reale.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.controllers.text_edits_sync import refresh_text_edits_for_current_block


class _StubTextEdit:
    """Sostituto minimo di QTextEdit per i test offline."""

    def __init__(self, text=""):
        self._text = text
        self._signals_blocked = False
        self.set_calls = []
        self.clear_calls = 0
        self.blockSignals_calls = 0

    def toPlainText(self):
        return self._text

    def setPlainText(self, text):
        kind = "blocked" if self._signals_blocked else "normal"
        self.set_calls.append((kind, text))
        self._text = text

    def clear(self):
        self._text = ""
        self.clear_calls += 1

    def blockSignals(self, block):
        self._signals_blocked = bool(block)
        self.blockSignals_calls += 1


class _ControllerHarness:
    """Harness minimo che espone l'API usata da _refresh_text_edits_for_current_block."""

    def __init__(self, blk_list, curr_tblock=None):
        self.blk_list = blk_list
        self.curr_tblock = curr_tblock
        self.curr_tblock_item = None
        self.s_text_edit = _StubTextEdit()
        self.t_text_edit = _StubTextEdit()
        self.refresh_polygon_text_button_state = MagicMock()

    def _refresh_text_edits_for_current_block(self):
        refresh_text_edits_for_current_block(self)


def _make_block(text="", translation=""):
    from modules.utils.textblock import TextBlock
    blk = TextBlock()
    blk.text = text
    blk.translation = translation
    blk.xyxy = [0, 0, 100, 30]
    return blk


class TestRefreshTextEditsCurrBlock(unittest.TestCase):
    """Verifica la logica di _refresh_text_edits_for_current_block."""

    def test_curr_tblock_preserved_when_in_list(self):
        blk_a = _make_block("Ciao", "Hello")
        blk_b = _make_block("Mondo", "World")
        h = _ControllerHarness([blk_a, blk_b], curr_tblock=blk_a)
        h._refresh_text_edits_for_current_block()
        self.assertEqual(h.s_text_edit.toPlainText(), "Ciao")
        self.assertEqual(h.t_text_edit.toPlainText(), "Hello")
        self.assertIs(h.curr_tblock, blk_a)

    def test_first_translated_block_used_when_curr_is_none(self):
        blk_empty = _make_block("Foo", "")
        blk_translated = _make_block("Bar", "Tradotto")
        h = _ControllerHarness([blk_empty, blk_translated], curr_tblock=None)
        h._refresh_text_edits_for_current_block()
        self.assertEqual(h.s_text_edit.toPlainText(), "Bar")
        self.assertEqual(h.t_text_edit.toPlainText(), "Tradotto")
        self.assertIs(h.curr_tblock, blk_translated)

    def test_fallback_to_first_block_when_no_translation(self):
        blk_a = _make_block("Primo", "")
        blk_b = _make_block("Secondo", "")
        h = _ControllerHarness([blk_a, blk_b], curr_tblock=None)
        h._refresh_text_edits_for_current_block()
        self.assertEqual(h.s_text_edit.toPlainText(), "Primo")
        self.assertEqual(h.t_text_edit.toPlainText(), "")
        self.assertIs(h.curr_tblock, blk_a)

    def test_empty_blocklist_clears_edits(self):
        h = _ControllerHarness([], curr_tblock=None)
        h.s_text_edit.setPlainText("vecchio")
        h.t_text_edit.setPlainText("vecchio tradotto")
        h._refresh_text_edits_for_current_block()
        self.assertEqual(h.s_text_edit.toPlainText(), "")
        self.assertEqual(h.t_text_edit.toPlainText(), "")
        self.assertIsNone(h.curr_tblock)

    def test_signals_blocked_during_refresh(self):
        blk = _make_block("X", "Y")
        h = _ControllerHarness([blk], curr_tblock=blk)
        h._refresh_text_edits_for_current_block()
        self.assertGreaterEqual(h.s_text_edit.blockSignals_calls, 2)
        self.assertGreaterEqual(h.t_text_edit.blockSignals_calls, 2)
        for kind, _ in h.s_text_edit.set_calls:
            self.assertEqual(kind, "blocked")
        for kind, _ in h.t_text_edit.set_calls:
            self.assertEqual(kind, "blocked")

    def test_stale_curr_tblock_replaced(self):
        stale = _make_block("Stale", "")
        fresh = _make_block("Fresh", "Tradotto")
        h = _ControllerHarness([fresh], curr_tblock=stale)
        h._refresh_text_edits_for_current_block()
        self.assertEqual(h.s_text_edit.toPlainText(), "Fresh")
        self.assertEqual(h.t_text_edit.toPlainText(), "Tradotto")
        self.assertIs(h.curr_tblock, fresh)

    def test_multi_image_scenario(self):
        """Scenario del bug originale: blk_list con più blocchi tradotti,
        nessun curr_tblock (simula reset post batch)."""
        blocks = [
            _make_block("Pagina 1 - Blocco 1", "Page 1 - Block 1"),
            _make_block("Pagina 1 - Blocco 2", "Page 1 - Block 2"),
            _make_block("Pagina 1 - Blocco 3", ""),
        ]
        h = _ControllerHarness(blocks, curr_tblock=None)
        h._refresh_text_edits_for_current_block()
        self.assertEqual(h.s_text_edit.toPlainText(), "Pagina 1 - Blocco 1")
        self.assertEqual(h.t_text_edit.toPlainText(), "Page 1 - Block 1")
        self.assertIs(h.curr_tblock, blocks[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
