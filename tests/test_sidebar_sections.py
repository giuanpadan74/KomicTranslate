import os
import unittest

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.dayu_widgets.collapse import MSectionItem
from app.ui.operativa_layout_controller import SETTINGS_GROUP
from app.ui.sidebar_dock_title_bar import SidebarDockTitleBar
from app.ui.sidebar_sections import (
    SETTINGS_KEY_SIDEBAR_SECTION_ORDER,
    SidebarSectionsWidget,
)


class TestSidebarSectionsWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = QSettings("ComicLabsTest", "KomicTranslateSectionsTest")
        self.settings.beginGroup(SETTINGS_GROUP)
        self.settings.remove("")
        self.settings.endGroup()

    def _make_container(self):
        widget = SidebarSectionsWidget(self.settings)
        for section_key in ("text", "font", "selection"):
            section = MSectionItem(
                title=section_key,
                expand=True,
                widget=QLabel(section_key),
            )
            widget.add_section(section_key, section)
        return widget

    def test_move_section_persists_order(self):
        widget = self._make_container()
        widget.move_section("selection", 0)

        self.assertEqual(widget.ordered_keys(), ["selection", "text", "font"])

        self.settings.beginGroup(SETTINGS_GROUP)
        try:
            stored = self.settings.value(SETTINGS_KEY_SIDEBAR_SECTION_ORDER, [])
        finally:
            self.settings.endGroup()
        self.assertEqual(list(stored), ["selection", "text", "font"])

    def test_restore_order_appends_new_sections(self):
        self.settings.beginGroup(SETTINGS_GROUP)
        self.settings.setValue(
            SETTINGS_KEY_SIDEBAR_SECTION_ORDER,
            ["selection", "text"],
        )
        self.settings.endGroup()

        widget = self._make_container()
        widget.restore_order()

        self.assertEqual(widget.ordered_keys(), ["selection", "text", "font"])


class TestSidebarDockTitleBar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_layout_button_reflects_operativa_state(self):
        title_bar = SidebarDockTitleBar("Barra Laterale")

        title_bar.set_operativa_in_sidebar(True)
        self.assertTrue(title_bar.layout_button.isChecked())
        self.assertIn("barra laterale", title_bar.layout_button.toolTip().lower())

        title_bar.set_operativa_in_sidebar(False)
        self.assertFalse(title_bar.layout_button.isChecked())
        self.assertIn("barra superiore", title_bar.layout_button.toolTip().lower())


if __name__ == "__main__":
    unittest.main()
