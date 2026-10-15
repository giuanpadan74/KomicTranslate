from PySide6 import QtCore, QtGui

from app.ui.messages import Messages
from modules.gvb_image_state import image_to_base64, qimage_signature
from modules.region_crop_service import crop_qimage


class GvbRegionSelection:
    def __init__(self, host, session, result_handler, current_qimage_getter, open_gvb_callback):
        self.host = host
        self.session = session
        self.result_handler = result_handler
        self.current_qimage_getter = current_qimage_getter
        self.open_gvb_callback = open_gvb_callback

    def finalize_selection(self, view_rect: QtCore.QRect):
        if (
            not hasattr(self.host, "image_files")
            or not self.host.image_files
            or not hasattr(self.host, "curr_img_idx")
            or self.host.curr_img_idx < 0
            or self.host.curr_img_idx >= len(self.host.image_files)
        ):
            Messages.show_warning(self.host, 'Nessuna immagine', 'Carica prima un\'immagine.')
            return False
        scene_rect = self.host.image_viewer.mapToScene(view_rect).boundingRect()
        image_rect = scene_rect.toAlignedRect().intersected(self.host.image_viewer.photo.boundingRect().toAlignedRect())
        cropped = crop_qimage(self.current_qimage_getter(), image_rect)
        if cropped.isNull():
            Messages.show_error(self.host, 'Selezione non valida', 'La regione selezionata non è valida.')
            return False
        self.session.source_image_path = self.host.image_files[self.host.curr_img_idx]
        self.session.source_rect = (image_rect.x(), image_rect.y(), image_rect.width(), image_rect.height())
        self.session.cropped_png_base64 = image_to_base64(cropped)
        self.session.cropped_signature = qimage_signature(cropped)
        self.result_handler.invalidate_previous_result(cropped)
        self.session.status = 'region_ready'
        self.open_gvb_callback(cropped)
        return True
