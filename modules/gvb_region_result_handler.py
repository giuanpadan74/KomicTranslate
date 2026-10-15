from PySide6 import QtGui

from app.ui.messages import Messages
from modules.gvb_image_clipboard import get_image_from_windows_clipboard
from modules.gvb_image_state import qimage_signature


class GvbRegionResultHandler:
    def __init__(self, session, result_store, original_image_getter):
        self.session = session
        self.result_store = result_store
        self.original_image_getter = original_image_getter

    def invalidate_previous_result(self, source_image: QtGui.QImage):
        self.result_store.invalidate()
        self.result_store.remember_source(source_image)
        self.session.edited_png_base64 = ''
        self.session.edited_signature = ''

    def resolve_candidate_image(self, force_clipboard: bool) -> QtGui.QImage:
        clipboard_image = get_image_from_windows_clipboard()
        if not clipboard_image.isNull():
            signature = qimage_signature(clipboard_image)
            if force_clipboard:
                return clipboard_image
            if self.result_store.has_result() and signature == self.result_store.source_signature():
                return self.result_store.result_image()
            if signature != self.session.cropped_signature:
                return clipboard_image
        if self.result_store.has_result():
            return self.result_store.result_image()
        return clipboard_image

    def store_result(self, image: QtGui.QImage):
        self.result_store.store_result(image)

    def should_apply_closed_image(self, host, image: QtGui.QImage) -> bool:
        if image.isNull():
            Messages.show_warning(
                host,
                'Nessuna immagine finale',
                'Alla chiusura di GVB non è stata trovata un’immagine valida negli appunti.',
            )
            return False
        if self._matches_original(image):
            Messages.show_info(
                host,
                'Nessuna modifica rilevata',
                'L’immagine negli appunti coincide con la regione originale: nessuna patch applicata.',
                duration=4,
            )
            return False
        return True

    def _matches_original(self, image: QtGui.QImage) -> bool:
        if self.result_store.has_result() and self.result_store.signature() == qimage_signature(image):
            return False
        return self.result_store.matches_source() or qimage_signature(self.original_image_getter()) == qimage_signature(image)
