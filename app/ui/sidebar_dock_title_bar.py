from PySide6 import QtCore, QtWidgets

from .dayu_widgets.tool_button import MToolButton


class SidebarDockTitleBar(QtWidgets.QWidget):
    layout_toggle_requested = QtCore.Signal()
    float_toggle_requested = QtCore.Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarDockTitleBar")
        self.setFixedHeight(28)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 2)
        layout.setSpacing(4)

        self._title_label = QtWidgets.QLabel(title, self)
        self._title_label.setStyleSheet("color: white; font-weight: 600;")
        layout.addWidget(self._title_label)
        layout.addStretch()

        self._layout_button = self._build_button(
            "list_view.svg",
            "Sposta i pulsanti operativi nella barra laterale",
            self.layout_toggle_requested.emit,
        )
        self._float_button = self._build_button(
            "float.svg",
            "Sgancia la barra laterale in una finestra separata",
            self.float_toggle_requested.emit,
        )
        layout.addWidget(self._layout_button)
        layout.addWidget(self._float_button)

        self.setStyleSheet(
            """
            QWidget#SidebarDockTitleBar {
                background-color: #333333;
                border-bottom: 1px solid #444444;
            }
            QWidget#SidebarDockTitleBar QToolButton {
                border: none;
                background: transparent;
                padding: 0;
            }
            QWidget#SidebarDockTitleBar QToolButton:hover {
                background: rgba(255, 255, 255, 0.08);
                border-radius: 3px;
            }
            """
        )

    def _build_button(self, svg_name: str, tooltip: str, callback) -> MToolButton:
        button = MToolButton(self)
        button.small().icon_only().svg(svg_name)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setFocusPolicy(QtCore.Qt.NoFocus)
        button.setFixedSize(18, 18)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_operativa_in_sidebar(self, in_sidebar: bool) -> None:
        self._layout_button.setChecked(bool(in_sidebar))
        if in_sidebar:
            self._layout_button.setToolTip(
                "Mostra i pulsanti operativi nella barra laterale"
            )
        else:
            self._layout_button.setToolTip(
                "Mostra i pulsanti operativi nella barra superiore"
            )

    def set_dock_floating(self, floating: bool) -> None:
        self._float_button.setChecked(bool(floating))
        if floating:
            self._float_button.setToolTip("Riaggancia la barra laterale alla finestra")
        else:
            self._float_button.setToolTip(
                "Sgancia la barra laterale in una finestra separata"
            )

    @property
    def layout_button(self) -> MToolButton:
        return self._layout_button
