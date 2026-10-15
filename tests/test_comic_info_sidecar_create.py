"""
Test: Scheda Fumetto - su OK il ComicInfo.xml viene creato nella cartella
dell'ultima immagine caricata se non esiste (e aggiornato se esiste).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import types

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6 import QtWidgets

import app.ui.comic_info_dialog as dlg_module
from app.controllers import comic_info_controller as cic

class _FakeDialog:
    """Sostituto del ComicInfoDialog: simula OK con dati fissi."""
    seen = {}

    def __init__(self, base, existing, parent=None):
        _FakeDialog.seen["base"] = base
        _FakeDialog.seen["existing"] = existing
        self._result = {"Series": "Celestia", "Writer": "Manuele Fior"}

    def exec(self):
        return QtWidgets.QDialog.DialogCode.Accepted

    def result(self):
        return dict(self._result)


class _FakeSettings:
    def __init__(self, *a, **k):
        pass

    def beginGroup(self, *a, **k):
        pass

    def endGroup(self, *a, **k):
        pass

    def setValue(self, *a, **k):
        pass


class _Handler:
    def __init__(self, archive_info=None):
        self.archive_info = archive_info or []


class _Controller:
    def __init__(self, image_files, archive_info=None):
        self.image_files = image_files
        self.curr_img_idx = 0
        self.project_file = None
        self.file_handler = _Handler(archive_info)
        self.comic_info = {}
        self.t_combo = None


def _make_image(directory, name="p01.jpg"):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(b"\x00")
    return path


class TestComicInfoSidecarCreate(unittest.TestCase):
    def setUp(self):
        _FakeDialog.seen.clear()
        # Simula la scelta della cartella su OK: di default conferma la
        # cartella proposta; i singoli test possono impostare
        # self.chosen_dir (o "" per simulare Annulla).
        self.chosen_dir = None
        self.captured_start = None

        def _fake_get_dir(parent, title, start):
            self.captured_start = start
            return self.chosen_dir if self.chosen_dir is not None else start

        fake_widgets = types.SimpleNamespace(
            QDialog=QtWidgets.QDialog,
            QFileDialog=types.SimpleNamespace(getExistingDirectory=_fake_get_dir),
            QMessageBox=types.SimpleNamespace(
                warning=lambda *a, **k: None,
                information=lambda *a, **k: None,
            ),
        )
        self._patches = [
            patch.object(dlg_module, "ComicInfoDialog", _FakeDialog),
            patch.object(cic, "QSettings", _FakeSettings),
            patch.object(cic, "QtWidgets", fake_widgets),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_ok_creates_missing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _make_image(tmp)
            ctrl = _Controller([img])
            target = os.path.join(tmp, "ComicInfo.xml")
            self.assertFalse(os.path.exists(target))
            out = cic.open_comic_info_dialog(ctrl)
            self.assertIsNotNone(out)
            self.assertTrue(os.path.isfile(target), "ComicInfo.xml non creato")
            with open(target, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Celestia", content)
            self.assertEqual(ctrl.comic_info.get("Series"), "Celestia")

    def test_ok_uses_last_image_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_a = os.path.join(tmp, "A")
            dir_b = os.path.join(tmp, "B")
            img_a = _make_image(dir_a, "a.jpg")
            img_b = _make_image(dir_b, "b.jpg")
            ctrl = _Controller([img_a, img_b])
            ctrl.curr_img_idx = 0  # immagine corrente in A, ultima in B
            cic.open_comic_info_dialog(ctrl)
            # La cartella proposta e' quella dell'ultima immagine (B)
            self.assertEqual(os.path.normcase(os.path.abspath(self.captured_start)),
                             os.path.normcase(os.path.abspath(dir_b)))
            self.assertTrue(os.path.isfile(os.path.join(dir_b, "ComicInfo.xml")))
            self.assertFalse(os.path.exists(os.path.join(dir_a, "ComicInfo.xml")))

    def test_ok_user_picks_other_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_dir = os.path.join(tmp, "img")
            dest_dir = os.path.join(tmp, "dest")
            os.makedirs(dest_dir, exist_ok=True)
            img = _make_image(img_dir, "a.jpg")
            self.chosen_dir = dest_dir  # l'utente sceglie un'altra cartella
            ctrl = _Controller([img])
            cic.open_comic_info_dialog(ctrl)
            self.assertTrue(os.path.isfile(os.path.join(dest_dir, "ComicInfo.xml")))
            self.assertFalse(os.path.exists(os.path.join(img_dir, "ComicInfo.xml")))

    def test_ok_cancel_folder_keeps_memory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _make_image(tmp)
            self.chosen_dir = ""  # l'utente annulla la scelta cartella
            ctrl = _Controller([img])
            out = cic.open_comic_info_dialog(ctrl)
            self.assertIsNotNone(out)
            self.assertEqual(ctrl.comic_info.get("Series"), "Celestia")
            self.assertFalse(os.path.exists(os.path.join(tmp, "ComicInfo.xml")))

    def test_ok_updates_existing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _make_image(tmp)
            target = os.path.join(tmp, "ComicInfo.xml")
            with open(target, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" ?><ComicInfo><Series>Vecchia</Series></ComicInfo>')
            ctrl = _Controller([img])
            cic.open_comic_info_dialog(ctrl)
            # Nessun duplicato, contenuto aggiornato
            matches = [n for n in os.listdir(tmp) if n.lower() == "comicinfo.xml"]
            self.assertEqual(len(matches), 1)
            with open(target, encoding="utf-8") as f:
                self.assertIn("Celestia", f.read())
            # Il dialog ha ricevuto la scheda esistente
            self.assertEqual(_FakeDialog.seen["existing"].get("Series"), "Vecchia")

    def test_ok_reads_lowercase_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _make_image(tmp)
            lower = os.path.join(tmp, "comicinfo.xml")
            with open(lower, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" ?><ComicInfo><Series>Minuscola</Series></ComicInfo>')
            ctrl = _Controller([img])
            cic.open_comic_info_dialog(ctrl)
            matches = [n for n in os.listdir(tmp) if n.lower() == "comicinfo.xml"]
            self.assertEqual(len(matches), 1, f"duplicato sidecar: {matches}")
            self.assertEqual(_FakeDialog.seen["existing"].get("Series"), "Minuscola")

    def test_archive_images_use_archive_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            arch_dir = os.path.join(tmp, "fumetto")
            extract_dir = os.path.join(tmp, "fumetto", "tmp123")
            os.makedirs(extract_dir, exist_ok=True)
            extracted = os.path.join(extract_dir, "page01.jpg")
            with open(extracted, "wb") as f:
                f.write(b"\x00")
            archive_path = os.path.join(arch_dir, "fumetto.cbz")
            with open(archive_path, "wb") as f:
                f.write(b"\x00")
            ctrl = _Controller(
                [extracted],
                archive_info=[{"archive_path": archive_path,
                               "extracted_images": [extracted],
                               "temp_dir": extract_dir}],
            )
            cic.open_comic_info_dialog(ctrl)
            self.assertTrue(os.path.isfile(os.path.join(arch_dir, "ComicInfo.xml")))
            self.assertFalse(
                os.path.exists(os.path.join(extract_dir, "ComicInfo.xml")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
