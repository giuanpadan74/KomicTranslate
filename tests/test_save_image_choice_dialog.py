"""
Test di regressione per il fix del dialog "Salva Immagine".

Prima del fix:
- Il flag di default era su "Salva pagina corrente" invece di
  "Salva tutte le pagine", e l'utente non riusciva a flaggare
  correttamente l'altra opzione.
- La presenza contemporanea di ``setAutoExclusive(True)`` sui singoli
  radio e di un ``QButtonGroup.setExclusive(True)`` esplicito creava
  conflitti che impedivano la commutazione visiva del flag.

Dopo il fix:
- ``setAutoExclusive(True)`` rimosso dai singoli radio (il QButtonGroup
  gestisce già l'esclusività).
- ``setFocusPolicy(Qt.StrongFocus)`` rimosso per non bloccare i click.
- ``_apply_default_selection()`` azzera PRIMA entrambi i radio e poi
  imposta ``radio_all`` checked, per evitare il bug di stato Qt
  iniziale.
- ``_on_radio_toggled`` traccia l'ultima selezione utente in modo
  esplicito.
- ``on_confirm`` usa l'ultima selezione tracciata come fallback robusto.
- ``showEvent`` ri-applica il default se l'utente non ha toccato nulla.

I test usano un ``QApplication`` reale (richiesto da Qt) e operano via
chiamate dirette ai metodi del dialog, senza event loop, per restare
veloci e deterministici.
"""
from pathlib import Path
import os
import sys
import unittest

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestSaveImageChoiceDialogDefault(unittest.TestCase):
    """Verifica il default e la commutazione dei radio button."""

    @classmethod
    def setUpClass(cls):
        # Crea un QApplication una sola volta per tutti i test
        from PySide6 import QtWidgets
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from app.ui.save_image_choice_dialog import SaveImageChoiceDialog
        self.dialog = SaveImageChoiceDialog(page_count=2, parent=None)

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()

    def test_default_is_radio_all(self):
        """Di default 'Salva tutte le pagine' deve essere flaggato."""
        self.assertTrue(
            self.dialog.radio_all.isChecked(),
            "Di default 'Salva tutte le pagine' (radio_all) deve essere flaggato"
        )

    def test_default_is_not_radio_current(self):
        """Di default 'Salva pagina corrente' NON deve essere flaggato."""
        self.assertFalse(
            self.dialog.radio_current.isChecked(),
            "Di default 'Salva pagina corrente' (radio_current) NON deve essere flaggato"
        )

    def test_only_one_radio_checked(self):
        """Solo un radio deve essere checked (esclusività del QButtonGroup)."""
        all_checked = self.dialog.radio_all.isChecked()
        current_checked = self.dialog.radio_current.isChecked()
        self.assertNotEqual(
            all_checked, current_checked,
            "Esattamente uno dei due radio deve essere checked"
        )

    def test_user_can_switch_to_radio_current(self):
        """L'utente deve poter cliccare e attivare radio_current."""
        # Simula il click dell'utente
        self.dialog.radio_current.setChecked(True)
        self.assertTrue(self.dialog.radio_current.isChecked())
        self.assertFalse(self.dialog.radio_all.isChecked())

    def test_user_can_switch_back_to_radio_all(self):
        """Dopo aver cliccato radio_current, l'utente deve poter tornare a radio_all."""
        self.dialog.radio_current.setChecked(True)
        self.assertTrue(self.dialog.radio_current.isChecked())

        # L'utente clicca di nuovo su radio_all
        self.dialog.radio_all.setChecked(True)
        self.assertTrue(self.dialog.radio_all.isChecked())
        self.assertFalse(self.dialog.radio_current.isChecked())

    def test_user_selection_tracked(self):
        """L'ultima selezione utente deve essere tracciata in _user_selection."""
        self.assertEqual(self.dialog._user_selection, "all")

        # Simula click su radio_current
        self.dialog.radio_current.setChecked(True)
        self.assertEqual(self.dialog._user_selection, "current")

        # Torna a radio_all
        self.dialog.radio_all.setChecked(True)
        self.assertEqual(self.dialog._user_selection, "all")

    def test_on_confirm_default_returns_all(self):
        """Se l'utente non tocca nulla e clicca Conferma, deve salvare 'all'."""
        self.dialog.on_confirm()
        self.assertEqual(self.dialog.choice, "all")

    def test_on_confirm_after_user_picks_current(self):
        """Se l'utente seleziona 'current' e clicca Conferma, deve salvare 'current'."""
        self.dialog.radio_current.setChecked(True)
        self.dialog.on_confirm()
        self.assertEqual(self.dialog.choice, "current")

    def test_on_confirm_after_user_picks_all(self):
        """Se l'utente seleziona esplicitamente 'all' e clicca Conferma, deve salvare 'all'."""
        self.dialog.radio_current.setChecked(True)  # cambio
        self.dialog.radio_all.setChecked(True)  # e poi torno ad all
        self.dialog.on_confirm()
        self.assertEqual(self.dialog.choice, "all")

    def test_no_set_auto_exclusive_on_radio_buttons(self):
        """I radio NON devono avere setAutoExclusive(True) per evitare conflitti col QButtonGroup."""
        # Verifica a livello di codice sorgente per garantire che il bug
        # non venga reintrodotto da regressioni future. Si considera solo
        # il codice "attivo" (escludendo le righe di commento che iniziano
        # con '#').
        path = os.path.join(PROJECT_ROOT, 'app', 'ui', 'save_image_choice_dialog.py')
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue  # Ignora i commenti
            self.assertNotIn(
                "setAutoExclusive(True)",
                line,
                f"setAutoExclusive(True) trovato alla riga {i} "
                f"(codice attivo): causa conflitti con il QButtonGroup "
                f"esplicito e può rendere i radio 'non flaggabili' visivamente. "
                f"Riga: {line.rstrip()}"
            )

    def test_no_strong_focus_on_radio_buttons(self):
        """I radio NON devono avere setFocusPolicy(StrongFocus) per non bloccare i click."""
        path = os.path.join(PROJECT_ROOT, 'app', 'ui', 'save_image_choice_dialog.py')
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue
            self.assertNotIn(
                "setFocusPolicy(Qt.StrongFocus)",
                line,
                f"setFocusPolicy(Qt.StrongFocus) trovato alla riga {i}: "
                f"può bloccare i click sui radio button su alcuni temi "
                f"Qt / Windows. Riga: {line.rstrip()}"
            )

    def test_apply_default_resets_both_first(self):
        """_apply_default_selection deve azzerare PRIMA entrambi i radio."""
        # Parti da uno stato "sporco": radio_current checked
        self.dialog.radio_current.setChecked(True)
        # Applica il default
        self.dialog._apply_default_selection()
        # Deve essere tornato a radio_all
        self.assertTrue(self.dialog.radio_all.isChecked())
        self.assertFalse(self.dialog.radio_current.isChecked())


if __name__ == "__main__":
    unittest.main(verbosity=2)
