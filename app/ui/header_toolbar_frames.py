from PySide6 import QtWidgets


def make_bordered_frame() -> QtWidgets.QFrame:
    frame = QtWidgets.QFrame()
    frame.setObjectName("toolbarGroupFrame")
    frame.setStyleSheet(
        """
        QFrame#toolbarGroupFrame {
            border: 1px solid #4a4a4a;
            border-radius: 4px;
        }
        """
    )
    return frame

