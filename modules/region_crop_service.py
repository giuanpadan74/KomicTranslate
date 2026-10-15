from PySide6 import QtCore, QtGui


def normalize_rect(rect: QtCore.QRect) -> QtCore.QRect:
    return rect.normalized().intersected(rect.normalized())


def crop_qimage(image: QtGui.QImage, rect: QtCore.QRect) -> QtGui.QImage:
    if image.isNull():
        return QtGui.QImage()
    image_rect = QtCore.QRect(0, 0, image.width(), image.height())
    safe_rect = rect.normalized().intersected(image_rect)
    if safe_rect.width() <= 1 or safe_rect.height() <= 1:
        return QtGui.QImage()
    return image.copy(safe_rect)
