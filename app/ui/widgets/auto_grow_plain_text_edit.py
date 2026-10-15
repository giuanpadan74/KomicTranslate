import math

from PySide6 import QtCore, QtGui, QtWidgets


class AutoGrowPlainTextEdit(QtWidgets.QPlainTextEdit):
    def __init__(self, parent=None, *, read_only: bool = False, min_lines: int = 2):
        super().__init__(parent)
        self._min_lines = max(1, int(min_lines))
        self._pending = False

        self.setReadOnly(bool(read_only))
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        opt = self.document().defaultTextOption()
        opt.setAlignment(QtCore.Qt.AlignLeft)
        self.document().setDefaultTextOption(opt)

        self.document().documentLayout().documentSizeChanged.connect(self._schedule_adjust)
        self.textChanged.connect(self._schedule_adjust)
        self._schedule_adjust()

    def adjust_height_now(self):
        self._adjust_height_now()

    def set_min_lines(self, min_lines: int):
        self._min_lines = max(1, int(min_lines))
        self._schedule_adjust()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_adjust()

    def _schedule_adjust(self):
        if self._pending:
            return
        self._pending = True
        QtCore.QTimer.singleShot(0, self._adjust_height_now)

    def _adjust_height_now(self):
        self._pending = False

        fm = QtGui.QFontMetrics(self.font())
        line_h = fm.lineSpacing()
        min_h = int(line_h * self._min_lines)

        self.document().setTextWidth(max(0, self.viewport().width()))
        doc_units_h = float(self.document().size().height())
        doc_h = int(math.ceil(doc_units_h * line_h) + self.frameWidth() * 2 + 12)

        margins = self.contentsMargins()
        doc_h += int(margins.top() + margins.bottom())

        desired = max(min_h, doc_h)

        if desired != self.height():
            self.setFixedHeight(desired)
        self.verticalScrollBar().setValue(0)
