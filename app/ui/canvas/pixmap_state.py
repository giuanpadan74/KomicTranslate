import numpy as np
from PySide6 import QtGui


def pixmap_to_cv2_rgb(pixmap: QtGui.QPixmap):
    """Converte un QPixmap in un'immagine numpy RGB."""
    if pixmap is None or pixmap.isNull():
        return None

    qimage = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_RGB888)
    width = qimage.width()
    height = qimage.height()
    bytes_per_line = qimage.bytesPerLine()
    ptr = qimage.bits()
    arr = np.array(ptr).reshape((height, bytes_per_line))
    arr = arr[:, : width * 3].reshape((height, width, 3)).copy()
    return arr


def sync_viewer_photo_to_image_data(viewer) -> bool:
    """Allinea il pixmap mostrato dal viewer con image_data della pagina corrente."""
    photo = getattr(viewer, "photo", None)
    if photo is None:
        return False

    try:
        pixmap = photo.pixmap()
    except (RuntimeError, AttributeError):
        return False

    cv2_image = pixmap_to_cv2_rgb(pixmap)
    if cv2_image is None:
        return False

    parent = viewer.parent()
    while parent is not None:
        image_files = getattr(parent, "image_files", None)
        curr_img_idx = getattr(parent, "curr_img_idx", None)
        image_data = getattr(parent, "image_data", None)
        if isinstance(image_files, list) and isinstance(curr_img_idx, int) and isinstance(image_data, dict):
            if 0 <= curr_img_idx < len(image_files):
                image_data[image_files[curr_img_idx]] = cv2_image
                return True
        parent = parent.parent()

    return False
