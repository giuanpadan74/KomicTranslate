#!/usr/bin/env python
# -*- coding: utf-8 -*-
###################################################################
# Author: Mu yanru
# Date  : 2019.2
# Email : muyanru345@163.com
###################################################################
"""
MToast
"""
# Import future modules
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# Import third-party modules
from PySide6 import QtCore
from PySide6 import QtWidgets

# Import local modules
from . import dayu_theme
from .avatar import MAvatar
from .label import MLabel
from .loading import MLoading
from .qt import MPixmap


class MToast(QtWidgets.QWidget):
    """
    MToast
    A Phone style message.
    """

    InfoType = "info"
    SuccessType = "success"
    WarningType = "warning"
    ErrorType = "error"
    LoadingType = "loading"

    default_config = {
        "duration": 5,  # Aumentato da 2 a 5 secondi
    }

    sig_closed = QtCore.Signal()

    def __init__(self, text, duration=None, dayu_type=None, parent=None):
        super(MToast, self).__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Dialog
            | QtCore.Qt.WindowStaysOnTopHint
        )
        
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 0.8);
                color: white;
                border-radius: 4px;
                padding: 10px;
            }
            QLabel {
                color: white;
                padding: 5px;
            }
        """)

        # Layout principale
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # Icona
        if dayu_type == MToast.LoadingType:
            icon = MLoading(size=dayu_theme.huge, color=dayu_theme.text_color_inverse)
        else:
            icon = MAvatar()
            icon.set_dayu_size(dayu_theme.toast_icon_size)
            icon.set_dayu_image(
                MPixmap(
                    "{}_line.svg".format(dayu_type or MToast.InfoType),
                    dayu_theme.text_color_inverse,
                )
            )
        layout.addWidget(icon, 0, QtCore.Qt.AlignTop)

        # Testo
        self._content_label = QtWidgets.QLabel(text)
        self._content_label.setWordWrap(True)
        self._content_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self._content_label.setMinimumWidth(200)
        self._content_label.setMaximumWidth(500)
        layout.addWidget(self._content_label, 1)  # Espandi il testo

        # Pulsante di chiusura
        self._close_button = QtWidgets.QPushButton("×")
        self._close_button.setFixedSize(24, 24)
        self._close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                font-size: 18px;
                font-weight: bold;
                padding: 0;
                margin: 0;
            }
            QPushButton:hover {
                color: #cccccc;
            }
        """)
        self._close_button.clicked.connect(self.close)
        layout.addWidget(self._close_button, 0, QtCore.Qt.AlignTop)

        self.setLayout(layout)
        self.adjustSize()

        # Timer per la chiusura automatica
        self._close_timer = QtCore.QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self.close)
        self._close_timer.timeout.connect(self.sig_closed)
        self._close_timer.setInterval((duration or self.default_config.get("duration")) * 1000)
        
        if dayu_type != MToast.LoadingType:
            self._close_timer.start()

        # Animazione di ingresso
        self.setWindowOpacity(0.0)
        self._fade_animation = QtCore.QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(300)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(0.9)
        self._fade_animation.finished.connect(self._on_fade_in_finished)
        
        self._get_center_position(parent)
        self.show()
        self._fade_animation.start()
        
    def _on_fade_in_finished(self):
        # Assicurati che il timer parta solo dopo che l'animazione di ingresso è completata
        if hasattr(self, '_close_timer') and not self._close_timer.isActive() and not self._close_timer.isSingleShot():
            self._close_timer.start()
            
    def closeEvent(self, event):
        # Ferma il timer quando il widget viene chiuso
        if hasattr(self, '_close_timer') and self._close_timer.isActive():
            self._close_timer.stop()
        super(MToast, self).closeEvent(event)

    def closeEvent(self, event):
        if hasattr(self, '_close_timer') and self._close_timer.isActive():
            self._close_timer.stop()
            
        if self.has_played:
            event.accept()
        else:
            self._fade_out()
            event.ignore()

    def _fade_out(self):
        self.has_played = True
        self._opacity_ani.setDirection(QtCore.QAbstractAnimation.Backward)
        self._opacity_ani.finished.connect(self.close)
        self._opacity_ani.start()

    def _fade_int(self):
        self._opacity_ani.start()

    def _get_center_position(self, parent):
        parent_geo = parent.geometry()
        if parent.isWindowType():
            # 其parent没有parent了，就是个完全独立的窗口
            pos = parent_geo.topLeft()
        elif parent in QtWidgets.QApplication.topLevelWidgets():
            # 其parent虽然是独立窗口，但却还有parent，常见情况，DCC中比如Maya我们开发的工具窗口，会将maya主窗口作为工具节目的parent
            pos = parent_geo.topLeft()
        else:
            pos = parent.mapToGlobal(parent_geo.topLeft())
        offset = 0
        for child in parent.children():
            if isinstance(child, MToast) and child.isVisible():
                offset = max(offset, child.y())
        target_x = pos.x() + parent_geo.width() / 2 - self.width() / 2
        target_y = pos.y() + parent_geo.height() / 2 - self.height() / 2
        self.setProperty("pos", QtCore.QPoint(target_x, target_y))

    @classmethod
    def info(cls, text, parent, duration=None):
        """Show a normal toast message"""
        inst = cls(text, duration=duration, dayu_type=MToast.InfoType, parent=parent)
        inst.show()
        return inst

    @classmethod
    def success(cls, text, parent, duration=None):
        """Show a success toast message"""
        inst = cls(text, duration=duration, dayu_type=MToast.SuccessType, parent=parent)
        inst.show()
        return inst

    @classmethod
    def warning(cls, text, parent, duration=None):
        """Show a warning toast message"""
        inst = cls(text, duration=duration, dayu_type=MToast.WarningType, parent=parent)
        inst.show()
        return inst

    @classmethod
    def error(cls, text, parent, duration=None):
        """Show an error toast message"""
        inst = cls(text, duration=duration, dayu_type=MToast.ErrorType, parent=parent)
        inst.show()
        return inst

    @classmethod
    def loading(cls, text, parent):
        """Show a toast message with loading animation.
        You should close this widget by yourself."""
        inst = cls(text, dayu_type=MToast.LoadingType, parent=parent)
        inst.show()
        return inst

    @classmethod
    def config(cls, duration):
        """
        Config the global MToast duration setting.
        :param duration: int (unit is second)
        :return: None
        """
        if duration is not None:
            cls.default_config["duration"] = duration
