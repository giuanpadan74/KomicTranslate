from PySide6 import QtCore, QtGui, QtWidgets

from app.models.region_edit_session import RegionEditSession
from app.ui.messages import Messages
from modules.gvb_browser_flow import GvbBrowserFlow
from modules.gvb_image_upload_service import GvbImageUploadService
from modules.gvb_patch_applier import GvbPatchApplier
from modules.gvb_prompt_store import load_gvb_prompt_text
from modules.gvb_region_result_handler import GvbRegionResultHandler
from modules.gvb_region_selection import GvbRegionSelection
from modules.gvb_result_store import GvbResultStore
from modules.gvb_temp_image_store import GvbTempImageStore


class RegionGvbController(QtCore.QObject):
    patch_received = QtCore.Signal(object)
    cancel_requested = QtCore.Signal()
    window_closed = QtCore.Signal()

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.session = RegionEditSession()
        self.result_store = GvbResultStore()
        self.temp_store = GvbTempImageStore()
        self.upload_service = GvbImageUploadService()
        self.browser_flow = GvbBrowserFlow(host, self.upload_service)
        self.result_handler = GvbRegionResultHandler(self.session, self.result_store, self._cropped_qimage_from_session)
        self.patch_applier = GvbPatchApplier(
            host,
            self.session,
            self._current_qimage,
            self._cropped_result_qimage,
            self._set_current_qimage,
        )
        self.selection_handler = GvbRegionSelection(
            host,
            self.session,
            self.result_handler,
            self._current_qimage,
            self._complete_selection,
        )
        self.origin = None
        self.rubber_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, host.image_viewer.viewport())
        self.patch_received.connect(self._apply_patch_on_ui_thread)
        self.cancel_requested.connect(self._cancel_on_ui_thread)

    def start_selection(self):
        if (
            not self.host.image_viewer.hasPhoto()
            or not hasattr(self.host, "image_files")
            or not self.host.image_files
            or self.host.curr_img_idx < 0
            or self.host.curr_img_idx >= len(self.host.image_files)
        ):
            Messages.show_warning(self.host, 'Nessuna immagine', 'Carica prima un\'immagine.')
            return
        self.cancel_selection()
        self.session.reset()
        self.session.status = 'selecting'
        viewport = self.host.image_viewer.viewport()
        viewport.installEventFilter(self)
        viewport.setCursor(QtCore.Qt.CrossCursor)
        Messages.show_info(self.host, 'Selezione attiva', 'Disegna un rettangolo sull\'immagine.', duration=4)

    def eventFilter(self, obj, event):
        if obj is not self.host.image_viewer.viewport() or self.session.status != 'selecting':
            return super().eventFilter(obj, event)
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.rubber_band.setGeometry(QtCore.QRect(self.origin, QtCore.QSize()))
            self.rubber_band.show()
            return True
        if event.type() == QtCore.QEvent.Type.MouseMove and self.origin is not None:
            self.rubber_band.setGeometry(QtCore.QRect(self.origin, event.position().toPoint()).normalized())
            return True
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton and self.origin is not None:
            rect = self.rubber_band.geometry()
            self.rubber_band.hide()
            self.origin = None
            self._finalize_selection(rect)
            return True
        return super().eventFilter(obj, event)

    def _finalize_selection(self, view_rect: QtCore.QRect):
        if (
            not hasattr(self.host, "image_files")
            or not self.host.image_files
            or self.host.curr_img_idx < 0
            or self.host.curr_img_idx >= len(self.host.image_files)
        ):
            Messages.show_warning(self.host, 'Nessuna immagine', 'Carica prima un\'immagine.')
            self.cancel_selection()
            return
        if not self.selection_handler.finalize_selection(view_rect):
            self.cancel_selection()
            return
        self.cancel_selection(keep_session=True)

    def _complete_selection(self, cropped: QtGui.QImage):
        self._copy_region_and_open_gvb(cropped)

    def cancel_selection(self, keep_session=False):
        viewport = self.host.image_viewer.viewport()
        try:
            viewport.removeEventFilter(self)
        except Exception:
            pass
        viewport.unsetCursor()
        self.rubber_band.hide()
        self.origin = None
        if not keep_session and self.session.status == 'selecting':
            self.session.reset()

    def open_in_gvb(self):
        if not self.session.is_ready():
            Messages.show_warning(self.host, 'Nessuna selezione', 'Seleziona prima una regione valida.')
            return
        self._copy_region_and_open_gvb()

    def _copy_region_and_open_gvb(self, cropped: QtGui.QImage | None = None):
        region = cropped if cropped is not None else self._cropped_qimage_from_session()
        if region.isNull():
            Messages.show_error(self.host, 'Regione non disponibile', 'Impossibile preparare la regione per GVB.')
            return
        self.result_handler.invalidate_previous_result(region)
        image_path = self.temp_store.save_qimage(region)
        if not image_path:
            Messages.show_error(self.host, 'File temporaneo non disponibile', 'Impossibile preparare l’immagine per GVB.')
            return
        prompt_text = load_gvb_prompt_text("")
        print(
            f"[REGION GVB DEBUG] Prompt caricato da QSettings: "
            f"{('' if prompt_text is None else repr(prompt_text)[:100] + ('...' if len(prompt_text or '') > 100 else ''))}"
        )
        self.session.status = 'waiting_gvb_result'
        self.browser_flow.open_with_image(image_path, self._on_gvb_window_closed, prompt_text=prompt_text)
        if prompt_text and prompt_text.strip():
            Messages.show_info(
                self.host,
                'Regione e prompt pronti',
                'La regione e il prompt salvato vengono caricati automaticamente in GVB. Poi copia il risultato finale e premi Apply GVB Region.',
                duration=6,
            )
        else:
            Messages.show_info(
                self.host,
                'Regione pronta',
                'La regione viene caricata automaticamente in GVB con retry e fallback. Poi copia il risultato finale e premi Apply GVB Region.',
                duration=6,
            )

    def _on_gvb_window_closed(self):
        self.window_closed.emit()

    @QtCore.Slot()
    def _apply_patch_after_window_closed(self):
        if not self.session.source_rect or self.session.status != 'waiting_gvb_result':
            return
        image = self.result_handler.resolve_candidate_image(force_clipboard=False)
        if not self.result_handler.should_apply_closed_image(self.host, image):
            return
        self.result_handler.store_result(image)
        self.patch_received.emit(image)

    def apply_region_from_clipboard(self):
        if not self.session.source_rect:
            Messages.show_warning(self.host, 'Nessuna regione', 'Seleziona prima una regione da inviare a GVB.')
            return
        image = self.result_handler.resolve_candidate_image(force_clipboard=True)
        if image.isNull():
            Messages.show_error(self.host, 'Clipboard vuota', 'Nessuna immagine valida trovata negli appunti.')
            return
        self.result_handler.store_result(image)
        self.patch_received.emit(image)

    @QtCore.Slot(object)
    def _apply_patch_on_ui_thread(self, image: QtGui.QImage):
        self.patch_applier.store_result_image(image)
        self.session.status = 'result_ready'
        self.patch_applier.apply_result()

    def apply_result(self):
        self.patch_applier.apply_result()

    def cancel_region_editing(self):
        self.cancel_requested.emit()

    @QtCore.Slot()
    def _cancel_on_ui_thread(self):
        self.cancel_selection()
        self.result_store.invalidate()
        self.temp_store.cleanup()
        self.session.reset()

    def _current_qimage(self) -> QtGui.QImage:
        pixmap = self.host.image_viewer.photo.pixmap()
        return pixmap.toImage() if not pixmap.isNull() else QtGui.QImage()

    def _cropped_qimage_from_session(self) -> QtGui.QImage:
        from modules.image_codec_service import png_base64_to_qimage

        return png_base64_to_qimage(self.session.cropped_png_base64)

    def _cropped_result_qimage(self) -> QtGui.QImage:
        from modules.image_codec_service import png_base64_to_qimage

        return png_base64_to_qimage(self.session.edited_png_base64)

    def _set_current_qimage(self, image: QtGui.QImage):
        pixmap = QtGui.QPixmap.fromImage(image)
        self.host.image_viewer.setPhoto(pixmap)
