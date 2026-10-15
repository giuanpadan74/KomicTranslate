from PySide6 import QtCore, QtWidgets


SETTINGS_ORG = "ComicLabs"
SETTINGS_APP = "KomicTranslate"
SETTINGS_GROUP = "ui_layout"
SETTINGS_KEY_HEADER_IN_SIDEBAR = "header_in_sidebar"


class OperativaLayoutController(QtCore.QObject):
    def __init__(
        self,
        settings: QtCore.QSettings,
        header_toolbar_widget: QtWidgets.QWidget,
        header_host_widget: QtWidgets.QWidget,
        header_host_layout: QtWidgets.QLayout,
        sidebar_host_widget: QtWidgets.QWidget,
        sidebar_host_layout: QtWidgets.QLayout,
        toggle_button: QtWidgets.QAbstractButton,
        on_mode_changed=None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._header_toolbar_widget = header_toolbar_widget
        self._header_host_widget = header_host_widget
        self._header_host_layout = header_host_layout
        self._sidebar_host_widget = sidebar_host_widget
        self._sidebar_host_layout = sidebar_host_layout
        self._toggle_button = toggle_button
        self._on_mode_changed = on_mode_changed
        self._in_sidebar = False

    def load_preference(self) -> bool:
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            return self._settings.value(SETTINGS_KEY_HEADER_IN_SIDEBAR, False, type=bool)
        finally:
            self._settings.endGroup()

    def save_preference(self, value: bool) -> None:
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            self._settings.setValue(SETTINGS_KEY_HEADER_IN_SIDEBAR, bool(value))
        finally:
            self._settings.endGroup()

    def apply(self, show_in_sidebar: bool) -> None:
        show_in_sidebar = bool(show_in_sidebar)
        if self._in_sidebar == show_in_sidebar:
            self._update_toggle_ui()
            if self._on_mode_changed is not None:
                self._on_mode_changed(show_in_sidebar)
            return

        self._detach_toolbar()
        if show_in_sidebar:
            self._sidebar_host_layout.addWidget(self._header_toolbar_widget)
            self._header_host_widget.setVisible(False)
            self._sidebar_host_widget.setVisible(True)
        else:
            self._header_host_layout.addWidget(self._header_toolbar_widget)
            self._header_host_widget.setVisible(True)
            self._sidebar_host_widget.setVisible(False)

        self._in_sidebar = show_in_sidebar
        self.save_preference(show_in_sidebar)
        self._update_toggle_ui()
        if self._on_mode_changed is not None:
            self._on_mode_changed(show_in_sidebar)

    def toggle(self) -> None:
        self.apply(not self._in_sidebar)

    def _detach_toolbar(self) -> None:
        old_parent = self._header_toolbar_widget.parentWidget()
        if old_parent is None:
            return

        for layout in (self._header_host_layout, self._sidebar_host_layout):
            if layout is None:
                continue
            layout.removeWidget(self._header_toolbar_widget)

        self._header_toolbar_widget.setParent(None)

    def _update_toggle_ui(self) -> None:
        if self._toggle_button is None:
            return
        if self._in_sidebar:
            self._toggle_button.setToolTip("Mostra i pulsanti nella barra laterale (risparmia spazio verticale)")
            self._toggle_button.setChecked(True)
        else:
            self._toggle_button.setToolTip("Mostra i pulsanti nella barra superiore")
            self._toggle_button.setChecked(False)
