"""Comando undo/redo per lo strumento secchiello (bucket fill)."""

from PySide6.QtGui import QUndoCommand, QPixmap
from app.ui.canvas.pixmap_state import sync_viewer_photo_to_image_data


class BucketFillCommand(QUndoCommand):
    """Salva il pixmap prima e dopo il flood fill per supportare undo/redo."""

    def __init__(self, viewer, old_pixmap: QPixmap, new_pixmap: QPixmap):
        super().__init__()
        self.viewer = viewer
        self.old_pixmap = old_pixmap
        self.new_pixmap = new_pixmap
        self.first = True

    def _is_photo_valid(self):
        """Verifica che il photo item sia ancora valido e appartenga alla scena."""
        try:
            return (
                self.viewer.photo is not None and
                self.viewer.photo.scene() is not None and
                not self.viewer.photo.pixmap().isNull()
            )
        except (RuntimeError, AttributeError):
            return False

    def redo(self):
        if self.first:
            self.first = False
            return
        if self._is_photo_valid():
            self.viewer.photo.setPixmap(self.new_pixmap)
            sync_viewer_photo_to_image_data(self.viewer)
            self.viewer._scene.update()

    def undo(self):
        if self._is_photo_valid():
            self.viewer.photo.setPixmap(self.old_pixmap)
            sync_viewer_photo_to_image_data(self.viewer)
            self.viewer._scene.update()
