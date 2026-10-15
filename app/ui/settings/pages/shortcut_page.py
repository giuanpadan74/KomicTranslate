from PySide6 import QtWidgets

from ...dayu_widgets.divider import MDivider
from ...dayu_widgets.label import MLabel
from ...dayu_widgets.line_edit import MLineEdit
from ...dayu_widgets.push_button import MPushButton
from ...dayu_widgets.message import MMessage
from ..shortcut_manager import SHORTCUT_GROUPS
from ..widgets.shortcut_edit import ShortcutEditWidget


class ShortcutPage:
    def _sync_shortcut_inputs(self, *keys: str) -> None:
        for key in keys:
            edit = self.shortcut_inputs.get(key)
            manager = self.parent().shortcut_manager if hasattr(self.parent(), 'shortcut_manager') else None
            if edit is None or manager is None:
                continue
            text = manager.get(key)
            if edit.text() == text:
                continue
            edit.blockSignals(True)
            edit.setText(text)
            edit.blockSignals(False)

    def _on_shortcut_changed(self, key: str, text: str) -> None:
        manager = self.parent().shortcut_manager if hasattr(self.parent(), 'shortcut_manager') else None
        if manager is None:
            return
        manager.set(key, text)
        self._sync_shortcut_inputs(key, "delete_box", "delete_shape")

    def _create_shortcut_widget(self) -> QtWidgets.QWidget:
        shortcut_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(shortcut_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        header_layout = QtWidgets.QHBoxLayout()
        self.shortcut_search = MLineEdit().small()
        self.shortcut_search.setPlaceholderText(self.tr("Cerca scorciatoia..."))
        self.shortcut_search.set_prefix_widget(QtWidgets.QLabel("🔍"))

        save_btn = MPushButton(self.tr("Salva")).small()
        save_btn.clicked.connect(self._save_shortcuts)

        reset_all_btn = MPushButton(self.tr("Ripristina tutti")).small()
        reset_all_btn.clicked.connect(self._reset_all_shortcuts)

        header_layout.addWidget(self.shortcut_search, 1)
        header_layout.addWidget(save_btn)
        header_layout.addWidget(reset_all_btn)
        layout.addLayout(header_layout)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QtWidgets.QWidget()
        self.shortcut_scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        self.shortcut_scroll_layout.setContentsMargins(0, 0, 10, 0)
        self.shortcut_scroll_layout.setSpacing(15)

        self.shortcut_inputs = {}
        self.shortcut_sections = []

        for group_name, keys in SHORTCUT_GROUPS.items():
            section_widget = QtWidgets.QWidget()
            section_layout = QtWidgets.QVBoxLayout(section_widget)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(8)

            title = MLabel(self.tr(group_name)).h4()
            section_layout.addWidget(title)

            group_items = []
            for key in keys:
                item_widget = QtWidgets.QWidget()
                item_layout = QtWidgets.QHBoxLayout(item_widget)
                item_layout.setContentsMargins(10, 0, 0, 0)

                label = MLabel(key).secondary()
                label.setFixedWidth(180)

                edit = ShortcutEditWidget()
                manager = self.parent().shortcut_manager if hasattr(self.parent(), 'shortcut_manager') else None
                if manager:
                    edit.setText(manager.get(key))
                    edit.shortcutChanged.connect(lambda text, k=key: self._on_shortcut_changed(k, text))

                self.shortcut_inputs[key] = edit

                item_layout.addWidget(label)
                item_layout.addWidget(edit, 1)
                section_layout.addWidget(item_widget)
                group_items.append((key, item_widget))

            section_layout.addWidget(MDivider())
            self.shortcut_scroll_layout.addWidget(section_widget)
            self.shortcut_sections.append((section_widget, group_items))

        self.shortcut_scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        self.shortcut_search.textChanged.connect(self._filter_shortcuts)

        return shortcut_widget

    def _filter_shortcuts(self, text: str):
        text = text.lower()
        for section_widget, items in self.shortcut_sections:
            section_visible = False
            for key, widget in items:
                match = text in key.lower() or text in widget.findChild(ShortcutEditWidget).text().lower()
                widget.setVisible(match)
                if match:
                    section_visible = True
            section_widget.setVisible(section_visible)

    def _save_shortcuts(self):
        """Salva le scorciatoie correnti in QSettings e conferma all'utente."""
        manager = self.parent().shortcut_manager if hasattr(self.parent(), 'shortcut_manager') else None
        if manager is None:
            return
        manager.save()
        MMessage.success(self.tr("Scorciatoie salvate"), parent=self)

    def _reset_all_shortcuts(self):
        confirm = QtWidgets.QMessageBox.question(
            self, self.tr("Conferma"),
            self.tr("Vuoi ripristinare tutte le scorciatoie ai valori predefiniti?"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            manager = self.parent().shortcut_manager if hasattr(self.parent(), 'shortcut_manager') else None
            if manager:
                manager.reset_all()
                for key, edit in self.shortcut_inputs.items():
                    edit.setText(manager.get_default(key))
                MMessage.success(self.tr("Scorciatoie ripristinate"), parent=self)