from PySide6 import QtCore, QtGui, QtWidgets

from .dayu_widgets.tool_button import MToolButton
from .operativa_layout_controller import SETTINGS_GROUP

SETTINGS_KEY_SIDEBAR_SECTION_ORDER = "sidebar_section_order"
SECTION_MIME_TYPE = "application/x-komictranslate-sidebar-section"


class _SectionDragHandle(MToolButton):
    def __init__(self, section_key: str, parent=None):
        super().__init__(parent)
        self._section_key = section_key
        self._drag_start_pos = QtCore.QPoint()
        self.small().icon_only().svg("move.svg")
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setToolTip("Trascina per riordinare la sezione")
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setFixedSize(18, 18)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & QtCore.Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if (
            event.position().toPoint() - self._drag_start_pos
        ).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return super().mouseMoveEvent(event)
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setData(SECTION_MIME_TYPE, self._section_key.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(QtCore.Qt.MoveAction)
        self.setCursor(QtCore.Qt.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        self.setCursor(QtCore.Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class SidebarSectionsWidget(QtWidgets.QWidget):
    def __init__(self, settings: QtCore.QSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._sections: dict[str, QtWidgets.QWidget] = {}
        self._ordered_keys: list[str] = []
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setAcceptDrops(True)

    def add_section(self, section_key: str, section_widget: QtWidgets.QWidget) -> None:
        if section_key in self._sections:
            raise ValueError(f"Sezione duplicata: {section_key}")
        self._sections[section_key] = section_widget
        self._ordered_keys.append(section_key)
        self._install_drag_handle(section_key, section_widget)
        self._rebuild_layout()

    def ordered_keys(self) -> list[str]:
        return list(self._ordered_keys)

    def restore_order(self) -> None:
        stored = self._load_order()
        if not stored:
            return
        ordered = [key for key in stored if key in self._sections]
        ordered.extend(key for key in self._ordered_keys if key not in ordered)
        self._ordered_keys = ordered
        self._rebuild_layout()

    def move_section(self, section_key: str, target_index: int) -> None:
        if section_key not in self._sections:
            return
        source_index = self._ordered_keys.index(section_key)
        target_index = max(0, min(target_index, len(self._ordered_keys) - 1))
        if source_index == target_index:
            return
        self._ordered_keys.pop(source_index)
        self._ordered_keys.insert(target_index, section_key)
        self._rebuild_layout()
        self._save_order()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SECTION_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SECTION_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        raw_key = bytes(event.mimeData().data(SECTION_MIME_TYPE)).decode("utf-8")
        if raw_key not in self._sections:
            event.ignore()
            return
        target_index = self._index_for_y(event.position().toPoint().y())
        source_index = self._ordered_keys.index(raw_key)
        if source_index < target_index:
            target_index -= 1
        self.move_section(raw_key, target_index)
        event.acceptProposedAction()

    def eventFilter(self, watched, event):
        if event.type() in (
            QtCore.QEvent.DragEnter,
            QtCore.QEvent.DragMove,
            QtCore.QEvent.Drop,
        ):
            if not getattr(event.mimeData(), "hasFormat", lambda *_: False)(SECTION_MIME_TYPE):
                return super().eventFilter(watched, event)
            if event.type() == QtCore.QEvent.Drop:
                local_pos = watched.mapTo(self, event.position().toPoint())
                raw_key = bytes(event.mimeData().data(SECTION_MIME_TYPE)).decode("utf-8")
                # Chiave obsoleta (ordine salvato in una sessione precedente,
                # o add_section mai riuscita): list.index solleverebbe
                # ValueError dentro un event filter.
                if raw_key not in self._ordered_keys:
                    return super().eventFilter(watched, event)
                target_index = self._index_for_y(local_pos.y())
                source_index = self._ordered_keys.index(raw_key)
                if source_index < target_index:
                    target_index -= 1
                self.move_section(raw_key, target_index)
            event.acceptProposedAction()
            return True
        return super().eventFilter(watched, event)

    def _install_drag_handle(self, section_key: str, section_widget: QtWidgets.QWidget) -> None:
        header = getattr(section_widget, "header_widget", None)
        header_layout = header.layout() if header is not None else None
        if header_layout is None:
            return
        handle = _SectionDragHandle(section_key, header)
        insert_at = max(0, header_layout.count() - 3)
        header_layout.insertWidget(insert_at, handle)
        for watched in (section_widget, header):
            watched.setAcceptDrops(True)
            watched.installEventFilter(self)

    def _index_for_y(self, y_pos: int) -> int:
        for index, section_key in enumerate(self._ordered_keys):
            widget = self._sections[section_key]
            midpoint = widget.geometry().top() + widget.height() / 2
            if y_pos < midpoint:
                return index
        return len(self._ordered_keys)

    def _rebuild_layout(self) -> None:
        while self._layout.count():
            self._layout.takeAt(0)
        for section_key in self._ordered_keys:
            self._layout.addWidget(self._sections[section_key])
        self._layout.addStretch()

    def _load_order(self) -> list[str]:
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            value = self._settings.value(SETTINGS_KEY_SIDEBAR_SECTION_ORDER, [])
        finally:
            self._settings.endGroup()
        if isinstance(value, str):
            return [value]
        return list(value or [])

    def _save_order(self) -> None:
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            self._settings.setValue(
                SETTINGS_KEY_SIDEBAR_SECTION_ORDER,
                self._ordered_keys,
            )
        finally:
            self._settings.endGroup()
