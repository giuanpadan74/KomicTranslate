"""py7zr deve essere opzionale: se la sua DLL nativa e' bloccata da una
policy di controllo applicazioni, l'import di archives non deve fallire
e solo l'uso del .7z deve dare errore chiaro (non tutto l'avvio)."""
import importlib.abc
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _BlockNative7z(importlib.abc.MetaPathFinder):
    """Simula la policy che blocca bcj._bcj (vedi log D:\\KomicTranslate)."""

    def find_spec(self, name, path=None, target=None):
        if name == "py7zr" or name.startswith(("py7zr.", "bcj", "bcj.")):
            raise ImportError(
                "DLL load failed while importing _bcj: Un criterio di "
                "controllo dell'applicazione ha bloccato il file.")
        return None


def _unload_archives():
    for mod in [m for m in list(sys.modules)
                if m == "modules.utils.archives"]:
        del sys.modules[mod]
    # l'import lascia anche l'attributo stale sul package parent
    parent = sys.modules.get("modules.utils")
    if parent is not None and getattr(parent, "archives", None) is not None:
        try:
            delattr(parent, "archives")
        except AttributeError:
            pass


class TestArchives7zOptional(unittest.TestCase):
    def _fresh_archives_blocked(self):
        blocker = _BlockNative7z()
        sys.meta_path.insert(0, blocker)
        try:
            _unload_archives()
            from modules.utils import archives
            return archives
        finally:
            sys.meta_path.remove(blocker)
            _unload_archives()

    def test_import_survives_blocked_dll(self):
        archives = self._fresh_archives_blocked()
        self.assertIsNone(archives.py7zr)
        self.assertIsInstance(archives._PY7ZR_ERROR, ImportError)

    def test_zip_still_works_without_py7zr(self):
        archives = self._fresh_archives_blocked()
        with tempfile.TemporaryDirectory() as tmp:
            zpath = os.path.join(tmp, "test.cbz")
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("001.jpg", b"fake-jpeg-bytes")
            out = os.path.join(tmp, "out")
            os.makedirs(out)
            got = archives.extract_archive(zpath, out)
            self.assertEqual(len(got), 1)
            self.assertTrue(got[0].endswith("001.jpg"))

    def test_7z_fails_with_clear_error(self):
        archives = self._fresh_archives_blocked()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError) as ctx:
                archives.extract_archive(os.path.join(tmp, "x.7z"), tmp)
            self.assertIn(".7z", str(ctx.exception))
            with self.assertRaises(RuntimeError):
                archives.make_cb7(tmp)

    def test_normal_import_has_py7zr(self):
        _unload_archives()
        from modules.utils import archives
        self.assertIsNotNone(archives.py7zr)


if __name__ == "__main__":
    unittest.main()
