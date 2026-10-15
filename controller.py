import os
import cv2, shutil
import tempfile
import logging
import time
import numpy as np
import copy
import json
import zipfile
from pathlib import Path
from typing import Callable, Tuple, List
from dataclasses import asdict, is_dataclass
from PySide6 import QtWidgets
from PySide6 import QtCore
from PySide6.QtCore import QCoreApplication, QSettings, QThreadPool, QTimer, Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPixmap, QUndoStack, QUndoGroup
from datetime import datetime
from PySide6.QtWidgets import QDialog
from app.ui.dayu_widgets.clickable_card import ClickMeta
from app.ui.dayu_widgets.qt import MPixmap
from app.ui.main_window import ComicTranslateUI
from app.ui.messages import Messages
from app.thread_worker import GenericWorker
from app.ui.dayu_widgets.message import MMessage
from app.ui.canvas.text_item import TextBlockItem
from app.ui.canvas.rectangle import MoveableRectItem
from app.ui.canvas.save_renderer import ImageSaveRenderer
from app.ui.commands.box import AddRectangleCommand, DeleteBoxesCommand, \
                                      BoxesChangeCommand, AddTextItemCommand 
from app.ui.commands.textformat import TextFormatCommand
from app.ui.commands.multipletextformat import MultipleTextFormatCommand
from app.ui.commands.image import SetImageCommand
# save_state_to_proj_file / load_state_from_proj_file NON vengono usate:
# il percorso di salvataggio/caricamento reale e' in
# app.controllers.project_controller (save_project_new / _load_pages_project).
# Importarle qui era solo un rischio di NameError silenzioso.
from modules.detection import do_rectangles_overlap, get_inpaint_bboxes
from modules.utils.textblock import TextBlock
from modules.rendering.render import manual_wrap
from modules.utils.file_handler import FileHandler
from modules.utils.pipeline_utils import font_selected, validate_settings, get_layout_direction, \
                                         validate_ocr, validate_translator, get_language_code
from modules.utils.archives import make
from modules.utils.download import get_models, mandatory_models
from modules.utils.translator_utils import format_translations, is_there_text
from modules.rendering.render import TextRenderingSettings
# PDFExporter (reportlab) is imported lazily inside export_to_pdf() to avoid cold-start delay
# from modules.utils.pdf_export import PDFExporter

from app.controllers.project_controller import ProjectMixin
from app.controllers.batch_controller import BatchMixin
from app.controllers.text_polygon_mixin import TextPolygonMixin
from app.controllers.polygon_inpaint_mixin import PolygonInpaintMixin
from app.controllers.ui_controller import UIMixin
from app.controllers.save_export_mixin import SaveExportMixin
from app.controllers.save_cleanup import deactivate_viewer_selections
from app.controllers.commands.image_update_handler import ImageUpdateHandler
from constants import (
    MAX_IMAGES_IN_MEMORY,
    MODEL_VERIFY_DELAY_MS,
    UI_REFRESH_DELAY_MS
)

logger = logging.getLogger(__name__)

class ComicTranslate(BatchMixin, TextPolygonMixin, PolygonInpaintMixin, UIMixin, SaveExportMixin, ProjectMixin, ImageUpdateHandler, ComicTranslateUI):
    image_processed = QtCore.Signal(int, object, str)
    progress_update = QtCore.Signal(int, int, int, int, bool)
    image_skipped = QtCore.Signal(str, str, str)
    blk_rendered = QtCore.Signal(str, int, object)

    @property
    def pipeline(self):
        """Lazy loading per ComicTranslatePipeline - viene istanziato solo quando necessario."""
        if self._pipeline is None:
            from pipeline import ComicTranslatePipeline
            self._pipeline = ComicTranslatePipeline(self)
        return self._pipeline

    def __init__(self, parent=None):
        super(ComicTranslate, self).__init__(parent)
        self.image_files = []
        self.curr_img_idx = -1
        self.image_states = {}
        self.blk_list = []
        self.image_data = {}
        self.image_history = {}
        self.in_memory_history = {}
        self.current_history_index = {}
        self.displayed_images = set()
        
        self.text_blocks = {}
        self.rect_items = {}
        self.text_items = {}
        self.comic_info = {}
        self.undo_group = QUndoGroup(self)
        self.undo_stacks = {}
        self.curr_tblock = None
        self.curr_tblock_item = None
        self.selected_text_items = []
        self.project_file = None
        self._pipeline = None

        self.file_handler = FileHandler()
        self.threadpool = QThreadPool()
        self.current_worker = None
        self.image_skipped.connect(self.on_image_skipped)
        self.image_processed.connect(self.on_image_processed)
        self.progress_update.connect(self.update_progress)
        self.blk_rendered.connect(self.on_blk_rendered)
        self.image_cards = []
        self.current_highlighted_card = None
        self.connect_ui_elements()
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.load_main_page_settings()

        self.settings_page.load_settings()
        self.image_viewer.fit_mode = self.settings_page.get_value('tools.fit_mode', 0)
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self.settings_page.theme_changed.connect(self.apply_theme)
        self.settings_page.font_imported.connect(self.set_font)
        self.settings_page.selected_fonts_changed.connect(self.update_font_dropdown)
        self._connect_tool_dropdown_sync()
        self._sync_home_tool_dropdowns_from_settings()
        
        self._connect_geminiamo_signals()
        
        self.current_inpainter_model = None
        QTimer.singleShot(MODEL_VERIFY_DELAY_MS, self._verify_mandatory_models)
        
        self.temp_dir = tempfile.mkdtemp()
        self.originals_temp_dir = os.path.join(self.temp_dir, 'originals')
        os.makedirs(self.originals_temp_dir, exist_ok=True)
        self.max_images_in_memory = MAX_IMAGES_IN_MEMORY
        self.loaded_images = []
        self.original_images = {}
        
        self._images_processed_count = 0
        self._images_updated_visually = set()
        self._total_images_in_batch = 0
        self.widgets_to_block = [
            self.font_dropdown,
            self.font_size_dropdown,
            self.line_spacing_dropdown,
            self.block_font_color_button,
            self.outline_font_color_button,
            self.outline_width_dropdown,
            self.outline_button
        ]

        self.outline_enabled = True

    def _connect_geminiamo_signals(self):
        """Connect Geminiamo client signals to UI handlers."""
        try:
            from modules.api_clients.geminiamo_client import geminiamo_client
            geminiamo_client.refresh_failed.connect(self._show_geminiamo_cookie_expired_popup)
            logger.debug("Geminiamo refresh_failed signal connected")
        except Exception as e:
            logger.warning(f"Could not connect Geminiamo signals: {e}")

    def _verify_mandatory_models(self):
        """Avvia la verifica dei modelli obbligatori su thread background (cold-start fix B3).
        L'I/O bloccante (SHA-256 checksum) non blocca più il thread UI."""
        def _background_verify():
            # 1. Download/verifica checksum modelli obbligatori (I/O pesante)
            for model in mandatory_models:
                get_models(model)

            # 2. Verifica disponibilità modelli configurati (leggera)
            unavailable = []
            try:
                from modules.utils.model_manager import model_manager
                from modules.browser_sites import is_browser_site, site_keys
                selected_ocr = self.settings_page.get_tool_selection('ocr')
                selected_translator = self.settings_page.get_tool_selection('translator')
                ocr_key = self.processor._get_ocr_key(selected_ocr) if hasattr(self, 'processor') else selected_ocr
                # I siti browser (Gemini, Dola...) non sono provider: si guidano
                # con una webview, quindi non hanno uno stato da verificare.
                excluded = set(site_keys()) | {'TXT', 'Gemini Vision Browser'}
                if is_browser_site(selected_translator):
                    excluded.add(selected_translator)
                models_to_check = [ocr_key] + ([selected_translator] if selected_translator not in excluded else [])
                unavailable = model_manager.check_models_availability(models_to_check)
            except Exception as e:
                logger.error(f"Errore durante la verifica dei modelli configurati: {e}")
            return unavailable

        def _on_verify_done(unavailable):
            if unavailable:
                models_str = ", ".join(unavailable)
                message = self.tr(
                    f"I seguenti modelli configurati non sembrano più disponibili presso il provider: "
                    f"{models_str}.\nTi consigliamo di verificarli nelle impostazioni."
                )
                MMessage.warning(text=message, parent=self, duration=10, closable=True)
                logger.warning(f"[STARTUP] Modelli non disponibili: {models_str}")

        def _on_verify_error(error_tuple):
            exctype, value, _ = error_tuple
            logger.error(f"Errore nel worker di verifica modelli: {exctype.__name__}: {value}")

        worker = GenericWorker(_background_verify)
        worker.signals.result.connect(lambda result: QTimer.singleShot(0, lambda: _on_verify_done(result)))
        worker.signals.error.connect(lambda err: QTimer.singleShot(0, lambda: _on_verify_error(err)))
        self.threadpool.start(worker)

    def connect_ui_elements(self):
        self.image_browser_button.sig_files_changed.connect(self.thread_load_images)
        self.document_browser_button.sig_files_changed.connect(self.thread_load_images)
        self.archive_browser_button.sig_files_changed.connect(self.thread_load_images)
        self.comic_browser_button.sig_files_changed.connect(self.thread_load_images)
        self.project_browser_button.sig_file_changed.connect(self.thread_load_project)

        self.save_browser.set_save_choice_handler(self._on_save_choice_clicked)
        self.save_browser.sig_save_with_choice.connect(self._on_save_with_choice)
        self.save_browser.sig_file_changed.connect(self.save_current_image)
        self.save_all_browser.sig_file_changed.connect(self.save_and_make)
        self.save_project_button.clicked.connect(self.thread_save_project)
        self.save_as_project_button.clicked.connect(self.thread_save_as_project)
        self.join_ctpr_button.clicked.connect(self.join_ctpr_files)
        
        self.export_pdf_button.clicked.connect(self.export_to_pdf)
        self.drag_browser.sig_files_changed.connect(self.thread_load_images)
        self.manual_radio.clicked.connect(self.manual_mode_selected)
        self.automatic_radio.clicked.connect(self.batch_mode_selected)

        self.hbutton_group.get_button_group().buttons()[0].clicked.connect(lambda: self.block_detect())
        
        ocr_btn = self.hbutton_group.get_button_group().buttons()[1]
        ocr_btn.clicked.connect(self.ocr)
        ocr_btn.installEventFilter(self)
        
        # Connessioni dropdown per la barra principale
        self.ocr_dropdown.currentTextChanged.connect(self._on_ocr_dropdown_changed)
        self.translate_dropdown.currentTextChanged.connect(self._on_translate_dropdown_changed)
        self.inpainter_dropdown.currentTextChanged.connect(self._on_inpainter_dropdown_changed_main)
        
        self.hbutton_group.get_button_group().buttons()[2].clicked.connect(self.translate_image)
        self.hbutton_group.get_button_group().buttons()[3].clicked.connect(self.show_txt_modal)
        self.hbutton_group.get_button_group().buttons()[4].clicked.connect(self.load_segmentation_points)
        self.hbutton_group.get_button_group().buttons()[5].clicked.connect(self.inpaint_and_set)
        self.hbutton_group.get_button_group().buttons()[6].clicked.connect(self.render_text)
        self.original_button.setCheckable(True)
        self.original_button.toggled.connect(self.toggle_original_view)
        self.detect_font_button.clicked.connect(self.detect_fonts)
        self.auto_center_button.clicked.connect(self.auto_center_text)

        self.undo_tool_group.get_button_group().buttons()[0].clicked.connect(lambda: self._debug_undo())
        self.undo_tool_group.get_button_group().buttons()[1].clicked.connect(lambda: self._debug_redo())

        self.detect_batch_button.clicked.connect(self.detect_batch)
        self.translate_button.clicked.connect(self.start_batch_process)
        if hasattr(self, "sbianchetta_button"):
            self.sbianchetta_button.clicked.connect(self.sbianchetta)

        if hasattr(self, "markers_button"):
            self.markers_button.clicked.connect(self.toggle_markers)
        if hasattr(self, "polygons_button"):
            self.polygons_button.clicked.connect(self.toggle_polygons)
        if hasattr(self, "rect_boxes_button"):
            self.rect_boxes_button.clicked.connect(self.toggle_rect_boxes)
        if hasattr(self, "toggle_text_boxes_button"):
            self.toggle_text_boxes_button.clicked.connect(self.toggle_text_boxes)
        self.cancel_batch_button.clicked.connect(self.cancel_batch_operation)
        self.set_all_button.clicked.connect(self.set_src_trg_all)
        self.clear_rectangles_button.clicked.connect(self.image_viewer.clear_rectangles)
        self.toggle_shape_button.clicked.connect(lambda: self.image_viewer.toggle_shape())
        self.clear_brush_strokes_button.clicked.connect(self.image_viewer.clear_brush_strokes)
        self.draw_blklist_blks.clicked.connect(self.show_boxes_overlays)
        self.change_all_blocks_size_dec.clicked.connect(lambda: self.change_all_blocks_size(-int(self.change_all_blocks_size_diff.text())))
        self.change_all_blocks_size_inc.clicked.connect(lambda: self.change_all_blocks_size(int(self.change_all_blocks_size_diff.text())))
        self.delete_button.clicked.connect(self.delete_selected_box)
        self.s_text_edit.textChanged.connect(self.update_text_block)
        self.t_text_edit.textChanged.connect(self.update_text_block_from_edit)
        self.s_combo.currentTextChanged.connect(self.save_src_trg)
        self.t_combo.currentTextChanged.connect(self.save_src_trg)
        self.image_viewer.rectangle_selected.connect(self.handle_rectangle_selection)
        self.image_viewer.rectangle_created.connect(self.handle_rectangle_creation)
        self.image_viewer.rectangle_deleted.connect(self.handle_rectangle_deletion)
        self.image_viewer.command_emitted.connect(self.push_command)
        self.image_viewer.connect_rect_item.connect(self.connect_rect_item_signals)
        self.image_viewer.connect_text_item.connect(self.connect_text_item_signals)

        self._init_bucket_controller()

        self.font_dropdown.currentTextChanged.connect(self.on_font_dropdown_change)
        self.font_size_dropdown.currentTextChanged.connect(self.on_font_size_change)
        self.line_spacing_dropdown.currentTextChanged.connect(self.on_line_spacing_change)
        self.block_font_color_button.clicked.connect(self.on_font_color_change)
        self.alignment_tool_group.get_button_group().buttons()[0].clicked.connect(self.left_align)
        self.alignment_tool_group.get_button_group().buttons()[1].clicked.connect(self.center_align)
        self.alignment_tool_group.get_button_group().buttons()[2].clicked.connect(self.right_align)
        self.alignment_tool_group.get_button_group().buttons()[3].clicked.connect(self.justify_align)
        self.bold_button.clicked.connect(self.bold)
        self.italic_button.clicked.connect(self.italic)
        self.underline_button.clicked.connect(self.underline)
        self.remove_newlines_button.clicked.connect(self.remove_newlines_from_target)
        self.polygon_text_button.toggled.connect(self.toggle_selected_text_polygon_mode)
        self.polygon_inpaint_button.toggled.connect(self.toggle_polygon_inpaint_mode)
        self.outline_font_color_button.clicked.connect(self.on_outline_color_change)
        self.outline_width_dropdown.currentTextChanged.connect(self.on_outline_width_change)
        self.outline_button.clicked.connect(self.toggle_outline_settings)

        self.page_list.currentItemChanged.connect(self.on_card_selected)
        self.page_list.del_img.connect(self.handle_image_deletion)
        self.page_list.insert_browser.sig_files_changed.connect(self.thread_insert)
        
        self.inpainter_model_dropdown.currentIndexChanged.connect(self._on_inpainter_dropdown_changed)
        self.refresh_models_button.clicked.connect(self.refresh_inpainter_models)
    
    def _on_settings_saved(self):
        """Update settings in real-time when they are saved."""
        self.image_viewer.fit_mode = self.settings_page.get_value('tools.fit_mode', 0)
        self._sync_home_tool_dropdowns_from_settings()

    def _connect_tool_dropdown_sync(self):
        self.settings_page.ui.ocr_combo.currentTextChanged.connect(
            lambda text: self._on_settings_tool_combo_changed('ocr', text)
        )
        self.settings_page.ui.translator_combo.currentTextChanged.connect(
            lambda text: self._on_settings_tool_combo_changed('translator', text)
        )
        self.settings_page.ui.inpainter_combo.currentTextChanged.connect(
            lambda text: self._on_settings_tool_combo_changed('inpainter', text)
        )

    def _sync_home_tool_dropdowns_from_settings(self):
        self._set_home_tool_dropdown('ocr', self.settings_page.get_tool_selection('ocr'))
        self._set_home_tool_dropdown('translator', self.settings_page.get_tool_selection('translator'))
        self._set_home_tool_dropdown('inpainter', self.settings_page.get_tool_selection('inpainter'))

    def _set_home_tool_dropdown(self, tool_type, value):
        dropdowns = {
            'ocr': getattr(self, 'ocr_dropdown', None),
            'translator': getattr(self, 'translate_dropdown', None),
            'inpainter': getattr(self, 'inpainter_dropdown', None),
        }
        dropdown = dropdowns.get(tool_type)
        if dropdown is None or not value:
            return
        dropdown.blockSignals(True)
        index = dropdown.findText(value)
        if index >= 0:
            dropdown.setCurrentIndex(index)
        dropdown.blockSignals(False)

    def _set_settings_tool_combo(self, tool_type, value):
        combos = {
            'translator': self.settings_page.ui.translator_combo,
            'ocr': self.settings_page.ui.ocr_combo,
            'inpainter': self.settings_page.ui.inpainter_combo,
        }
        combo = combos.get(tool_type)
        if combo is None or not value:
            return
        combo.blockSignals(True)
        index = combo.findText(value)
        if index < 0 and tool_type == 'inpainter':
            for i in range(combo.count()):
                if combo.itemText(i).startswith(f"{value} ("):
                    index = i
                    break
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _persist_tool_selection(self, tool_type, value):
        if not value:
            return
        settings = QSettings("ComicLabs", "KomicTranslate")
        settings.beginGroup('tools')
        mapped_value = self.settings_page.ui.value_mappings.get(str(value), value)
        settings.setValue(tool_type, mapped_value)
        settings.endGroup()

    def eventFilter(self, obj, event):
        ocr_btn = self.hbutton_group.get_button_group().buttons()[1]
        if obj == ocr_btn and event.type() == QtCore.QEvent.MouseButtonDblClick:
            ocr_btn.showMenu()
            return True
        return False

    def _on_inpainter_dropdown_changed(self, index):
        if index >= 0:
            model_name = self.inpainter_model_dropdown.itemData(index)
            if model_name:
                self.set_inpainter_model(model_name)

    def _on_ocr_dropdown_changed(self, text):
        if text:
            self._set_settings_tool_combo('ocr', text)
            self._persist_tool_selection('ocr', text)

    def _on_translate_dropdown_changed(self, text):
        if text:
            self._set_settings_tool_combo('translator', text)
            self._persist_tool_selection('translator', text)

    def _on_inpainter_dropdown_changed_main(self, text):
        if text:
            self._set_settings_tool_combo('inpainter', text)
            self._persist_tool_selection('inpainter', text)

    def _on_settings_tool_combo_changed(self, tool_type, text):
        if getattr(self.settings_page, '_loading_settings', False):
            return
        value = self.settings_page.get_tool_selection(tool_type)
        self._set_home_tool_dropdown(tool_type, value)
        self._persist_tool_selection(tool_type, value)

    def _init_bucket_controller(self):
        """Inizializza il controller per bucket fill asincrono."""
        from app.ui.commands.async_bucket import BucketFillUIController
        self._bucket_controller = BucketFillUIController(self.image_viewer, self)
        self._bucket_controller.connect_bucket_button(self.bucket_button)

    def remove_newlines_from_target(self):
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

    def delete_selected_box(self):
        if self.curr_tblock:
            command = DeleteBoxesCommand(
                self,
                self.image_viewer.selected_rect,
                self.curr_tblock_item,
                self.curr_tblock,
                self.blk_list,
            )
            self.undo_group.activeStack().push(command)

    def save_src_trg(self):
        source_lang = self.s_combo.currentText()
        target_lang = self.t_combo.currentText()
        if self.curr_img_idx >= 0 and self.image_files and self.curr_img_idx < len(self.image_files):
            current_file = self.image_files[self.curr_img_idx]
            
            if current_file not in self.image_states:
                self.image_states[current_file] = {
                    'viewer_state': {},
                    'source_lang': source_lang,
                    'target_lang': target_lang,
                    'brush_strokes': [],
                    'blk_list': [],
                    'text_items_data': []
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
            blk.xyxy[:] = np.array([blk_rect[0] - diff, blk_rect[1] - diff, blk_rect[2] + diff, blk_rect[3] + diff])
            updated_blk_list.append(blk)
        self.blk_list = updated_blk_list
        self.pipeline.load_box_coords(self.blk_list)

    def batch_mode_selected(self):
        self.enable_hbutton_group()
        if hasattr(self, '_apply_batch_action_gate'):
            self._apply_batch_action_gate()
        else:
            self.translate_button.setEnabled(True)

    def manual_mode_selected(self):
        self.enable_hbutton_group()
        if hasattr(self, '_apply_batch_action_gate'):
            self._apply_batch_action_gate()
        else:
            self.translate_button.setEnabled(True)

    def run_threaded(self, callback: Callable, result_callback: Callable=None, error_callback: Callable=None, finished_callback: Callable=None, *args, **kwargs):
        worker = GenericWorker(callback, *args, **kwargs)

        # GenericWorker emette 'error' e POI 'finished': senza questo reset i
        # completion handler mostravano "completato con successo" anche dopo un
        # crash. Il flag viene reimpostato a False all'avvio di ogni worker.
        self._batch_error = False

        if result_callback:
            worker.signals.result.connect(lambda result: QtCore.QTimer.singleShot(0, lambda: result_callback(result)))
        if error_callback:
            worker.signals.error.connect(lambda error: QtCore.QTimer.singleShot(0, lambda: error_callback(error)))
        if finished_callback:
            def _schedule_finished_callback():
                callback_name = getattr(finished_callback, "__name__", repr(finished_callback))
                logger.info(f"[THREADING] Worker finished: schedulo finished_callback={callback_name}")
                QtCore.QTimer.singleShot(0, finished_callback)
            worker.signals.finished.connect(_schedule_finished_callback)
        
        self.current_worker = worker
        self.threadpool.start(worker)

    def default_error_handler(self, error_tuple: Tuple):
        exctype, value, traceback_str = error_tuple
        error_msg = f"An error occurred:\n{exctype.__name__}: {value}"
        error_msg_trcbk = f"An error occurred:\n{exctype.__name__}: {value}\n\nTraceback:\n{traceback_str}"
        logger.error(error_msg_trcbk)

        # Segnala il fallimento: i completion handler (che ricevono comunque
        # 'finished') devono smettere di riportare successo.
        self._batch_error = True

        QtWidgets.QMessageBox.critical(self, "Error", error_msg)
        self.loading.setVisible(False)
        self.enable_hbutton_group()
        self._enable_batch_buttons()

        # Ripristina lo stato: senza questo _batch_completed_shown rimaneva False
        # e _is_batch_safe_for_save() disabilitava "Tutte le immagini" per tutta
        # la sessione; i timer di sicurezza potevano sparare dopo 5 minuti.
        self._batch_completed_shown = True
        self._in_translate_process = False
        for timer_attr in ('_safety_timer', '_cancellation_timer'):
            timer = getattr(self, timer_attr, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

    def _debug_undo(self):
        logger.debug(f"[UNDO] Undo button clicked. Active stack: {self.undo_group.activeStack()}")
        if self.undo_group.activeStack():
            stack = self.undo_group.activeStack()
            logger.debug(f"[UNDO] Stack index: {stack.index()}, count: {stack.count()}")
            if stack.index() > 0:
                logger.debug(f"[UNDO] About to call undo on command: {stack.command(stack.index() - 1).__class__.__name__}")
            else:
                logger.warning("[UNDO] Already at beginning of stack, nothing to undo")
        else:
            logger.warning("[UNDO] No active stack!")
        self.undo_group.undo()

    def _debug_redo(self):
        logger.debug(f"[UNDO] Redo button clicked. Active stack: {self.undo_group.activeStack()}")
        if self.undo_group.activeStack():
            stack = self.undo_group.activeStack()
            logger.debug(f"[UNDO] Stack index: {stack.index()}, count: {stack.count()}")
            if stack.index() < stack.count():
                logger.debug(f"[UNDO] About to call redo on command: {stack.command(stack.index()).__class__.__name__}")
            else:
                logger.warning("[UNDO] Already at end of stack, nothing to redo")
        else:
            logger.warning("[UNDO] No active stack!")
        self.undo_group.redo()

    def _on_save_choice_clicked(self):
        pass

    def _on_save_with_choice(self, suggested_filename):
        if len(self.image_files) <= 1:
            self.save_browser.trigger_save_dialog(suggested_filename)
            return

        from app.ui.save_image_choice_dialog import SaveImageChoiceDialog
        dialog = SaveImageChoiceDialog(len(self.image_files), self)
        result = dialog.exec()

        if result != QtWidgets.QDialog.Accepted:
            return

        choice = dialog.get_choice()
        if choice == "current":
            self.save_browser.trigger_save_dialog(suggested_filename)
        else:
            self._ask_and_save_all_images()

    def _ask_and_save_all_images(self):
        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Seleziona cartella per salvare tutte le immagini"),
            self.save_browser._last_directory
        )

        if not output_dir:
            return

        self.save_browser._last_directory = output_dir

        files_needing_overwrite = []
        for img_file in self.image_files:
            original_name = os.path.basename(img_file)
            output_path = os.path.join(output_dir, original_name)
            if os.path.exists(output_path):
                files_needing_overwrite.append(original_name)

        overwrite_all = False

        if files_needing_overwrite:
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tr("Conferma sovrascrittura"),
                self.tr(f"{len(files_needing_overwrite)} file(s) esistono già nella cartella.\nVuoi sovrascrivere tutti?")
            )
            if reply == QtWidgets.QMessageBox.Yes:
                overwrite_all = True
            else:
                return

        self._save_all_images_worker(output_dir, overwrite_all)

    def _save_all_images_worker(self, output_dir, overwrite_all):
        success_count = 0
        error_count = 0
        errors = []

        total = len(self.image_files)

        for idx, img_file in enumerate(self.image_files):
            original_name = os.path.basename(img_file)
            output_path = os.path.join(output_dir, original_name)

            if os.path.exists(output_path) and not overwrite_all:
                continue

            try:
                self.curr_img_idx = idx
                self.load_image_state(img_file, update_ui=True)
                deactivate_viewer_selections(self.image_viewer)

                rendered_image = self.image_viewer.get_cv2_image(paint_all=True)
                success = cv2.imwrite(output_path, rendered_image)

                if not success:
                    raise ValueError(f"cv2.imwrite ha restituito False per: {output_path}")

                success_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"Pagina {idx + 1}: {str(e)}")
                logger.error(f"Errore nel salvare l'immagine {idx + 1}: {str(e)}")

        try:
            if hasattr(self, 'pipeline') and hasattr(self.pipeline, '_cleanup_stray_translated_files'):
                self.pipeline._cleanup_stray_translated_files()
        except Exception:
            pass

        if error_count > 0:
            error_msg = self.tr(f"Salvataggio completato: {success_count} immagini.\nErrori: {error_count}")
            if errors:
                error_msg += "\n\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    error_msg += self.tr(f"\n... e altri {len(errors) - 5} errori")
            QtWidgets.QMessageBox.warning(self, self.tr("Salvataggio con errori"), error_msg)
        elif success_count > 0:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Salvataggio completato"),
                self.tr(f"{success_count} immagine(i) salvata(e) con successo.")
            )

    def closeEvent(self, event):
        """Cleanup on application close."""
        logger.info("Closing application, cleaning up...")
        
        if hasattr(self, 'threadpool'):
            self.threadpool.waitForDone()
        
        # Cleanup temp directory
        if hasattr(self, 'temp_dir') and self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.info(f"Deleted temp directory: {self.temp_dir}")
            except Exception as e:
                logger.error(f"Error deleting temp directory {self.temp_dir}: {e}")
        
        # Cleanup image cache to prevent memory leak
        if hasattr(self, 'loaded_images'):
            self.loaded_images.clear()
        if hasattr(self, 'original_images'):
            self.original_images.clear()
        if hasattr(self, 'image_data'):
            self.image_data.clear()
            
        super().closeEvent(event)

Controller = ComicTranslate
