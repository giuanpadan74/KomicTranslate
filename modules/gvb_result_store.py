from PySide6 import QtGui

from modules.gvb_image_state import image_from_base64, image_to_base64, qimage_signature


class GvbResultStore:
    def __init__(self):
        self.invalidate()

    def invalidate(self):
        self._image_base64 = ""
        self._signature = ""
        self._source_signature = ""

    def remember_source(self, image: QtGui.QImage):
        self._source_signature = qimage_signature(image)

    def store_result(self, image: QtGui.QImage):
        self._image_base64 = image_to_base64(image)
        self._signature = qimage_signature(image)

    def has_result(self) -> bool:
        return bool(self._image_base64 and self._signature)

    def result_image(self) -> QtGui.QImage:
        return image_from_base64(self._image_base64)

    def signature(self) -> str:
        return self._signature

    def source_signature(self) -> str:
        return self._source_signature

    def matches_source(self) -> bool:
        return bool(self._signature and self._signature == self._source_signature)
