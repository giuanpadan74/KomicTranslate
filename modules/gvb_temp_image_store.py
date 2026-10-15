import os
import tempfile
import uuid

from PySide6 import QtGui


class GvbTempImageStore:
    def __init__(self):
        self._paths: list[str] = []

    def save_qimage(self, image: QtGui.QImage) -> str:
        if image.isNull():
            return ''
        directory = os.path.join(tempfile.gettempdir(), 'komictranslate_gvb')
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f'{uuid.uuid4().hex}.png')
        if not image.save(path, 'PNG'):
            return ''
        self._paths.append(path)
        return path

    def cleanup(self):
        for path in self._paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self._paths.clear()
