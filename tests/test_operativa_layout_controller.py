import os
import unittest

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.operativa_layout_controller import (
    OperativaLayoutController,
    SETTINGS_GROUP,
    SETTINGS_KEY_HEADER_IN_SIDEBAR,
)


class TestOperativaLayoutController(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = QSettings("ComicLabsTest", "KomicTranslateTest")
        self.settings.beginGroup(SETTINGS_GROUP)
        self.settings.remove("")
        self.settings.endGroup()

        self.header_toolbar = QWidget()
        self.header_host = QWidget()
        self.header_host_layout = QVBoxLayout(self.header_host)
        self.header_host_layout.setContentsMargins(0, 0, 0, 0)
        self.header_host_layout.addWidget(self.header_toolbar)

        self.sidebar_host = QWidget()
        self.sidebar_host_layout = QVBoxLayout(self.sidebar_host)
        self.sidebar_host_layout.setContentsMargins(0, 0, 0, 0)

        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)

        self.controller = OperativaLayoutController(
            settings=self.settings,
            header_toolbar_widget=self.header_toolbar,
            header_host_widget=self.header_host,
            header_host_layout=self.header_host_layout,
            sidebar_host_widget=self.sidebar_host,
            sidebar_host_layout=self.sidebar_host_layout,
            toggle_button=self.toggle_button,
        )

    def test_apply_moves_toolbar_and_persists(self):
        self.controller.apply(True)
        self.assertIs(self.header_toolbar.parentWidget(), self.sidebar_host)
        self.assertFalse(self.header_host.isVisible())
        self.assertTrue(self.sidebar_host.isVisible())

        self.settings.beginGroup(SETTINGS_GROUP)
        try:
            self.assertTrue(self.settings.value(SETTINGS_KEY_HEADER_IN_SIDEBAR, False, type=bool))
        finally:
            self.settings.endGroup()

        self.controller.apply(False)
        self.assertIs(self.header_toolbar.parentWidget(), self.header_host)
        self.assertTrue(self.header_host.isVisible())
        self.assertFalse(self.sidebar_host.isVisible())


if __name__ == "__main__":
    unittest.main()
