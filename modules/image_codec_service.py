import base64

from PySide6 import QtCore, QtGui


def qimage_to_png_base64(image: QtGui.QImage) -> str:
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return base64.b64encode(bytes(buffer.data())).decode("utf-8")


def png_base64_to_qimage(data: str) -> QtGui.QImage:
    image = QtGui.QImage()
    image.loadFromData(base64.b64decode(data), "PNG")
    return image
