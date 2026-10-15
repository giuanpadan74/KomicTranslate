import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestInstallerPhase1Paths(unittest.TestCase):
    def test_log_dir_in_appdata(self):
        from modules.utils.paths import get_log_dir, get_app_data_dir
        log_dir = get_log_dir(create=False)
        app_data = get_app_data_dir()
        self.assertTrue(log_dir.startswith(app_data))
        self.assertTrue(log_dir.endswith('logs'))
        # Non deve piu' puntare alla cartella install/sorgenti
        self.assertNotEqual(
            os.path.normcase(os.path.abspath(log_dir)),
            os.path.normcase(os.path.abspath('logs')),
        )

    def test_model_path_strips_prefix_and_dev_base(self):
        from modules.utils.paths import get_model_path, get_models_base_dir
        base = get_models_base_dir()
        self.assertTrue(base.endswith('models'))
        a = get_model_path('models/detection/x.pt')
        b = get_model_path('detection/x.pt')
        self.assertEqual(a, b)
        self.assertTrue(a.startswith(base))

    def test_models_base_installed_goes_to_appdata(self):
        from modules.utils import paths
        orig = paths.is_installed_environment
        try:
            paths.is_installed_environment = lambda: True
            base = paths.get_models_base_dir()
            self.assertIn('KomicTranslate', base)
            self.assertTrue(base.endswith('models'))
            # Non deve essere sotto Program Files (non scrivibile)
            self.assertNotIn('Program Files', base)
        finally:
            paths.is_installed_environment = orig

    def test_resource_path_dev(self):
        from modules.utils.paths import resource_path
        p = resource_path(os.path.join('assets', 'icons'))
        self.assertTrue(os.path.isdir(p))

    def test_bootstrap_gated_with_env(self):
        from modules.utils.paths import is_bootstrap_gated
        old = os.environ.get('KOMIC_TRANSLATE_INSTALLED')
        os.environ['KOMIC_TRANSLATE_INSTALLED'] = '1'
        try:
            self.assertTrue(is_bootstrap_gated())
        finally:
            if old is None:
                del os.environ['KOMIC_TRANSLATE_INSTALLED']
            else:
                os.environ['KOMIC_TRANSLATE_INSTALLED'] = old

    def test_bootstrap_run_refuses_when_gated(self):
        old = os.environ.get('KOMIC_TRANSLATE_INSTALLED')
        os.environ['KOMIC_TRANSLATE_INSTALLED'] = '1'
        try:
            import bootstrap
            self.assertFalse(bootstrap.run_bootstrap())
        finally:
            if old is None:
                del os.environ['KOMIC_TRANSLATE_INSTALLED']
            else:
                os.environ['KOMIC_TRANSLATE_INSTALLED'] = old

    def test_comic_setup_logging_uses_appdata(self):
        import comic
        logger = comic.setup_logging()
        self.assertIsNotNone(logger)
        import logging
        files = [
            getattr(h, 'baseFilename', '')
            for h in logging.getLogger().handlers
        ]
        self.assertTrue(any('KomicTranslate' in f and 'logs' in f for f in files))


if __name__ == '__main__':
    unittest.main()
