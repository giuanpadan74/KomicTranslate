"""
UIMixin - Text/rectangle interactions, text formatting, rendering,
           display helpers, and page-navigation logic.

This mixin is inserted in the MRO so that every method still uses `self`.
"""
import os
import copy
import logging
import time
import winsound
import json as json_mod
import numpy as np
from typing import Tuple
from app.controllers.region_gvb_controller import RegionGvbController
from app.controllers.text_edits_sync import refresh_text_edits_for_current_block
from modules.detection import extract_bubble_polygon
from modules.browser_sites import is_browser_site


def _firefox_is_available() -> bool:
    """True se Firefox e' installato e ha un profilo leggibile.

    Serve solo per Geminiamo, che legge i cookie dal profilo di Firefox.
    Non lancia pywebview e non blocca: una semplice ricerca del profilo.
    Se il controllo stesso fallisce si risponde True (meglio mostrare il
    messaggio generico che nascondere la causa reale).
    """
    try:
        from modules.geminiamo_auth.cookie_manager import BrowserCookieManager
        return bool(BrowserCookieManager().get_firefox_status().get("installed"))
    except Exception:
        return True

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QUndoStack

from app.ui.canvas.polygon_overlay import EditablePolygonOverlay, remove_polygon_overlay
from app.ui.canvas.text_item import TextBlockItem
from app.ui.canvas.rectangle import MoveableRectItem, MoveableEllipseItem
from app.ui.canvas.z_layers import TEXT_BOX_Z
from app.ui.commands.box import (AddRectangleCommand, DeleteBoxesCommand,
                                  BoxesChangeCommand, DeleteMultipleBoxesCommand)
from app.ui.commands.event_utils import ProfilingContext
from app.ui.commands.textformat import TextFormatCommand
from app.ui.commands.multipletextformat import MultipleTextFormatCommand
from constants import (
    HIGHLIGHT_BORDER_CSS,
    BLOCK_MATCH_DIST_THRESHOLD,
    IMAGE_STATE_SAVE_DELAY_MS,
    BLOCK_MATCH_TOLERANCE_PX,
    TEXT_ITEM_ANGLE_TOLERANCE_DEG,
)
from modules.detection import do_rectangles_overlap, get_inpaint_bboxes
from modules.utils.polygon_region import polygon_to_bbox
from modules.utils.textblock import TextBlock
from modules.utils.pipeline_utils import (get_language_code, get_layout_direction,
                                           font_selected, validate_ocr, validate_translator)
from modules.utils.translator_utils import (
    format_translations,
    is_there_text,
    _repair_truncated_json,
    validate_translation_integrity,
)
from modules.rendering.render import manual_wrap
from modules.translator.processor import Translator
from app.ui.font_size_utils import parse_font_size, format_font_size

logger = logging.getLogger(__name__)


class UIMixin:
    """Rectangle / text-item interactions, formatting, rendering, and page nav."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _ensure_region_gvb_controller(self):
        controller = getattr(self, '_region_gvb_controller', None)
        if controller is None:
            controller = RegionGvbController(self)
            self._region_gvb_controller = controller
        return controller

    def start_region_gvb_selection(self):
        self._ensure_region_gvb_controller().start_selection()

    def apply_region_from_gvb_clipboard(self):
        self._ensure_region_gvb_controller().apply_region_from_clipboard()

    def _schedule_save_current_image_state(self, delay_ms: int) -> None:
        try:
            timer = getattr(self, '_image_state_save_timer', None)
            if timer is None:
                timer = QtCore.QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._execute_deferred_save)
                self._image_state_save_timer = timer
            timer.stop()
            timer.start(int(delay_ms))
        except Exception as e:
            logger.debug(f"Errore nel debounce save_current_image_state: {e}")

    def _execute_deferred_save(self):
        """Esegue il save in modo silenzioso senza bloccare l'interfaccia."""
        try:
            self.save_current_image_state()
        except Exception as e:
            logger.debug(f"Errore nel deferred save: {e}")

    def _play_operation_sound(self, sound_name: str):
        """Helper to play operation sounds asynchronously from the wave directory."""
        try:
            sound_path = os.path.join(os.getcwd(), 'wave', sound_name)
            if os.path.exists(sound_path):
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            else:
                logger.warning(f"Sound file not found: {sound_path}")
        except Exception as e:
            logger.error(f"Error playing sound {sound_name}: {e}")

    # ─── Signal-item wiring ───────────────────────────────────────

    def _ensure_moveable_rect_item(self, rect_item):
        """Converte eventuali item legacy senza signals nei tipi Moveable* corretti."""
        if rect_item is None or hasattr(rect_item, "signals"):
            return rect_item

        if isinstance(rect_item, QtWidgets.QGraphicsEllipseItem):
            shape_type = "ellipse"
        else:
            shape_type = getattr(rect_item, "shape_type", "rectangle")
        item_cls = MoveableEllipseItem if shape_type == "ellipse" else MoveableRectItem
        local_rect = rect_item.rect()
        text_block = getattr(rect_item, "text_block", None)
        new_item = item_cls(QtCore.QRectF(local_rect), self.image_viewer.photo, text_block=text_block)
        new_item.setPos(rect_item.pos())
        new_item.setRotation(rect_item.rotation())
        new_item.setTransformOriginPoint(rect_item.transformOriginPoint())
        new_item.setBrush(rect_item.brush())
        new_item.setPen(rect_item.pen())
        new_item.setZValue(rect_item.zValue())
        new_item.setVisible(rect_item.isVisible())
        new_item.setEnabled(rect_item.isEnabled())
        new_item.selected = getattr(rect_item, "selected", False)
        if text_block is not None and getattr(text_block, "shape_type", None):
            new_item.shape_type = text_block.shape_type

        if rect_item in getattr(self.image_viewer, "rectangles", []):
            index = self.image_viewer.rectangles.index(rect_item)
            self.image_viewer.rectangles[index] = new_item
        scene = rect_item.scene()
        if scene is not None:
            scene.removeItem(rect_item)
        return new_item

    def connect_rect_item_signals(self, rect_item: MoveableRectItem):
        rect_item = self._ensure_moveable_rect_item(rect_item)
        if rect_item is None or not hasattr(rect_item, "signals"):
            logger.warning("Skipping rect item without custom signals: %s", type(rect_item).__name__)
            return
        if getattr(rect_item, '_kt_signals_connected', False):
            self._attach_polygon_overlay(rect_item)
            return
        rect_item.signals.rectangle_changed.connect(self.handle_rectangle_change)
        rect_item.signals.change_undo.connect(self.rect_change_undo)
        rect_item.signals.ocr_block.connect(lambda: self.ocr(True))
        rect_item.signals.translate_block.connect(lambda: self.translate_image(True))
        rect_item._kt_signals_connected = True
        self._attach_polygon_overlay(rect_item)

    def _resolve_rect_text_block(self, rect_item):
        blk = getattr(rect_item, 'text_block', None)
        if blk in self.blk_list:
            return blk
        scene_rect = rect_item.mapRectToScene(rect_item.rect())
        rect_coords = scene_rect.getCoords()
        blk = self.find_corresponding_text_block(rect_coords, 0.5)
        if blk is None:
            blk = self.find_corresponding_text_block(rect_coords, 0.1)
        rect_item.text_block = blk
        return blk

    def _attach_polygon_overlay(self, rect_item):
        blk = self._resolve_rect_text_block(rect_item)
        active_polygon = (
            blk.get_active_inpaint_polygon() if blk is not None and hasattr(blk, "get_active_inpaint_polygon") else None
        )
        if blk is None or active_polygon is None:
            remove_polygon_overlay(rect_item, self.image_viewer)
            return
        existing = getattr(rect_item, 'polygon_overlay', None)
        if existing is not None:
            existing.text_block = blk
            existing.rect_item = rect_item
            existing.refresh_from_block()
            existing.set_selected(rect_item.selected)
            return
        overlay = EditablePolygonOverlay(rect_item, blk, self.image_viewer.photo)
        overlay.signals.polygon_changed.connect(self.handle_polygon_overlay_change)
        rect_item.polygon_overlay = overlay
        self.image_viewer.polygon_overlays.append(overlay)
        if not getattr(self.image_viewer, 'polygons_visible', True):
            overlay.setVisible(False)
        overlay.set_selected(rect_item.selected)

    def handle_polygon_overlay_change(self, rect_item, polygon_points):
        blk = self._resolve_rect_text_block(rect_item)
        if blk is None:
            return
        blk.polygon_points = polygon_points
        blk.segm_pts = polygon_points
        blk.use_polygon_inpaint = True
        bbox = polygon_to_bbox(polygon_points)
        if bbox is not None:
            blk.bubble_xyxy = bbox
        blk.filter_inpaint_bboxes()
        self._schedule_save_current_image_state(IMAGE_STATE_SAVE_DELAY_MS)

    def connect_text_item_signals(self, text_item: TextBlockItem):
        if getattr(text_item, '_kt_signals_connected', False):
            return
        text_item.item_selected.connect(self.on_text_item_selected)
        text_item.item_multi_selected.connect(lambda item, multi: self.on_text_item_selected(item, multi))
        text_item.item_deselected.connect(self.on_text_item_deselcted)
        text_item.text_changed.connect(self.update_text_block_from_item)
        text_item.item_changed.connect(self.handle_rectangle_change)
        text_item.text_highlighted.connect(self.set_values_from_highlight)
        text_item.change_undo.connect(self.rect_change_undo)
        text_item._kt_signals_connected = True

    # ─── Button highlighting ─────────────────────────────────────

    def highlight_button(self, button_index):
        """Evidenzia un pulsante del gruppo principale con bordo giallo e spegne i pulsanti successivi"""
        try:
            buttons = self.hbutton_group.get_button_group().buttons()
            # Rimuovi l'evidenziazione dai pulsanti dopo quello selezionato
            for i in range(button_index + 1, len(buttons)):
                buttons[i].setStyleSheet("")
            
            button = buttons[button_index]
            button.setStyleSheet(HIGHLIGHT_BORDER_CSS)
        except (IndexError, AttributeError) as e:
            logger.warning(f"Errore nell'evidenziazione del pulsante {button_index}: {e}")

    def clear_all_highlights(self):
        """Rimuove l'evidenziazione da tutti i pulsanti del gruppo principale (pulsanti 0-5)"""
        try:
            if hasattr(self, 'hbutton_group') and self.hbutton_group:
                button_group = self.hbutton_group.get_button_group()
                if button_group:
                    buttons = button_group.buttons()
                    for i in range(len(buttons)):
                        button = buttons[i]
                        if button:
                            button.setStyleSheet("border: 0px solid #323232; border-radius: 0px;")
                else:
                    logger.warning("button_group non disponibile")
            else:
                logger.warning("hbutton_group non disponibile")
        except Exception as e:
            logger.error(f"Errore nella rimozione delle evidenziazioni: {e}", exc_info=True)

    # ─── Button-group enable/disable ─────────────────────────────

    def disable_hbutton_group(self):
        for button in self.hbutton_group.get_button_group().buttons():
            button.setEnabled(False)
        self.original_button.setEnabled(True)
        self.auto_center_button.setEnabled(False)

    def enable_hbutton_group(self):
        for button in self.hbutton_group.get_button_group().buttons():
            button.setEnabled(True)
        self.original_button.setEnabled(True)
        self.detect_font_button.setEnabled(True)
        self.auto_center_button.setEnabled(True)

    def _enable_batch_buttons(self):
        if hasattr(self, '_apply_batch_action_gate'):
            self._apply_batch_action_gate()
        else:
            self.detect_batch_button.setEnabled(True)
            self.translate_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    # ─── Mode selection ──────────────────────────────────────────

    def batch_mode_selected(self):
        self.enable_hbutton_group()
        if hasattr(self, '_apply_batch_action_gate'):
            self._apply_batch_action_gate()
        else:
            self.translate_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

    def manual_mode_selected(self):
        self.enable_hbutton_group()
        if hasattr(self, '_apply_batch_action_gate'):
            self._apply_batch_action_gate()
        else:
            self.translate_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

    # ─── Undo helpers ────────────────────────────────────────────

    def _show_geminiamo_unavailable_popup(self):
        """Show popup when Geminiamo is unavailable.

        Geminiamo legge i cookie di accesso dal profilo di Firefox. Se
        Firefox non e' installato la causa e' precisa e va detta: prima
        l'utente riceveva solo "non disponibile", senza capire il motivo.
        """
        from PySide6.QtWidgets import QMessageBox

        if not _firefox_is_available():
            logger.warning(
                "[GEMINIAMO] Firefox non trovato: i cookie non possono essere letti"
            )
            from app.ui.messages import Messages
            Messages.show_firefox_not_found_error(self)
            return

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Geminiamo non disponibile")
        msg_box.setText(
            "Geminiamo al momento non disponibile. Possibili cause:\n"
            "• i cookie di Firefox per gemini.google.com sono scaduti\n"
            "• non hai effettuato l'accesso in Firefox\n\n"
            "Apri Firefox, accedi a gemini.google.com e riprova, oppure "
            "scegli un traduttore basato su browser (Gemini o Dola) che "
            "non richiedono Firefox."
        )
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    def _show_geminiamo_cookie_expired_popup(self):
        """Show popup when Geminiamo cookies are expired, with retry option."""
        from PySide6.QtWidgets import QMessageBox
        from modules.api_clients.geminiamo_client import geminiamo_client
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Cookie Gemini scaduti")
        msg_box.setText(
            "I cookie di Firefox per Gemini sono scaduti.\n\n"
            "1. Apri Firefox e vai su gemini.google.com\n"
            "2. Assicurati di essere loggato\n"
            "3. Clicca 'Riprova' quando sei pronto"
        )
        retry_btn = msg_box.addButton("Riprova", QMessageBox.AcceptRole)
        skip_btn = msg_box.addButton("Usa altro modello", QMessageBox.RejectRole)
        msg_box.setDefaultButton(retry_btn)
        msg_box.exec()
        
        if msg_box.clickedButton() == retry_btn:
            logger.info("Utente ha cliccato Riprova - Reinvio richiesta Gemini")
            self.pipeline.translate_image()
        else:
            logger.info("Utente ha scelto di usare altro modello")

    def _is_geminiamo_error(self, exc: Exception) -> bool:
        """Check if the exception is a Geminiamo-specific error."""
        error_msg = str(exc).lower()
        # Check for common Geminiamo error patterns
        geminiamo_error_patterns = [
            "cookie mancanti",
            "non inizializzato",
            "geminiamo failed",
            "geminiamo saturation",
            "saturation",
            "no .har file",  # Fallback if HAR-related
        ]
        return any(pattern in error_msg for pattern in geminiamo_error_patterns)

    def push_command(self, command):
        app = QtWidgets.QApplication.instance()
        if app is not None and QtCore.QThread.currentThread() != app.thread():
            worker_signals = getattr(self.current_worker, 'signals', None)
            if worker_signals is not None and QtCore.QThread.currentThread() == worker_signals.thread():
                worker_signals.finished.connect(lambda: self.push_command(command), QtCore.Qt.SingleShotConnection)
                return
            QtCore.QTimer.singleShot(0, lambda: self.push_command(command))
            return
        logger.debug(f"[UNDO] push_command: {command.__class__.__name__}")
        if self.undo_group.activeStack():
            logger.debug(f"[UNDO] Active stack: {self.undo_group.activeStack()}, index: {self.undo_group.activeStack().index()}")
            self.undo_group.activeStack().push(command)
        else:
            logger.warning("[UNDO] No active stack for push_command!")

    # ─── Pipeline step methods ───────────────────────────────────

    def block_detect(self, load_rects: bool = True):
        self.highlight_button(0)
        self.loading.setVisible(True)
        self.disable_hbutton_group()
        self.run_threaded(self.pipeline.detect_blocks, self.pipeline.on_blk_detect_complete,
                          self.default_error_handler, self.on_block_detect_finished, load_rects)

    def ocr(self, single_block=False, use_combined_mode=False):
        """Esegue OCR con timing"""
        self.highlight_button(1)
        ocr_model = self.settings_page.get_tool_selection('ocr')
        is_geminiamo = ocr_model.lower() == 'geminiamo'
        logger.info(f"Inizio OCR - Modello: {ocr_model}")

        # Avvia il timer nella UI
        if hasattr(self, 'start_time_display'):
            self.start_time_display()

        start_time = time.time()

        try:
            # Esegui OCR tramite pipeline
            self.pipeline.OCR_image(single_block, use_combined_mode)

            end_time = time.time()
            duration = end_time - start_time

            # Ferma il timer nella UI
            if hasattr(self, 'stop_time_display'):
                self.stop_time_display()

            logger.info(f"OCR completato in {duration:.2f} secondi | Modello: {ocr_model}")
            self.on_ocr_finished()

        except Exception as e:
            # Ferma il timer nella UI in caso di errore
            if hasattr(self, 'stop_time_display'):
                self.stop_time_display()

            end_time = time.time()
            duration = end_time - start_time

            # Check if this is a Geminiamo error and show popup
            if is_geminiamo and self._is_geminiamo_error(e):
                logger.error(f"OCR Geminiamo fallito: {str(e)}")
                self._show_geminiamo_unavailable_popup()
                return  # Don't re-raise, just return to avoid crash

            logger.error(f"OCR fallito dopo {duration:.2f} secondi - Errore: {str(e)}")
            raise

    def translate_image(self, single_block=False):
        """Esegue traduzione con timing"""
        self.highlight_button(2)
        logger.info(f"Inizio traduzione - Modello: {self.settings_page.get_tool_selection('translator')}")

        # Avvia il timer nella UI
        if hasattr(self, 'start_time_display'):
            self.start_time_display()

        start_time = time.time()

        try:
            translator_model = self.settings_page.get_tool_selection('translator')

            if is_browser_site(translator_model):
                self.show_txt_modal(translator_model)
                return

            is_geminiamo = translator_model.lower() == 'geminiamo'

            max_attempts = 2 if is_geminiamo else 1
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    self.pipeline.translate_image(single_block)
                    break
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Traduzione tentativo {attempt + 1}/{max_attempts} fallito: {e}")

                    if attempt < max_attempts - 1:
                        logger.info("Ritento traduzione in 2 secondi...")
                        time.sleep(2)
                    else:
                        if is_geminiamo:
                            logger.error(f"Traduzione Geminiamo fallita dopo {max_attempts} tentativi: {e}")
                            self._show_geminiamo_unavailable_popup()
                            return
                        else:
                            raise

            end_time = time.time()
            duration = end_time - start_time

            if hasattr(self, 'stop_time_display'):
                self.stop_time_display()

            logger.info(f"Traduzione completata in {duration:.2f} secondi | Modello: {translator_model}")

        except Exception as e:
            if hasattr(self, 'stop_time_display'):
                self.stop_time_display()

            end_time = time.time()
            duration = end_time - start_time
            logger.error(f"Traduzione fallita dopo {duration:.2f} secondi - Errore: {str(e)}")
            raise

    def open_simple_gemini_browser(self, return_window=False, on_loaded=None, on_closed=None):
        """Apre semplicemente pywebview su gemini.google.com senza automazione."""
        try:
            import webview
            import tempfile
            import os

            storage_path = os.path.join(tempfile.gettempdir(), 'komictranslate_gemini')
            os.makedirs(storage_path, exist_ok=True)

            window = webview.create_window(
                "Gemini Browser",
                "https://gemini.google.com/",
                width=1100,
                height=850,
                resizable=True
            )
            self._active_gvb_window = window

            if on_loaded is not None:
                try:
                    window.events.loaded += on_loaded
                except Exception:
                    pass
            if on_closed is not None:
                try:
                    def _closed_dispatcher():
                        self._active_gvb_window = None
                        QtCore.QTimer.singleShot(0, on_closed)
                    window.events.closed += _closed_dispatcher
                except Exception:
                    pass
            webview.start(
                storage_path=storage_path,
                debug=False,
                private_mode=False,
                http_server=True,
                http_port=18766
            )
            return window if return_window else None
        except Exception as e:
            print(f"[GVB Simple] Errore: {e}")
            from app.ui.messages import Messages
            QtCore.QTimer.singleShot(0, lambda: Messages.show_error(self, "Errore Browser", f"Impossibile aprire il browser: {e}"))
            return None

    def _apply_vision_result_to_blocks(self, result):
        """Applica i risultati VisionResult ai blocchi."""
        for item in result.translations_json.items():
            block_id, translation = item
            try:
                idx = int(block_id.replace('block_', '')) - 1
                if 0 <= idx < len(self.blk_list):
                    self.blk_list[idx].translation = translation
            except (ValueError, IndexError):
                pass

    def _apply_translations_to_blocks(self, translations):
        """Applica le traduzioni dal dizionario ai blocchi."""
        for block_id, translation in translations.items():
            try:
                idx = int(block_id.replace('block_', '').replace('"', '')) - 1
                if 0 <= idx < len(self.blk_list):
                    self.blk_list[idx].translation = translation
            except (ValueError, IndexError):
                pass

    def inpaint_and_set(self):
        self.highlight_button(5)
        if self.image_viewer.hasPhoto() and self.image_viewer.has_drawn_elements():
            self.clear_text_edits()
            self.loading.setVisible(True)
            self.disable_hbutton_group()
            self.run_threaded(self.pipeline.inpaint, self.pipeline.inpaint_complete,
                              self.default_error_handler, self.on_inpaint_finished)

    def load_segmentation_points(self):
        self.highlight_button(4)
        if self.image_viewer.hasPhoto():
            self.clear_text_edits()
            self.set_tool('brush')
            self.disable_hbutton_group()
            self.image_viewer.clear_rectangles()
            self.image_viewer.clear_text_items()
            if self.blk_list:
                self.undo_group.activeStack().beginMacro('draw_segmentation_boxes')
                for blk in self.blk_list:
                    bboxes = blk.inpaint_bboxes
                    if bboxes is not None and len(bboxes) > 0:
                        self.image_viewer.draw_segmentation_lines(bboxes)
                self.undo_group.activeStack().endMacro()
                self.on_segmentation_finished()
            else:
                self.loading.setVisible(True)
                self.disable_hbutton_group()
                self.run_threaded(self.pipeline.detect_blocks, self.blk_detect_segment,
                                  self.default_error_handler, self.on_manual_finished)

    def blk_detect_segment(self, result):
        blk_list, load_rects = result
        self.blk_list = blk_list
        self.undo_group.activeStack().beginMacro('draw_segmentation_boxes')
        for blk in self.blk_list:
            bboxes = blk.inpaint_bboxes
            if bboxes is not None and len(bboxes) > 0:
                self.image_viewer.draw_segmentation_lines(bboxes)
        self.undo_group.activeStack().endMacro()

    # ─── Finish / callback helpers ───────────────────────────────

    def finish_ocr_translate(self, single_block=False):
        if self.blk_list:
            if single_block:
                rect = self.image_viewer.selected_rect
            else:
                rect = self.find_corresponding_rect(self.blk_list[0], 0.5)
            self.image_viewer.select_rectangle(rect)
        self.set_tool('pan')
        self.on_ocr_finished()

    def on_manual_finished(self):
        self.loading.setVisible(False)
        self.enable_hbutton_group()

    def on_block_detect_finished(self):
        self.loading.setVisible(False)
        self.enable_hbutton_group()
        self._play_operation_sound('rileva.wav')

    def on_ocr_finished(self):
        self.loading.setVisible(False)
        self.enable_hbutton_group()
        self._play_operation_sound('libro.wav')

    def on_translate_finished(self):
        self.loading.setVisible(False)
        self.enable_hbutton_group()
        self.set_tool('pan')
        refresh_text_edits_for_current_block(self)
        if hasattr(self, 'pan_button'):
            self.pan_button.setFocus()

    def on_segmentation_finished(self):
        self.loading.setVisible(False)
        self.enable_hbutton_group()
        self._play_operation_sound('segmenta.wav')

    def on_inpaint_finished(self):
        self.loading.setVisible(False)
        self.enable_hbutton_group()
        self._play_operation_sound('doccia.wav')

    def toggle_markers(self, checked=None):
        if not hasattr(self, "image_viewer") or not self.image_viewer:
            return
        font_size = parse_font_size(self.font_size_dropdown.currentText()) if hasattr(self, "font_size_dropdown") else 20
        visible = bool(checked) if checked is not None else (not getattr(self.image_viewer, "markers_visible", True))
        self.image_viewer.set_markers_visible(visible, font_size=font_size)
        if hasattr(self, "markers_button"):
            self.markers_button.setChecked(visible)

    def toggle_polygons(self, checked=None):
        if not hasattr(self, "image_viewer") or not self.image_viewer:
            return
        visible = bool(checked) if checked is not None else (not getattr(self.image_viewer, "polygons_visible", True))
        self.image_viewer.set_polygons_visible(visible)
        if hasattr(self, "polygons_button"):
            self.polygons_button.setChecked(visible)

    def toggle_rect_boxes(self, checked=None):
        if not hasattr(self, "image_viewer") or not self.image_viewer:
            return
        visible = bool(checked) if checked is not None else (not getattr(self.image_viewer, "rect_boxes_visible", True))
        self.image_viewer.set_rect_boxes_visible(visible)
        if hasattr(self, "rect_boxes_button"):
            self.rect_boxes_button.setChecked(visible)

    def toggle_text_boxes(self):
        """Mostra/nasconde le caselle di testo create da 'Traduci Tutto'.

        Applica lo stato di visibilità a tutte le immagini aperte nel progetto
        (``image_states``) e aggiorna l'etichetta del pulsante in modo coerente.
        """
        if not hasattr(self, "image_viewer") or not self.image_viewer:
            return
        if not hasattr(self, "toggle_text_boxes_button"):
            return

        # Determina il nuovo stato di visibilità partendo da quello corrente
        # del viewer attivo.
        text_items = getattr(self.image_viewer, "text_items", [])
        any_visible = any(
            getattr(item, "isVisible", lambda: True)() for item in text_items
        )
        new_visible = not any_visible

        # Aggiorna il viewer corrente (rende effettivamente visibili/nascosti
        # i text_items presenti).
        changed = self.image_viewer.set_text_boxes_visible(new_visible)
        if not changed and not getattr(self.image_viewer, "text_items", []):
            # Nessuna casella di testo nel viewer corrente: niente da fare.
            return

        # Persisti il flag sul viewer_state di ogni immagine aperta nel progetto
        # in modo che sia onnicomprensivo (viene rispettato al cambio immagine
        # e alla creazione di nuove caselle di testo).
        image_states = getattr(self, "image_states", {}) or {}
        image_files = getattr(self, "image_files", []) or []
        for image_path in image_files:
            state = image_states.get(image_path)
            if not state:
                continue
            viewer_state = state.setdefault("viewer_state", {})
            viewer_state["text_boxes_hidden"] = not new_visible

        # Aggiorna l'etichetta del pulsante in modo coerente con lo stato.
        if new_visible:
            self.toggle_text_boxes_button.setText(self.tr("Nascondi\nTesto"))
        else:
            self.toggle_text_boxes_button.setText(self.tr("Mostra\nTesto"))

    def sync_toggle_text_boxes_label(self):
        """Aggiorna l'etichetta del pulsante in base allo stato del viewer.

        Da chiamare dopo aver caricato una nuova immagine, in modo che l'etichetta
        del pulsante rifletta se le caselle di testo della pagina corrente sono
        nascoste o meno (lo stato è persistito in ``image_states``).
        """
        if not hasattr(self, "toggle_text_boxes_button"):
            return
        if not getattr(self, "image_viewer", None):
            return
        hidden = bool(getattr(self.image_viewer, "text_boxes_hidden", False))
        if hidden:
            self.toggle_text_boxes_button.setText(self.tr("Mostra\nTesto"))
        else:
            self.toggle_text_boxes_button.setText(self.tr("Nascondi\nTesto"))

    def show_boxes_overlays(self):
        if not getattr(self, "image_files", None) or not getattr(self, "image_states", None):
            return

        for image_path in self.image_files:
            state = self.image_states.get(image_path)
            if not state:
                continue
            viewer_state = state.get("viewer_state")
            if not viewer_state:
                continue
            viewer_state["overlays_hidden"] = False

        if hasattr(self, "pipeline") and self.pipeline and getattr(self, "blk_list", None):
            self.pipeline.load_box_coords(self.blk_list)

    # ─── Text-edit helpers ───────────────────────────────────────

    def clear_text_edits(self):
        self.curr_tblock = None
        self.curr_tblock_item = None
        self.s_text_edit.clear()
        self.t_text_edit.clear()
        if hasattr(self, "refresh_polygon_text_button_state"):
            self.refresh_polygon_text_button_state()
        if hasattr(self, "refresh_polygon_inpaint_button_state"):
            self.refresh_polygon_inpaint_button_state()

    def update_text_block(self):
        if self.curr_tblock:
            self.curr_tblock.text = self.s_text_edit.toPlainText()
            self.curr_tblock.translation = self.t_text_edit.toPlainText()

    def update_text_block_from_item(self, new_text):
        # Don't update UI elements if we're currently editing the text item
        if self.curr_tblock and (not self.curr_tblock_item or not self.curr_tblock_item.editing_mode):
            self.curr_tblock.translation = new_text
            self.t_text_edit.blockSignals(True)
            self.t_text_edit.setPlainText(new_text)
            self.t_text_edit.blockSignals(False)

    def update_text_block_from_edit(self):
        new_text = self.t_text_edit.toPlainText()
        if self.curr_tblock:
            self.curr_tblock.translation = new_text
        if self.curr_tblock_item and self.curr_tblock_item in self.image_viewer._scene.items():
            cursor_position = self.t_text_edit.textCursor().position()
            self.curr_tblock_item.set_plain_text(new_text)
            cursor = self.t_text_edit.textCursor()
            doc_length = self.t_text_edit.document().characterCount()
            safe_position = min(cursor_position, max(0, doc_length - 1))
            cursor.setPosition(safe_position)
            self.t_text_edit.setTextCursor(cursor)

    def remove_newlines_from_target(self):
        """Rimuove tutti i caratteri di a capo dal testo nel campo TARGET"""
        current_text = self.t_text_edit.toPlainText()
        cleaned_text = current_text.replace('\n', ' ').replace('\r', '')
        cleaned_text = ' '.join(cleaned_text.split())
        self.t_text_edit.blockSignals(True)
        self.t_text_edit.setPlainText(cleaned_text)
        self.t_text_edit.blockSignals(False)
        if self.curr_tblock:
            self.curr_tblock.translation = cleaned_text
        if self.curr_tblock_item and self.curr_tblock_item in self.image_viewer._scene.items():
            self.curr_tblock_item.set_plain_text(cleaned_text)

    # ─── Rectangle / text-block lookup ───────────────────────────

    def find_corresponding_text_block(self, rect: Tuple[float], iou_threshold: int = 0.5):
        for blk in self.blk_list:
            if do_rectangles_overlap(rect, blk.xyxy, iou_threshold):
                return blk
        return None

    def find_corresponding_rect(self, tblock: TextBlock, iou_threshold: int):
        for rect in self.image_viewer.rectangles:
            mp_rect = rect.mapRectToScene(rect.rect())
            x1, y1, w, h = mp_rect.getRect()
            rect_coord = (x1, y1, x1 + w, y1 + h)
            if do_rectangles_overlap(rect_coord, tblock.xyxy, iou_threshold):
                return rect
        return None

    # ─── Rectangle event handlers ────────────────────────────────

    def handle_rectangle_selection(self, rect: QRectF):
        rect = rect.getCoords()
        self.curr_tblock = self.find_corresponding_text_block(rect, 0.5)
        if self.curr_tblock:
            self.s_text_edit.blockSignals(True)
            self.t_text_edit.blockSignals(True)
            self.s_text_edit.setPlainText(self.curr_tblock.text)
            self.t_text_edit.setPlainText(self.curr_tblock.translation)
            self.s_text_edit.blockSignals(False)
            self.t_text_edit.blockSignals(False)
        else:
            self.s_text_edit.clear()
            self.t_text_edit.clear()
            self.curr_tblock = None
        if hasattr(self, "refresh_polygon_text_button_state"):
            self.refresh_polygon_text_button_state()
        if hasattr(self, "refresh_polygon_inpaint_button_state"):
            self.refresh_polygon_inpaint_button_state()

    def handle_rectangle_creation(self, rect_item: MoveableRectItem):
        new_rect = rect_item.mapRectToScene(rect_item.rect())
        x1, y1, w, h = new_rect.getRect()
        x1, y1, w, h = int(x1), int(y1), int(w), int(h)
        new_rect_coords = (x1, y1, x1 + w, y1 + h)
        image = self.image_viewer.get_cv2_image()
        inpaint_boxes = get_inpaint_bboxes(new_rect_coords, image)
        # Extract polygon using Detect's exact same logic
        polygon_points = extract_bubble_polygon(image, new_rect_coords)
        # Fallback to simple rectangle if bubble polygon extraction fails
        if polygon_points is None:
            polygon_points = np.array([
                [x1, y1],
                [x1 + w, y1],
                [x1 + w, y1 + h],
                [x1, y1 + h]
            ], dtype=np.int32)
        new_blk = TextBlock(text_bbox=np.array(new_rect_coords), inpaint_bboxes=inpaint_boxes, polygon_points=polygon_points, segm_pts=polygon_points, bubble_xyxy=np.array(new_rect_coords))
        self.blk_list.append(new_blk)
        rect_item.text_block = new_blk  # Set text_block on rect_item first
        self.connect_rect_item_signals(rect_item)
        command = AddRectangleCommand(self, rect_item, new_blk, self.blk_list)
        self.undo_group.activeStack().push(command)
        self._schedule_save_current_image_state(100)

    def handle_rectangle_deletion(self, rect: QRectF):
        rect_coords = rect.getCoords()

        current_text_block = self.find_corresponding_text_block(rect_coords, 0.5)

        if current_text_block is None:
            current_text_block = self.find_corresponding_text_block(rect_coords, 0.1)

        if current_text_block is None:
            min_dist = float('inf')
            closest_blk = None
            rc_x = (rect_coords[0] + rect_coords[2]) / 2
            rc_y = (rect_coords[1] + rect_coords[3]) / 2
            for blk in self.blk_list:
                blk_x = (blk.xyxy[0] + blk.xyxy[2]) / 2
                blk_y = (blk.xyxy[1] + blk.xyxy[3]) / 2
                dist = ((rc_x - blk_x)**2 + (rc_y - blk_y)**2)**0.5
                if dist < BLOCK_MATCH_DIST_THRESHOLD and dist < min_dist:
                    min_dist = dist
                    closest_blk = blk
            if closest_blk:
                current_text_block = closest_blk

        if current_text_block is not None:
            try:
                if current_text_block in self.blk_list:
                    self.blk_list.remove(current_text_block)
                    self._schedule_save_current_image_state(150)  # Sostituisce il salvataggio sincrono con debounce
            except ValueError:
                pass
        else:
            logger.warning(f"[BLK_LIST_UPDATE] IMPOSSIBILE rimuovere blocco per le coordinate {rect_coords}")
    def handle_rectangle_change(self, new_rect: QRectF, angle: float, tr_origin: Tuple, local_rect: QRectF = None):
        modified = False
        matched_blk = None
        for blk in self.blk_list:
            if do_rectangles_overlap(blk.xyxy,
                                     (new_rect.left(), new_rect.top(), new_rect.right(), new_rect.bottom()), 0.2):
                # Memorizza le dimensioni originali per rilevare il ridimensionamento
                old_width = blk.xyxy[2] - blk.xyxy[0]
                old_height = blk.xyxy[3] - blk.xyxy[1]
                
                blk.xyxy[:] = [int(new_rect.left()), int(new_rect.top()),
                               int(new_rect.right()), int(new_rect.bottom())]
                blk.angle = angle if angle else 0
                if tr_origin:
                    # Gestisce sia Tuple che QPointF
                    if hasattr(tr_origin, 'x'):
                        blk.tr_origin_point = (tr_origin.x(), tr_origin.y())
                    else:
                        blk.tr_origin_point = (tr_origin[0], tr_origin[1])
                else:
                    blk.tr_origin_point = ()
                
                # Se abbiamo il local_rect, usiamolo per le dimensioni reali (importante per l'ellisse)
                if local_rect:
                    blk.width = int(local_rect.width())
                    blk.height = int(local_rect.height())
                
                # Controlla se è avvenuto un ridimensionamento (cambio dimensioni)
                new_width = blk.xyxy[2] - blk.xyxy[0]
                new_height = blk.xyxy[3] - blk.xyxy[1]
                if old_width != new_width or old_height != new_height:
                    # Rimuovi caratteri di a capo dal testo target
                    if hasattr(blk, 'translation') and blk.translation:
                        blk.translation = blk.translation.replace('\n', ' ').replace('\r', ' ')
                
                modified = True
                matched_blk = blk
                break

        # Debounce: il calcolo pesante (get_cv2_image + get_inpaint_bboxes) viene differito
        # Il timer viene resettato ad ogni pixel di movimento, eseguendo solo quando il drag si ferma
        if modified:
            self._rect_change_debounce_stop(matched_blk)
            self._schedule_save_current_image_state(IMAGE_STATE_SAVE_DELAY_MS)

    def _rect_change_debounce_stop(self, blk):
        """Debounce per il calcolo pesante post-drag. Eseguito solo quando il mouse si ferma."""
        timer = getattr(self, '_rect_change_timer', None)
        if timer is not None:
            timer.stop()
        else:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._apply_deferred_inpaint_calc())
            self._rect_change_timer = timer
        self._pending_inpaint_blk = blk
        timer.start(100)  # 100ms debounce dopo l'ultimo movimento

    def _apply_deferred_inpaint_calc(self):
        """Esegue il calcolo delle inpaint bboxes differito dal debounce."""
        blk = getattr(self, '_pending_inpaint_blk', None)
        if blk is None:
            return
        self._pending_inpaint_blk = None
        try:
            image = self.image_viewer.get_cv2_image()
            # Se l'utente ha allargato il rettangolo oltre il bubble rilevato,
            # allarga anche il bubble: altrimenti ricalcolo e cleaning futuro
            # riclipperebbero tutto alle vecchie dimensioni.
            try:
                nx1, ny1, nx2, ny2 = [int(v) for v in blk.xyxy]
                cur = getattr(blk, 'bubble_xyxy', None)
                if cur is not None:
                    cx1, cy1, cx2, cy2 = [int(v) for v in cur]
                    if nx1 < cx1 or ny1 < cy1 or nx2 > cx2 or ny2 > cy2:
                        import numpy as _np
                        blk.bubble_xyxy = _np.array(
                            [min(nx1, cx1), min(ny1, cy1),
                             max(nx2, cx2), max(ny2, cy2)])
                elif nx1 < nx2 and ny1 < ny2:
                    import numpy as _np
                    blk.bubble_xyxy = _np.array([nx1, ny1, nx2, ny2])
            except (TypeError, ValueError):
                pass
            bubble_bbox = (
                blk.get_active_inpaint_bbox() if hasattr(blk, "get_active_inpaint_bbox") else getattr(blk, 'bubble_xyxy', None)
            )
            bubble_polygon = (
                blk.get_active_inpaint_polygon() if hasattr(blk, "get_active_inpaint_polygon") else getattr(blk, 'polygon_points', None)
            )
            inpaint_bboxes = get_inpaint_bboxes(
                blk.xyxy,
                image,
                bubble_bbox,
                bubble_polygon,
            )
            blk.inpaint_bboxes = inpaint_bboxes
        except Exception as e:
            logger.debug(f"Errore nel calcolo inpaint differito: {e}")

    def rect_change_undo(self, old_state, new_state):
        if (old_state is not None and new_state is not None and 
            hasattr(old_state, 'rect') and hasattr(new_state, 'rect')):
            command = BoxesChangeCommand(self.image_viewer, old_state, new_state, self.blk_list)
            self.undo_group.activeStack().push(command)

    def delete_selected_box(self):
        """Elimina le caselle di testo selezionate in modo istantaneo.
        
        Il salvataggio dello stato viene differito per non bloccare l'interfaccia.
        """
        if len(self.selected_text_items) > 1:
            # Build blk→rect lookup for O(1) access
            blk_to_rect = {}
            for rect in self.image_viewer.rectangles:
                if rect.blk:
                    blk_to_rect[id(rect.blk)] = rect
            rect_items = []
            text_items = []
            blks = []
            for text_item in self.selected_text_items:
                text_items.append(text_item)
                blk = getattr(text_item, 'blk', None)
                if blk:
                    blks.append(blk)
                    rect = blk_to_rect.get(id(blk))
                    if rect:
                        rect_items.append(rect)
            command = DeleteMultipleBoxesCommand(
                self, rect_items, text_items, blks, self.blk_list,
                defer_update=True)
            self.undo_group.activeStack().push(command)
            # Salvataggio differito con delay maggiore per evitare blocchi
            self._schedule_save_current_image_state(500)
        elif self.curr_tblock or self.curr_tblock_item:
            command = DeleteBoxesCommand(
                self, self.image_viewer.selected_rect,
                self.curr_tblock_item, self.curr_tblock, self.blk_list,
                defer_update=True)
            self.undo_group.activeStack().push(command)
            # Salvataggio differito con delay maggiore per evitare blocchi
            self._schedule_save_current_image_state(500)
        elif self.statusBar():
            self.statusBar().showMessage(
                self.tr("Nessun elemento selezionato per l'eliminazione"),
                2000)

    # ─── Text-item selection ─────────────────────────────────────

    def _link_text_items_to_blocks(self):
        """Associa ogni text_item al suo blk corrispondente per il recupero source/target."""
        if not hasattr(self, 'blk_list') or not self.blk_list:
            return
        if not hasattr(self, 'image_viewer') or not self.image_viewer:
            return

        for text_item in self.image_viewer.text_items:
            if text_item is None:
                continue
            text_item.blk = None

            linked_block_id = getattr(text_item, 'linked_block_id', None)
            if linked_block_id:
                for blk in self.blk_list:
                    if getattr(blk, 'block_id', None) == linked_block_id:
                        text_item.blk = blk
                        break
                if text_item.blk is not None:
                    continue

            x1, y1 = int(text_item.pos().x()), int(text_item.pos().y())
            rotation = text_item.rotation()

            tolerance = BLOCK_MATCH_TOLERANCE_PX
            best_match = None
            best_distance = float('inf')

            for blk in self.blk_list:
                if blk and hasattr(blk, 'xyxy') and blk.xyxy is not None:
                    blk_x, blk_y = int(blk.xyxy[0]), int(blk.xyxy[1])
                    blk_angle = getattr(blk, 'angle', 0.0)
                    distance = ((blk_x - x1) ** 2 + (blk_y - y1) ** 2) ** 0.5
                    angle_diff = abs(blk_angle - rotation)
                    if distance <= tolerance and angle_diff <= TEXT_ITEM_ANGLE_TOLERANCE_DEG:
                        if distance < best_distance:
                            best_distance = distance
                            best_match = blk

            if best_match:
                text_item.blk = best_match

    def on_text_item_deselcted(self):
        self.clear_text_edits()

    def on_text_item_selected(self, text_item, multi_select=False):
        if multi_select:
            if text_item in self.selected_text_items:
                self.selected_text_items.remove(text_item)
                text_item.set_multi_selected(False)
            else:
                self.selected_text_items.append(text_item)
                text_item.set_multi_selected(True)
            self.update_ui_for_multi_selection()
            return

        self.clear_multi_selection()
        self.curr_tblock_item = text_item
        self._selection_update_token = getattr(self, '_selection_update_token', 0) + 1

        if hasattr(text_item, 'blk') and text_item.blk is not None:
            self.curr_tblock = text_item.blk
        else:
            self.curr_tblock = None
        if hasattr(self, "refresh_polygon_text_button_state"):
            self.refresh_polygon_text_button_state()

        token = self._selection_update_token
        QtCore.QTimer.singleShot(0, lambda: self._delayed_selection_update(text_item, token))

    def _delayed_selection_update(self, text_item, token=None):
        if token is not None and token != getattr(self, '_selection_update_token', None):
            return
        try:
            if text_item is None or text_item.scene() is None:
                return
        except RuntimeError:
            return

        x1, y1 = int(text_item.pos().x()), int(text_item.pos().y())
        rotation = text_item.rotation()

        if self.curr_tblock is None and self.blk_list:
            tolerance = BLOCK_MATCH_TOLERANCE_PX
            best_match = None
            best_distance = float('inf')

            for blk in self.blk_list:
                if blk and hasattr(blk, 'xyxy') and blk.xyxy is not None:
                    blk_x, blk_y = int(blk.xyxy[0]), int(blk.xyxy[1])
                    blk_angle = getattr(blk, 'angle', 0.0)
                    distance = ((blk_x - x1) ** 2 + (blk_y - y1) ** 2) ** 0.5
                    angle_diff = abs(blk_angle - rotation)
                    if distance <= tolerance and angle_diff <= TEXT_ITEM_ANGLE_TOLERANCE_DEG:
                        if distance < best_distance:
                            best_distance = distance
                            best_match = blk

            if best_match:
                text_item.blk = best_match
                self.curr_tblock = best_match

        if self.curr_tblock is None and self.blk_list:
            plain_text = text_item.toPlainText()
            for blk in self.blk_list:
                if blk and hasattr(blk, 'translation') and blk.translation == plain_text:
                    self.curr_tblock = blk
                    break

        source_text = getattr(self.curr_tblock, 'text', '') if self.curr_tblock else ''
        translation_text = getattr(self.curr_tblock, 'translation', '') if self.curr_tblock else ''

        self.s_text_edit.blockSignals(True)
        self.t_text_edit.blockSignals(True)
        self.s_text_edit.setPlainText(source_text)
        self.t_text_edit.setPlainText(translation_text)
        self.s_text_edit.blockSignals(False)
        self.t_text_edit.blockSignals(False)

        self.set_values_for_blk_item(text_item)
        if hasattr(self, "refresh_polygon_text_button_state"):
            self.refresh_polygon_text_button_state()
        if hasattr(self, "refresh_polygon_inpaint_button_state"):
            self.refresh_polygon_inpaint_button_state()

    def clear_multi_selection(self):
        for item in self.selected_text_items:
            try:
                if item and hasattr(item, 'set_multi_selected'):
                    item.set_multi_selected(False)
            except RuntimeError:
                # L'oggetto C++ sottostante è già stato eliminato (es. cambio pagina)
                pass
        self.selected_text_items.clear()

    def select_all_text_items(self):
        """Seleziona in multi-selezione tutte le caselle di testo rilevate.

        Equivalente a fare CTRL+click su ogni casella, ma in un colpo solo.
        Seleziona solo i TextBlockItem ancora vivi e che hanno un blocco
        effettivamente rilevato (blk con coordinate valide): le caselle
        "vuote" non hanno nulla su cui operare.
        """
        try:
            from app.ui.canvas.text_item import TextBlockItem
        except Exception:
            return 0

        self.clear_multi_selection()

        if not self.image_viewer.hasPhoto():
            return 0

        candidates = []
        for item in self.image_viewer.text_items:
            try:
                if not isinstance(item, TextBlockItem):
                    continue
                blk = getattr(item, 'blk', None)
                if blk is None or getattr(blk, 'xyxy', None) is None:
                    continue
                if len(blk.xyxy) < 4:
                    continue
                if item.scene() is None:
                    continue
            except RuntimeError:
                # oggetto C++ gia' eliminato (cambio pagina)
                continue
            candidates.append(item)

        for item in candidates:
            try:
                if item in self.selected_text_items:
                    continue
                self.selected_text_items.append(item)
                item.set_multi_selected(True)
            except RuntimeError:
                continue

        self.update_ui_for_multi_selection()
        logger.info(
            f"[MULTI-SELECT] 'Seleziona tutte': {len(self.selected_text_items)} caselle"
        )
        return len(self.selected_text_items)

    def update_ui_for_multi_selection(self):
        count = len(self.selected_text_items)
        # Blocca i segnali per evitare che la stringa di conteggio sovrascriva il testo dei blocchi
        self.s_text_edit.blockSignals(True)
        self.t_text_edit.blockSignals(True)
        
        if count > 1:
            self.s_text_edit.setPlainText(f"[{count} caselle selezionate]")
            self.t_text_edit.setPlainText(f"[{count} caselle selezionate]")
        elif count == 0:
            self.s_text_edit.clear()
            self.t_text_edit.clear()
            
        self.s_text_edit.blockSignals(False)
        self.t_text_edit.blockSignals(False)
        
        # Se siamo in multi-selezione, non vogliamo che ci sia un blocco corrente attivo per l'editing
        if count > 0:
            self.curr_tblock = None
            self.curr_tblock_item = None
        if hasattr(self, "refresh_polygon_text_button_state"):
            self.refresh_polygon_text_button_state()
        if hasattr(self, "refresh_polygon_inpaint_button_state"):
            self.refresh_polygon_inpaint_button_state()

    # ─── Text rendering (on_blk_rendered + render_text) ──────────

    def on_blk_rendered(self, text: str, font_size: int, blk: TextBlock):
        if not self.image_viewer.hasPhoto():
            logger.warning("No main image to add to.")
            return

        target_lang = self.lang_mapping.get(self.t_combo.currentText(), None)
        trg_lng_cd = get_language_code(target_lang)
        if any(lang in trg_lng_cd.lower() for lang in ['zh', 'ja', 'th']):
            text = text.replace(' ', '')

        render_settings = self.render_settings()
        font_family = render_settings.font_family

        # Usa il colore del font rilevato dal TextBlock se disponibile
        if blk.font_color and blk.font_color.strip():
            text_color = QColor(blk.font_color)
        else:
            text_color_str = render_settings.color
            text_color = QColor(text_color_str)

        alignment = Qt.AlignmentFlag.AlignCenter
        line_spacing = float(render_settings.line_spacing)
        outline_color_str = render_settings.outline_color
        outline_color = QColor(outline_color_str) if self.outline_enabled else None
        text_width = str(render_settings.outline_width).strip()
        try:
            outline_width = float(text_width)
        except ValueError:
            outline_width = 0.0
        bold = render_settings.bold
        italic = render_settings.italic
        underline = render_settings.underline
        direction = render_settings.direction

        text_item = TextBlockItem(text, self.image_viewer.photo, font_family,
                                  font_size, text_color, alignment, line_spacing,
                                  outline_color, outline_width, bold, italic, underline, direction)
        text_item.detected_text_color = getattr(blk, "detected_text_color", getattr(blk, "font_color", "")) or ""
        text_item.detected_text_color_data = getattr(blk, "detected_text_color_data", None)
        
        # Imposta la posizione iniziale del text item
        text_item.setPos(blk.xyxy[0], blk.xyxy[1])
        text_item.set_plain_text(text)
        
        # Aggiungi il riferimento al blocco per la centratura automatica
        text_item.blk = blk

        self.image_viewer._scene.addItem(text_item)
        text_item.setZValue(TEXT_BOX_Z)
        self.image_viewer.text_items.append(text_item)
        # Get font size from dropdown for markers
        font_size = parse_font_size(self.font_size_dropdown.currentText())
        self.image_viewer.update_all_markers(font_size=font_size)
        self.connect_text_item_signals(text_item)

        # Rispetta lo stato "Hide text boxes" corrente: le nuove caselle
        # generate da "Traduci Tutto" restano nascoste se l'utente ha già
        # attivato la modalità di nascondimento.
        if getattr(self.image_viewer, "text_boxes_hidden", False):
            text_item.setVisible(False)

        # Il pulsante "Nascondi/Mostra Caselle di testo" si attiva solo
        # dopo che "Traduci Tutto" ha effettivamente creato le caselle.
        if hasattr(self, "toggle_text_boxes_button"):
            self.toggle_text_boxes_button.setEnabled(True)
            # L'etichetta deve riflettere lo stato corrente di visibilità.
            if getattr(self.image_viewer, "text_boxes_hidden", False):
                self.toggle_text_boxes_button.setText(self.tr("Mostra\nTesto"))
            else:
                self.toggle_text_boxes_button.setText(self.tr("Nascondi\nTesto"))

        # Centratura automatica intelligente
        try:
            # Calcola il centro del blocco
            x1, y1, x2, y2 = blk.xyxy
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            # Ottieni le dimensioni del testo renderizzato
            text_rect = text_item.boundingRect()
            
            # Calcola la nuova posizione centrata
            new_x = center_x - text_rect.width() / 2
            new_y = center_y - text_rect.height() / 2
            
            # Applica la centratura
            text_item.setPos(new_x, new_y)

        except Exception as e:
            # In caso di errore, mantieni la posizione originale
            pass

        item_key = f"text_item_{len(self.text_items)}"
        self.text_items[item_key] = text_item

    def on_render_complete(self, rendered_image: np.ndarray):
        self.loading.setVisible(False)
        self.enable_hbutton_group()
        self.undo_group.activeStack().endMacro()
        if hasattr(self, 'curr_img_idx') and self.curr_img_idx >= 0:
            self._schedule_save_current_image_state(100)
        self._play_operation_sound('render.wav')
        self.alignment_tool_group.get_button_group().buttons()[1].setChecked(True)

    def render_text(self):
        self.highlight_button(6)
        if self.image_viewer.hasPhoto() and self.blk_list:
            self.set_tool(None)
            if not font_selected(self):
                return
            self.clear_text_edits()
            self.image_viewer.clear_text_item_markers()  # Clear markers before render
            self.loading.setVisible(True)
            self.disable_hbutton_group()

            for item in self.image_viewer.text_items:
                if item not in self.image_viewer._scene.items():
                    self.image_viewer._scene.addItem(item)

            existing_text_items = {item: (int(item.pos().x()), int(item.pos().y()), item.rotation())
                                   for item in self.image_viewer.text_items}
            new_blocks = [
                blk for blk in self.blk_list
                if (int(blk.xyxy[0]), int(blk.xyxy[1]), blk.angle) not in existing_text_items.values()
            ]

            self.image_viewer.clear_rectangles()
            self.curr_tblock = None
            self.curr_tblock_item = None

            render_settings = self.render_settings()
            upper = render_settings.upper_case
            line_spacing = float(self.line_spacing_dropdown.currentText())
            font_family = self.font_dropdown.currentText()
            text = self.outline_width_dropdown.currentText().strip()
            try:
                outline_width = float(text)
            except ValueError:
                outline_width = 0.0
            bold = render_settings.bold
            italic = render_settings.italic
            underline_val = render_settings.underline

            target_lang = self.t_combo.currentText()
            target_lang_en = self.lang_mapping.get(target_lang, None)
            trg_lng_cd = get_language_code(target_lang_en)
            format_translations(self.blk_list, trg_lng_cd, upper_case=upper)
            min_font_size = self.settings_page.get_min_font_size()
            max_font_size = self.settings_page.get_max_font_size()
            align_id = render_settings.alignment_id
            alignment = self.button_to_alignment[align_id]
            direction = render_settings.direction

            self.undo_group.activeStack().beginMacro('text_items_rendered')
            self.run_threaded(manual_wrap, self.on_render_complete, self.default_error_handler,
                              None, self, new_blocks, font_family, line_spacing, outline_width,
                              bold, italic, underline_val, alignment, direction, max_font_size,
                              min_font_size)

    # ─── Text-formatting apply methods ───────────────────────────

    def apply_bold_to_selected(self, state):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_bold(state)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_bold(state)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    def apply_italic_to_selected(self, state):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_italic(state)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_italic(state)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    def apply_underline_to_selected(self, state):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_underline(state)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_underline(state)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    def apply_color_to_selected(self, color):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_color(color)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_color(color)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    def apply_font_to_selected(self, font_family):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                font_size = parse_font_size(self.font_size_dropdown.currentText())
                item.set_font(font_family, font_size)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            font_size = parse_font_size(self.font_size_dropdown.currentText())
            self.curr_tblock_item.set_font(font_family, font_size)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    def apply_font_size_to_selected(self, font_size):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_font_size(font_size)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_font_size(font_size)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)
        # Update markers with new font size
        self.image_viewer.update_all_markers(font_size=font_size)

    def apply_alignment_to_selected(self, alignment):
        # Mappa Qt.AlignmentFlag alle stringhe PIL
        qt_to_pil_alignment = {
            QtCore.Qt.AlignmentFlag.AlignLeft: 'left',
            QtCore.Qt.AlignmentFlag.AlignCenter: 'center',
            QtCore.Qt.AlignmentFlag.AlignRight: 'right',
            QtCore.Qt.AlignmentFlag.AlignJustify: 'left',  # PIL non supporta justify
        }
        
        pil_alignment = qt_to_pil_alignment.get(alignment, 'center')
        
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_alignment(alignment)
                # Aggiorna anche blk.alignment se esiste
                if hasattr(item, 'blk') and item.blk:
                    item.blk.alignment = pil_alignment
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_alignment(alignment)
            # Aggiorna anche blk.alignment se esiste
            if hasattr(self.curr_tblock_item, 'blk') and self.curr_tblock_item.blk:
                self.curr_tblock_item.blk.alignment = pil_alignment
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    def apply_line_spacing_to_selected(self, spacing):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_line_spacing(spacing)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_line_spacing(spacing)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    def apply_outline_to_selected(self, color, width):
        if len(self.selected_text_items) > 1:
            old_items = [copy.copy(item) for item in self.selected_text_items]
            for item in self.selected_text_items:
                item.set_outline(color, width)
            new_items = [copy.copy(item) for item in self.selected_text_items]
            command = MultipleTextFormatCommand(self.image_viewer, old_items, new_items)
            self.undo_group.activeStack().push(command)
        elif self.curr_tblock_item:
            old_item = copy.copy(self.curr_tblock_item)
            self.curr_tblock_item.set_outline(color, width)
            command = TextFormatCommand(self.image_viewer, old_item, self.curr_tblock_item)
            self.undo_group.activeStack().push(command)

    # ─── Font/style change handlers (UI event → apply) ───────────

    def on_font_dropdown_change(self, font_family):
        self.apply_font_to_selected(font_family)

    def on_font_size_change(self, font_size):
        self.apply_font_size_to_selected(parse_font_size(font_size))

    def on_line_spacing_change(self, line_spacing):
        self.apply_line_spacing_to_selected(float(line_spacing))

    def on_font_color_change(self):
        font_color = self.get_color()
        if font_color and font_color.isValid():
            self.block_font_color_button.setStyleSheet(
                f"background-color: {font_color.name()}; border: none; border-radius: 5px;")
            self.block_font_color_button.setProperty('selected_color', font_color.name())
            self.apply_color_to_selected(font_color)

    def left_align(self):
        self.apply_alignment_to_selected(QtCore.Qt.AlignmentFlag.AlignLeft)

    def center_align(self):
        self.apply_alignment_to_selected(QtCore.Qt.AlignmentFlag.AlignCenter)

    def right_align(self):
        self.apply_alignment_to_selected(QtCore.Qt.AlignmentFlag.AlignRight)

    def justify_align(self):
        self.apply_alignment_to_selected(QtCore.Qt.AlignmentFlag.AlignJustify)

    def bold(self):
        current_state = self.curr_tblock_item.bold if self.curr_tblock_item else False
        self.apply_bold_to_selected(not current_state)

    def italic(self):
        current_state = self.curr_tblock_item.italic if self.curr_tblock_item else False
        self.apply_italic_to_selected(not current_state)

    def underline(self):
        current_state = self.curr_tblock_item.underline if self.curr_tblock_item else False
        self.apply_underline_to_selected(not current_state)

    def on_outline_color_change(self):
        outline_color = self.get_color()
        if outline_color and outline_color.isValid():
            self.outline_font_color_button.setStyleSheet(
                f"background-color: {outline_color.name()}; border: none; border-radius: 5px;")
            self.outline_font_color_button.setProperty('selected_color', outline_color.name())
            self.outline_enabled = getattr(self, 'outline_enabled', True)
            if self.outline_enabled:
                outline_width = float(self.outline_width_dropdown.currentText())
                self.apply_outline_to_selected(outline_color, outline_width)

    def on_outline_width_change(self, outline_width):
        self.outline_enabled = getattr(self, 'outline_enabled', True)
        if self.outline_enabled:
            text = self.outline_width_dropdown.currentText().strip()
            
            try:
                outline_width = float(text)
            except ValueError:
                outline_width = 0.0
                
            color_str = self.outline_font_color_button.property('selected_color')
            color = QColor(color_str)
            self.apply_outline_to_selected(color, outline_width)

    def toggle_outline_settings(self):
        self.outline_enabled = not getattr(self, 'outline_enabled', True)
        if not self.outline_enabled:
            self.apply_outline_to_selected(None, None)
        else:
            outline_width = float(self.outline_width_dropdown.currentText())
            color_str = self.outline_font_color_button.property('selected_color')
            color = QColor(color_str)
            self.apply_outline_to_selected(color, outline_width)

    # ─── Widget signal blocking helpers ──────────────────────────

    def block_text_item_widgets(self, widgets):
        for widget in widgets:
            widget.blockSignals(True)
        self.bold_button.clicked.disconnect(self.bold)
        self.italic_button.clicked.disconnect(self.italic)
        self.underline_button.clicked.disconnect(self.underline)
        self.alignment_tool_group.get_button_group().buttons()[0].clicked.disconnect(self.left_align)
        self.alignment_tool_group.get_button_group().buttons()[1].clicked.disconnect(self.center_align)
        self.alignment_tool_group.get_button_group().buttons()[2].clicked.disconnect(self.right_align)
        self.alignment_tool_group.get_button_group().buttons()[3].clicked.disconnect(self.justify_align)

    def unblock_text_item_widgets(self, widgets):
        for widget in widgets:
            widget.blockSignals(False)
        self.bold_button.clicked.connect(self.bold)
        self.italic_button.clicked.connect(self.italic)
        self.underline_button.clicked.connect(self.underline)
        self.alignment_tool_group.get_button_group().buttons()[0].clicked.connect(self.left_align)
        self.alignment_tool_group.get_button_group().buttons()[1].clicked.connect(self.center_align)
        self.alignment_tool_group.get_button_group().buttons()[2].clicked.connect(self.right_align)
        self.alignment_tool_group.get_button_group().buttons()[3].clicked.connect(self.justify_align)

    def color_to_string(self, color):
        if hasattr(color, 'name'):
            return color.name()
        elif isinstance(color, str):
            return color
        else:
            return '#000000'

    def set_values_for_blk_item(self, text_item: TextBlockItem):
        self.block_text_item_widgets(self.widgets_to_block)
        try:
            self.font_dropdown.setCurrentText(text_item.font_family)
            self.font_size_dropdown.setCurrentText(format_font_size(text_item.font_size))
            self.line_spacing_dropdown.setCurrentText(str(text_item.line_spacing))

            text_color_str = self.color_to_string(text_item.text_color)
            self.block_font_color_button.setStyleSheet(
                f"background-color: {text_color_str}; border: none; border-radius: 5px;")
            self.block_font_color_button.setProperty('selected_color', text_color_str)

            if text_item.outline_color is not None:
                outline_color_str = self.color_to_string(text_item.outline_color)
                self.outline_font_color_button.setStyleSheet(
                    f"background-color: {outline_color_str}; border: none; border-radius: 5px;")
                self.outline_font_color_button.setProperty('selected_color', outline_color_str)
            else:
                self.outline_font_color_button.setStyleSheet(
                    "background-color: white; border: none; border-radius: 5px;")
                self.outline_font_color_button.setProperty('selected_color', '#ffffff')

            self.outline_width_dropdown.setCurrentText(str(text_item.outline_width))
            # outline_button is now momentary, no checked state
            self.outline_enabled = text_item.outline
            # self.bold_button.setChecked(text_item.bold)
            # self.italic_button.setChecked(text_item.italic)
            # self.underline_button.setChecked(text_item.underline)

            alignment_to_button = {
                QtCore.Qt.AlignmentFlag.AlignLeft: 0,
                QtCore.Qt.AlignmentFlag.AlignCenter: 1,
                QtCore.Qt.AlignmentFlag.AlignRight: 2,
                QtCore.Qt.AlignmentFlag.AlignJustify: 3,
            }
            alignment = text_item.alignment
            button_group = self.alignment_tool_group.get_button_group()
            if alignment in alignment_to_button:
                button_group.buttons()[alignment_to_button[alignment]].setChecked(True)
        finally:
            self.unblock_text_item_widgets(self.widgets_to_block)

    def set_values_from_highlight(self, item_highlighted=None):
        # Il blocco dei segnali deve essere annullato SEMPRE. Prima le letture
        # di item_highlighted erano FUORI dal try/finally: con il default
        # None (o un dict incompleto) l IndexError/TypeError propagava e
        # unblock_text_item_widgets non veniva mai chiamato, lasciando
        # font/colore/bold/allineamento disconnessi per tutta la sessione.
        self.block_text_item_widgets(self.widgets_to_block)
        try:
            if not item_highlighted:
                return
            font_family = item_highlighted['font_family']
            font_size = item_highlighted['font_size']
            text_color = item_highlighted['text_color']
            outline_color = item_highlighted['outline_color']
            outline_width = item_highlighted['outline_width']
            outline = item_highlighted['outline']
            bold_val = item_highlighted['bold']
            italic_val = item_highlighted['italic']
            underline_val = item_highlighted['underline']
            alignment = item_highlighted['alignment']
            self.font_dropdown.setCurrentText(font_family) if font_family else None
            self.font_size_dropdown.setCurrentText(format_font_size(font_size)) if font_size else None
            if text_color is not None:
                self.block_font_color_button.setStyleSheet(
                    f"background-color: {text_color}; border: none; border-radius: 5px;")
                self.block_font_color_button.setProperty('selected_color', text_color)
            if outline_color is not None:
                self.outline_font_color_button.setStyleSheet(
                    f"background-color: {outline_color}; border: none; border-radius: 5px;")
                self.outline_font_color_button.setProperty('selected_color', outline_color)
            else:
                self.outline_font_color_button.setStyleSheet(
                    "background-color: white; border: none; border-radius: 5px;")
                self.outline_font_color_button.setProperty('selected_color', '#ffffff')
            self.outline_width_dropdown.setCurrentText(str(outline_width)) if outline_width else None
            # outline_button is now momentary, no checked state
            self.outline_enabled = outline
            # self.bold_button.setChecked(bold_val)
            # self.italic_button.setChecked(italic_val)
            # self.underline_button.setChecked(underline_val)
            alignment_to_button = {
                QtCore.Qt.AlignmentFlag.AlignLeft: 0,
                QtCore.Qt.AlignmentFlag.AlignCenter: 1,
                QtCore.Qt.AlignmentFlag.AlignRight: 2,
                QtCore.Qt.AlignmentFlag.AlignJustify: 3,
            }
            button_group = self.alignment_tool_group.get_button_group()
            if alignment in alignment_to_button:
                button_group.buttons()[alignment_to_button[alignment]].setChecked(True)
        finally:
            self.unblock_text_item_widgets(self.widgets_to_block)

    # ─── Language save helpers ───────────────────────────────────

    def save_src_trg(self):
        source_lang = self.s_combo.currentText()
        target_lang = self.t_combo.currentText()
        if self.curr_img_idx >= 0 and self.image_files and self.curr_img_idx < len(self.image_files):
            current_file = self.image_files[self.curr_img_idx]
            if current_file not in self.image_states:
                self.image_states[current_file] = {
                    'viewer_state': {}, 'source_lang': source_lang,
                    'target_lang': target_lang, 'brush_strokes': [],
                    'blk_list': [], 'text_items_data': []
                }
            else:
                self.image_states[current_file]['source_lang'] = source_lang
                self.image_states[current_file]['target_lang'] = target_lang

        target_en = self.lang_mapping.get(target_lang, None)
        t_direction = get_layout_direction(target_en)
        t_text_option = self.t_text_edit.document().defaultTextOption()
        t_text_option.setTextDirection(t_direction)
        self.t_text_edit.document().setDefaultTextOption(t_text_option)

    def set_src_trg_all(self):
        source_lang = self.s_combo.currentText()
        target_lang = self.t_combo.currentText()
        for image_path in self.image_files:
            state = self.image_states.setdefault(image_path, {})
            state['source_lang'] = source_lang
            state['target_lang'] = target_lang

    def change_all_blocks_size(self, diff: int):
        if len(self.blk_list) == 0:
            return
        updated_blk_list = []
        for blk in self.blk_list:
            blk_rect = tuple(blk.xyxy)
            blk.xyxy[:] = [blk_rect[0] - diff, blk_rect[1] - diff,
                           blk_rect[2] + diff, blk_rect[3] + diff]
            updated_blk_list.append(blk)
        self.blk_list = updated_blk_list
        self.pipeline.load_box_coords(self.blk_list)

    def _get_default_txt_prompt(self, t_lang='English') -> str:
        return """You are a professional translator specialized in natural language.

Target language is {t_lang}. Use that.

You are translating OCR-extracted comic text. The input may contain errors, typos, or incomplete sentences. You must interpret and correct them when needed to produce a natural and fluent language translation.

You MUST return ONLY a valid JSON object.

- No explanations
- No extra text
- No markdown
- No code blocks
- No comments

If anything other than JSON is included, the response is INVALID.

You MUST use these keys:

"block_1"
"block_2"
"block_3"
etc.

All keys MUST be present.

Even if a block is empty, include it with this string "...".

- Translate into natural, fluent language
- Preserve tone, slang, and intent
- Adapt idioms naturally
- Fix OCR mistakes when necessary
- If already target language → return unchanged
- NEVER use Korean or Japanese pronouns (당신, 그녀, 그, etc.)
- Use SINGLE QUOTES for quoted speech inside translations (e.g., '他说 "你好"') or escape double quotes with backslash (\")

- Do NOT rename keys
- Do NOT change structure
- Do NOT omit keys
- Do NOT add keys
- Do NOT output arrays
- Do NOT output anything outside the JSON object

Before responding, verify:

1. Is the output valid JSON?
2. Are all keys present?
3. Is there any text outside JSON? → If YES, REMOVE it

Only return the JSON object.""".format(t_lang=t_lang)

    # ─── TXT modal dialogs ───────────────────────────────────────

    def show_txt_modal(self, site_key=None):
        """Apre il flusso manuale su un sito web (Gemini, Dola).

        site_key=None mantiene il comportamento di sempre (Gemini).
        """
        from modules.browser_sites import get_site as _get_site
        site = _get_site(site_key) if site_key else None
        if site is not None:
            logger.info(f"[BROWSER SITE] Flusso manuale su {site.label}")
        self.highlight_button(2)
        if not self.blk_list:
            from app.ui.messages import Messages
            Messages.show_warning(self, "Nessun testo", "Nessun testo OCR rilevato. Esegui prima l'OCR.")
            return

        # Sincronizza l'ordine dei blocchi spazialmente (Dall'alto in basso, sinistra a destra)
        # Questo garantisce che block_1 nel prompt corrisponda a blk_list[0]
        from modules.utils.textblock import sort_blk_list
        self.blk_list = sort_blk_list(self.blk_list, right_to_left=False)

        full_text = ""
        for i, blk in enumerate(self.blk_list):
            text = getattr(blk, 'text', '') or ""
            full_text += f"block_{i+1}: {text}\n\n"

        try:
            source_lang = self.s_combo.currentText()
            target_lang = self.t_combo.currentText()
            try:
                translator = Translator(self, source_lang, target_lang)
                if translator.is_llm_engine:
                    t_lang = translator.target_lang_en
                    if hasattr(self.settings_page, 'get_txt_prompt'):
                        prompt = self.settings_page.get_txt_prompt(t_lang)
                    else:
                        prompt = self._get_default_txt_prompt(t_lang)
                    full_text += "\n" + "═"*50 + "\n"
                    full_text += "TRANSLATION PROMPT (System Instruction):\n"
                    full_text += "═"*50 + "\n\n"
                    full_text += prompt
            except Exception:
                pass
        except Exception:
            pass

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Testo OCR Rilevato"))
        dialog.resize(600, 500)
        layout = QtWidgets.QVBoxLayout(dialog)
        text_edit = QtWidgets.QTextEdit()
        text_edit.setPlainText(full_text)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        btn_layout = QtWidgets.QHBoxLayout()
        copy_btn = QtWidgets.QPushButton(self.tr("Copia tutto"))
        gemini_auto_btn = QtWidgets.QPushButton(self.tr("🤖 Gemini Auto"))
        gemini_auto_btn.setStyleSheet("background-color: #4285F4; color: white; font-weight: bold;")

        def start_gemini_automation():
            dialog.accept()
            self._start_gemini_automation(full_text, site_key)

        gemini_auto_btn.clicked.connect(start_gemini_automation)

        def copy_and_close():
            QtWidgets.QApplication.clipboard().setText(full_text)
            dialog.accept()
            self._play_operation_sound('letsgo.wav')
            QtCore.QTimer.singleShot(1000, self.show_txt_in_modal)

        copy_btn.clicked.connect(copy_and_close)
        close_btn = QtWidgets.QPushButton(self.tr("Chiudi"))
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(gemini_auto_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.exec()

    @QtCore.Slot(str, str, int, str, str)
    def _run_browser_automation_sync(self, blocks_json, full_text, expected_count,
                                    source_lang, target_lang):
        """
        Slot che gira sul main thread e pilota un sito web in una webview.

        Chiamato via QMetaObject.invokeMethod da _translate_with_browser_automator.
        Legge/scrive il risultato via self._gemini_result_container.
        Il sito da pilotare arriva da self._browser_site_key, non come
        argomento: la firma di un metodo invocato via QMetaObject e' un
        contratto rigido, e aggiungere parametri la rompe per tutti i
        chiamanti. _gemini_result_container segue gia' questa regola.

        Args:
            blocks_json: JSON dei blocchi con 'id' e 'text'
            full_text: prompt completo da incollare nel sito
            expected_count: numero di blocchi attesi
            source_lang: lingua sorgente
            target_lang: lingua di destinazione
        """
        import json
        from modules.gemini_automator import create_gemini_automator
        from modules.browser_sites import get_site

        site_key = getattr(self, '_browser_site_key', None)

        result_container = getattr(self, '_gemini_result_container', None)
        if not result_container:
            print("[DEBUG] No result container found")
            return

        try:
            blocks = json.loads(blocks_json)
            site = get_site(site_key) if site_key else None
            automator = create_gemini_automator(site_key)
            translations = automator.translate_blocks(
                blocks,
                full_text=full_text,
                expected_count=expected_count,
                source_lang=source_lang,
                target_lang=target_lang,
                progress_callback=None
            )
            if not translations:
                translations = automator.translations
            if translations:
                result_container['json_result'] = json.dumps(translations, ensure_ascii=False, indent=2)
                print(f"[DEBUG] Ricevuti {len(translations)} blocchi da {site.label if site else 'Gemini'}. Copio negli appunti...")
                clipboard = QtWidgets.QApplication.clipboard()
                clipboard.setText(result_container['json_result'])
            else:
                # Scrive SEMPRE uno dei due campi. Prima, in questo ramo,
                # non scriveva nulla: per il chiamante era indistinguibile
                # da "lo slot non e' mai partito", e il messaggio che ne
                # derivava era falso. Il vuoto qui ha una causa precisa:
                # l'automator ha girato ma non ha ottenuto risposta
                # (login mancante, selettori DOM cambiati, consensus non
                # dato). Va scritto, non lasciato implicito.
                _nome = site.label if site else 'Gemini'
                result_container['error'] = (
                    f"Nessuna traduzione ricevuta da {_nome}. L'automator ha "
                    "aperto il sito ma non ha ottenuto risposta: verifica di "
                    "essere loggato, che il prompt sia comparso nella casella "
                    "e di aver premuto Invio."
                )
                print(f"[DEBUG] {result_container['error']}")
        except Exception as e:
            result_container['error'] = e
            print(f"[DEBUG] Error in Gemini automation: {e}")

    def _start_gemini_automation(self, full_text: str, site_key=None):
        """Avvia l'automator su un sito web (Gemini, Dola...)."""
        import json
        from modules.gemini_automator import create_gemini_automator

        # Sincronizza l'ordine dei blocchi spazialmente (Dall'alto in basso, sinistra a destra)
        from modules.utils.textblock import sort_blk_list
        self.blk_list = sort_blk_list(self.blk_list, right_to_left=False)

        blocks = []
        for i, blk in enumerate(self.blk_list):
            text = (getattr(blk, 'text', '') or "").replace('"', '')
            blocks.append({'id': f'block_{i+1}', 'text': text})

        if not blocks:
            from app.ui.messages import Messages
            Messages.show_warning(self, "Nessun testo", "Nessun testo da tradurre.")
            return

        def progress_callback(completed, total):
            pass

        automator = create_gemini_automator(site_key)
        # Il dropdown e' l'unica fonte di verita': mai 'auto'/'it' fissi.
        # L'automator oggi traduce in base al prompt in full_text, ma i
        # parametri devono restare coerenti per log/futuri usi.
        try:
            src_ui = self.s_combo.currentText()
            tgt_ui = self.t_combo.currentText()
            src_en = self.lang_mapping.get(src_ui, src_ui) if hasattr(self, 'lang_mapping') else src_ui
            tgt_en = self.lang_mapping.get(tgt_ui, tgt_ui) if hasattr(self, 'lang_mapping') else tgt_ui
        except Exception:
            src_en, tgt_en = 'auto', 'Italian'
        translations = automator.translate_blocks(
            blocks,
            full_text=full_text,
            expected_count=len(blocks),
            source_lang=src_en or 'auto',
            target_lang=tgt_en or 'Italian',
            progress_callback=progress_callback
        )

        # Recupera i risultati se presenti
        if not translations:
            translations = automator.translations

        if translations:
            print(f"[DEBUG] Received {len(translations)} blocks. Copying to clipboard...")
            json_str = json.dumps(translations, ensure_ascii=False, indent=2)
            
            # Usa il metodo più sicuro per la clipboard in PySide6
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(json_str)
            
            self._play_operation_sound('letsgo.wav')
            # Piccolo delay per assicurarsi che la clipboard sia registrata dal sistema
            QtCore.QTimer.singleShot(800, self.show_txt_in_modal)
        else:
            print("[DEBUG] No translations received from Gemini.")
            from app.ui.messages import Messages
            Messages.show_error(self, "Traduzione fallita", "Gemini non ha restituito un JSON valido.")

    def show_txt_in_modal(self):
        if not self.blk_list:
            from app.ui.messages import Messages
            Messages.show_warning(self, "Nessun testo", "Nessun blocco di testo rilevato. Esegui prima il rilevamento o l'OCR.")
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Importa Traduzioni da JSON"))
        dialog.resize(600, 500)
        
        # Creiamo il layout principale senza passargli il dialog subito
        layout = QtWidgets.QVBoxLayout()

        label = QtWidgets.QLabel(self.tr('Incolla qui il JSON con le traduzioni (formato: {"block_N": "traduzione"}):'))
        layout.addWidget(label)
        text_edit = QtWidgets.QTextEdit()
        layout.addWidget(text_edit)

        btn_layout = QtWidgets.QHBoxLayout()
        import_btn = QtWidgets.QPushButton(self.tr("Importa"))
        close_btn = QtWidgets.QPushButton(self.tr("Annulla"))
        btn_layout.addWidget(import_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)

        clipboard = QtWidgets.QApplication.clipboard()
        cb_text = clipboard.text().strip()
        if cb_text.startswith('{') and '"block_1"' in cb_text:
            text_edit.setPlainText(cb_text)
            
            # Calcoliamo quanti blocchi ci aspettiamo
            expected_count = len(self.blk_list)
            
            def auto_click_if_ready():
                current_text = text_edit.toPlainText().strip()
                if not current_text:
                    return
                
                # Conta quante volte compare "block_" nel testo incollato
                import re
                found_blocks = len(re.findall(r'"block_\d+"', current_text))
                
                # Verifica anche se l'ultimo blocco atteso è presente (es. "block_7")
                last_block_key = f'"block_{expected_count}"'
                is_complete = last_block_key in current_text
                
                if found_blocks >= expected_count and is_complete:
                    print(f"[DEBUG] Validazione completata: {found_blocks}/{expected_count} blocchi trovati. Procedo all'importazione.")
                    import_btn.click()
                else:
                    print(f"[DEBUG] Validazione fallita: trovati {found_blocks} blocchi su {expected_count} attesi. L'importazione automatica è stata annullata per sicurezza.")
            
            QtCore.QTimer.singleShot(1000, auto_click_if_ready)

        def fix_quotes_in_json(json_text):
            import re
            def replace_inner_quotes(match):
                content = match.group(0)
                inner = content[1:-1]
                inner_fixed = re.sub(r'(?<!\\)"', "'", inner)
                return '"' + inner_fixed + '"'
            fixed = re.sub(r'"([^"\\]|\\.)*"', replace_inner_quotes, json_text)
            return fixed

        def import_translations():
            try:
                json_text = text_edit.toPlainText()
                try:
                    translations = json_mod.loads(json_text)
                except json_mod.JSONDecodeError:
                    fixed_json = fix_quotes_in_json(json_text)
                    try:
                        translations = json_mod.loads(fixed_json)
                    except json_mod.JSONDecodeError:
                        translations = _repair_truncated_json(json_text) or _repair_truncated_json(fixed_json)

                report = validate_translation_integrity(translations, len(self.blk_list))
                if not report["is_valid"]:
                    from app.ui.messages import Messages
                    details = ", ".join(report["missing_blocks"] + report["empty_blocks"]) or "JSON incompleto"
                    Messages.show_warning(self, "Traduzioni incomplete", f"Import annullato: {details}")
                    return

                updated_count = 0
                for i, blk in enumerate(self.blk_list):
                    key = f"block_{i+1}"
                    if key in translations:
                        blk.translation = translations[key]
                        updated_count += 1
                if updated_count > 0:
                    if self.curr_tblock:
                        self.t_text_edit.setPlainText(self.curr_tblock.translation)
                    dialog.accept()
                else:
                    from app.ui.messages import Messages
                    Messages.show_warning(self, "Nessun dato", "Nessuna chiave 'block_N' trovata nel JSON.")
            except json_mod.JSONDecodeError:
                from app.ui.messages import Messages
                Messages.show_error(self, "Errore JSON", "Il testo incollato non è un JSON valido.")
            except Exception as e:
                from app.ui.messages import Messages
                Messages.show_error(self, "Errore", f"Errore durante l'importazione: {str(e)}")

        import_btn.clicked.connect(import_translations)
        close_btn = QtWidgets.QPushButton(self.tr("Annulla"))
        close_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(import_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.exec()
