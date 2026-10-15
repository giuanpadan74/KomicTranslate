from PySide6 import QtCore, QtGui

from app.ui.messages import Messages
from modules.gvb_image_state import image_to_base64, qimage_signature
from modules.region_patch_service import apply_patch_to_qimage


class GvbPatchApplier:
    def __init__(self, host, session, current_qimage_getter, result_qimage_getter, current_qimage_setter):
        self.host = host
        self.session = session
        self.current_qimage_getter = current_qimage_getter
        self.result_qimage_getter = result_qimage_getter
        self.current_qimage_setter = current_qimage_setter

    def store_result_image(self, image: QtGui.QImage):
        self.session.edited_png_base64 = image_to_base64(image)
        self.session.edited_signature = qimage_signature(image)

    def apply_result(self):
        if not self.session.has_result() or not self.session.source_rect:
            return
        source_image = self.current_qimage_getter()
        patch_image = self.result_qimage_getter()
        rect = QtCore.QRect(*self.session.source_rect)
        result_image = apply_patch_to_qimage(source_image, rect, patch_image)
        if result_image.isNull():
            Messages.show_error(self.host, 'Patch fallita', 'Impossibile applicare la patch alla tavola.')
            return
        self.current_qimage_setter(result_image)
        self.session.status = 'applied'
        self.host._schedule_save_current_image_state(100)
        Messages.show_info(self.host, 'Patch applicata', 'La porzione modificata è stata reintegrata.', duration=4)
