import os
import cv2
import json
import copy
import shutil
import logging
import tempfile
import zipfile
import glob
import re
import time
import numpy as np
from typing import List, Tuple
from dataclasses import asdict, is_dataclass
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt, QSettings, QCoreApplication
from PySide6.QtGui import QColor, QImage, QPixmap, QUndoStack

from modules.utils.textblock import TextBlock
from modules.utils.textblock_serialization import (
    deserialize_text_block,
    serialize_text_block,
)
from modules.utils.pipeline_utils import get_language_code, get_layout_direction
from modules.utils.translator_utils import format_translations
from modules.rendering.render import manual_wrap
from app.ui.dayu_widgets.clickable_card import ClickMeta
from app.ui.canvas.text_item import TextBlockItem
from app.ui.canvas.text_outline_utils import (
    outline_color_for_loading,
    outline_enabled_from_data,
)
from app.ui.canvas.save_renderer import ImageSaveRenderer
from app.ui.canvas.pixmap_state import sync_viewer_photo_to_image_data
from app.ui.canvas.z_layers import TEXT_BOX_Z
from app.projects.ctpr_state_support import (
    create_text_item_from_data,
    deserialize_brush_strokes,
    ensure_block_id,
    serialize_brush_strokes,
    serialize_text_item,
)
from app.projects.ctpr_compat import adapt_project_data_to_pages
from app.projects.ctpr_svg_state import clear_svg_items, restore_svg_items, serialize_svg_items
from app.controllers.save_cleanup import deactivate_viewer_selections
from app.controllers.project_image_cache import resolve_cached_image
from app.controllers.project_save_support import execute_ctpr_save, normalize_ctpr_path
from app.controllers.text_edits_sync import refresh_text_edits_for_current_block
from app.ui.font_size_utils import parse_font_size, format_font_size
from constants import (
    MAX_IMAGES_IN_MEMORY,
    DEFAULT_FONT_COLOR,
    DEFAULT_OUTLINE_COLOR,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_LINE_SPACING
)

logger = logging.getLogger(__name__)


class ProjectMixin:
    """Mixin containing project save/load, image loading/display,
    image-state persistence, settings, and miscellaneous feature methods."""

    # ------------------------------------------------------------------ #
    #  Image Loading & Display
    # ------------------------------------------------------------------ #

    def load_initial_image(self, file_paths: List[str]):
        file_paths = self.file_handler.prepare_files(file_paths)
        self.image_files = file_paths
        self.project_file = None

        if file_paths:
            for idx, file_path in enumerate(file_paths):
                img = cv2.imread(file_path)
                if img is not None:
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    self.original_images[file_path] = img_rgb.copy()
                    original_filename = f"original_{idx:03d}.jpg"
                    original_temp_path = os.path.join(self.originals_temp_dir, original_filename)
                    cv2.imwrite(original_temp_path, img)

            return self.load_image(file_paths[0])
        return None

    def load_image(self, file_path: str):
        if file_path in self.image_data:
            return self.image_data[file_path]

        if file_path in self.image_history:
            current_index = self.current_history_index[file_path]
            current_temp_path = self.image_history[file_path][current_index]
            cv2_image = cv2.imread(current_temp_path)
            cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
            if cv2_image is not None:
                return cv2_image

        try:
            file_name = os.path.basename(file_path)
            file_dir = os.path.dirname(file_path)
            clean_pattern = os.path.join(file_dir, "comic_clean_*", "cleaned_images", file_name)
            clean_matches = glob.glob(clean_pattern)

            if clean_matches:
                clean_image_path = clean_matches[0]
                print(f"[DEBUG] Trovata immagine pulita: {clean_image_path}")
                cv2_image = cv2.imread(clean_image_path)
                if cv2_image is not None:
                    cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
                    print(f"[DEBUG] Caricata immagine pulita per {file_name}")
                    return cv2_image
                else:
                    print(f"[WARNING] Impossibile caricare immagine pulita: {clean_image_path}")

            cv2_image = cv2.imread(file_path)
            cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
            return cv2_image
        except Exception as e:
            print(f"Error loading image {file_path}: {str(e)}")
            return None

    def _remember_last_open_path(self, file_paths):
        """Persist last opened folder/file so load dialogs reopen there after restart."""
        try:
            from app.ui.dayu_widgets.browser import remember_last_open_path
            remember_last_open_path(file_paths)
        except Exception:
            try:
                path = file_paths[0] if isinstance(file_paths, (list, tuple)) else file_paths
                if path and isinstance(path, str):
                    directory = os.path.dirname(path) if os.path.isfile(path) else path
                    if directory and os.path.isdir(directory):
                        settings = QSettings("ComicLabs", "KomicTranslate")
                        settings.setValue("last_open_directory", directory)
                        settings.sync()
            except Exception:
                pass

    def thread_load_images(self, file_paths: List[str]):
        if file_paths:
            self._remember_last_open_path(file_paths)
        if file_paths and file_paths[0].lower().endswith('.ctpr'):
            self.thread_load_project(file_paths[0])
            return
        self.clear_state()
        self.run_threaded(self.load_initial_image, self.on_initial_image_loaded, self.default_error_handler, None, file_paths)

    def thread_insert(self, file_paths: list[str]):
        if file_paths:
            self._remember_last_open_path(file_paths)
        if self.image_files:
            def on_files_prepared(prepared_files):
                self.image_files.extend(prepared_files)
                for path in prepared_files:
                    stack = QUndoStack(self)
                    self.undo_stacks[path] = stack
                    self.undo_group.addStack(stack)
                new_index = self.image_files.index(prepared_files[0])
                self.update_image_cards()
                self.page_list.setCurrentRow(new_index)
                if hasattr(self, 'reset_batch_action_gate'):
                    self.reset_batch_action_gate()
                self.save_project_button.setEnabled(True)
                self.save_as_project_button.setEnabled(True)

            self.run_threaded(
                lambda: self.file_handler.prepare_files(file_paths, True),
                on_files_prepared,
                self.default_error_handler)
        else:
            self.thread_load_images(file_paths)

    def clear_state(self):
        self.image_viewer.hide_original_overlay()
        self._set_original_button_checked(False)
        self.image_files = []
        self.image_states.clear()
        self.image_data.clear()
        self.image_history.clear()
        self.current_history_index.clear()
        self.blk_list = []
        self.displayed_images.clear()
        self.image_viewer.clear_rectangles(page_switch=True)
        self.image_viewer.clear_brush_strokes(page_switch=True)
        clear_svg_items(self.image_viewer)
        self.s_text_edit.clear()
        self.t_text_edit.clear()
        self.image_viewer.clear_text_items()
        self.loaded_images = []
        self.in_memory_history.clear()
        self.undo_stacks.clear()
        self.project_file = None

        self.text_blocks.clear()
        self.rect_items.clear()
        self.text_items.clear()
        self.original_images.clear()
        self.comic_info = {}

        if hasattr(self, 'originals_temp_dir') and os.path.exists(self.originals_temp_dir):
            try:
                shutil.rmtree(self.originals_temp_dir)
                os.makedirs(self.originals_temp_dir, exist_ok=True)
                print(f"[DEBUG] Cartella temporanea originali pulita: {self.originals_temp_dir}")
            except Exception as e:
                print(f"[WARNING] Errore nella pulizia della cartella temporanea: {str(e)}")

        self.curr_img_idx = -1
        self.clear_all_highlights()

    def clear_all_items_new(self):
        """Pulisce completamente tutti gli elementi dal progetto"""
        print(f"[DEBUG] Pulizia completa degli elementi")
        try:
            if hasattr(self, 'image_viewer') and self.image_viewer:
                self.image_viewer.clear_text_items(delete=True)
                self.image_viewer.clear_rectangles()
                clear_svg_items(self.image_viewer)

            if hasattr(self, 'text_items'):
                self.text_items.clear()
            if hasattr(self, 'text_blocks'):
                self.text_blocks.clear()
            if hasattr(self, 'rect_items'):
                self.rect_items.clear()

            if hasattr(self, 'blk_list'):
                self.blk_list.clear()

            self.clear_text_edits()
            print(f"[DEBUG] Pulizia completata")
        except Exception as e:
            print(f"[WARNING] Errore durante la pulizia: {str(e)}")

    def on_initial_image_loaded(self, cv2_image):
        if cv2_image is not None:
            self.image_data[self.image_files[0]] = cv2_image
            self.image_history[self.image_files[0]] = [self.image_files[0]]
            self.in_memory_history[self.image_files[0]] = [cv2_image.copy()]
            self.current_history_index[self.image_files[0]] = 0
            self.save_image_state(self.image_files[0])

        for file in self.image_files:
            self.save_image_state(file)
            stack = QUndoStack(self)
            self.undo_stacks[file] = stack
            self.undo_group.addStack(stack)

        if self.image_files:
            self.page_list.blockSignals(True)
            self.update_image_cards()
            self.page_list.blockSignals(False)
            self.page_list.setCurrentRow(0)
            self.loaded_images.append(self.image_files[0])
            if hasattr(self, 'reset_batch_action_gate'):
                self.reset_batch_action_gate()
            self.save_project_button.setEnabled(True)
            self.save_as_project_button.setEnabled(True)
        else:
            self.image_viewer.clear_scene()

        self.image_viewer.resetTransform()
        self.image_viewer.smartFit()

    def update_image_cards(self):
        self.page_list.clear()
        for index, file_path in enumerate(self.image_files):
            file_name = os.path.basename(file_path)
            list_item = QtWidgets.QListWidgetItem(file_name)
            card = ClickMeta(extra=False, avatar_size=(35, 50))
            card.setup_data({"title": file_name})
            self.page_list.addItem(list_item)
            self.page_list.setItemWidget(list_item, card)

    def on_card_selected(self, current, previous):
        if current:
            index = self.page_list.row(current)
            self.curr_tblock_item = None
            self.run_threaded(
                lambda: self.load_image(self.image_files[index]),
                lambda result: self.display_image_from_loaded(result, index),
                self.default_error_handler,
                None
            )

    def navigate_images(self, direction: int):
        if self.image_files:
            new_index = self.curr_img_idx + direction
            if 0 <= new_index < len(self.image_files):
                item = self.page_list.item(new_index)
                self.page_list.setCurrentItem(item)

    def handle_image_deletion(self, file_names: list[str]):
        """Handles the deletion of images based on the provided file names."""
        self.save_current_image_state()

        for file_name in file_names:
            file_path = next((f for f in self.image_files if os.path.basename(f) == file_name), None)
            if file_path:
                self.image_files.remove(file_path)
                self.image_data.pop(file_path, None)
                self.image_history.pop(file_path, None)
                self.in_memory_history.pop(file_path, None)
                self.current_history_index.pop(file_path, None)

                if file_path in self.undo_stacks:
                    stack = self.undo_stacks[file_path]
                    self.undo_group.removeStack(stack)
                    self.undo_stacks.pop(file_path, None)

                if file_path in self.displayed_images:
                    self.displayed_images.remove(file_path)

                if file_path in self.loaded_images:
                    self.loaded_images.remove(file_path)

        if self.image_files:
            if self.curr_img_idx >= len(self.image_files):
                self.curr_img_idx = len(self.image_files) - 1
            new_index = max(0, self.curr_img_idx - 1)
            file = self.image_files[new_index]
            im = self.load_image(file)
            self.display_image_from_loaded(im, new_index, False)
            self.update_image_cards()
            self.page_list.blockSignals(True)
            self.page_list.setCurrentRow(new_index)
            self.page_list.blockSignals(False)
        else:
            self.curr_img_idx = -1
            self.central_stack.setCurrentWidget(self.drag_browser)
            self.update_image_cards()

    def display_image_from_loaded(self, cv2_image, index, switch_page=True):
        file_path = self.image_files[index]
        self.image_data[file_path] = cv2_image

        if file_path not in self.image_history:
            self.image_history[file_path] = [file_path]
            self.in_memory_history[file_path] = [cv2_image.copy()]
            self.current_history_index[file_path] = 0

        self.display_image(index, switch_page)

        if file_path not in self.loaded_images:
            self.loaded_images.append(file_path)
            if len(self.loaded_images) > MAX_IMAGES_IN_MEMORY:
                oldest_image = self.loaded_images.pop(0)
                del self.image_data[oldest_image]
                self.in_memory_history[oldest_image] = []

    def set_cv2_image(self, cv2_img: np.ndarray):
        """Set the current image data directly without undo command."""
        if self.curr_img_idx >= 0:
            file_path = self.image_files[self.curr_img_idx]
            self.image_data[file_path] = cv2_img
            self.image_viewer.display_cv2_image(cv2_img)
            self._set_original_button_checked(False)

    def display_image(self, index: int, switch_page=True):
        if 0 <= index < len(self.image_files):
            self.image_viewer.hide_original_overlay()
            self._set_original_button_checked(False)
            if switch_page:
                self.save_current_image_state()
                self.clear_multi_selection()
            self.curr_img_idx = index
            file_path = self.image_files[index]

            if file_path in self.undo_stacks:
                self.undo_group.setActiveStack(self.undo_stacks[file_path])

            first_time_display = file_path not in self.displayed_images
            self.load_image_state(file_path)
            logger.info(f"[BLK_LIST_UPDATE] Caricata immagine {os.path.basename(file_path)}, blk_list contiene {len(self.blk_list)} elementi")

            self.central_stack.setCurrentWidget(self.image_viewer)
            self.central_stack.layout().activate()

            if first_time_display:
                self.image_viewer.smartFit()
                self.displayed_images.add(file_path)

    # ------------------------------------------------------------------ #
    #  Image State Persistence
    # ------------------------------------------------------------------ #

    def save_image_state(self, file: str):
        """Salva lo stato completo dell'immagine inclusi i text_items"""
        start_time = time.perf_counter()

        if (
            0 <= getattr(self, "curr_img_idx", -1) < len(getattr(self, "image_files", []))
            and self.image_files[self.curr_img_idx] == file
        ):
            sync_viewer_photo_to_image_data(self.image_viewer)
        
        # Get viewer state once (includes text_items_state which has toHtml results)
        viewer_state = self.image_viewer.save_state()
        existing_overlays_hidden = bool(
            self.image_states.get(file, {})
            .get('viewer_state', {})
            .get('overlays_hidden', False)
        )
        if existing_overlays_hidden:
            viewer_state['overlays_hidden'] = True
        existing_text_boxes_hidden = bool(
            self.image_states.get(file, {})
            .get('viewer_state', {})
            .get('text_boxes_hidden', False)
        )
        if existing_text_boxes_hidden:
            viewer_state['text_boxes_hidden'] = True
        current_text_items = [
            serialize_text_item(item)
            for item in self.image_viewer.text_items
            if item is not None
        ]
        current_svg_items = serialize_svg_items(self.image_viewer)

        blk_list_to_save = []
        if self.blk_list is not None:
            try:
                # Use shallow copy of the list
                blk_list_to_save = list(self.blk_list)
                for blk in blk_list_to_save:
                    if blk is not None:
                        ensure_block_id(blk)
                logger.debug(f"[SAVE_PERF] blk_list copy: {len(blk_list_to_save)} items")
            except Exception as e:
                logger.error(f"[BLK_LIST_UPDATE] Errore nel salvare blk_list per {os.path.basename(file)}: {str(e)}")
                blk_list_to_save = []
        else:
            logger.warning(f"[BLK_LIST_UPDATE] blk_list è None per {os.path.basename(file)}, salvata lista vuota")

        self.image_states[file] = {
            'viewer_state': viewer_state,
            'source_lang': self.s_combo.currentText(),
            'target_lang': self.t_combo.currentText(),
            'brush_strokes': self.image_viewer.save_brush_strokes(),
            'blk_list': blk_list_to_save,
            'text_items_data': current_text_items,
            'svg_items_data': current_svg_items,
        }
        
        elapsed = (time.perf_counter() - start_time) * 1000
        logger.info(f"[SAVE_PERF] save_image_state per {os.path.basename(file)} completato in {elapsed:.2f}ms")

    def save_current_image_state(self):
        if (self.curr_img_idx >= 0 and
            self.image_files and
            self.curr_img_idx < len(self.image_files)):
            current_file = self.image_files[self.curr_img_idx]
            self.save_image_state(current_file)
        else:
            pass

    def load_image_state(self, file_path: str, update_ui: bool = True, show_overlays: bool = True):
        """Carica lo stato completo dell'immagine inclusi i text_items"""
        cv2_image, matched_key, source = resolve_cached_image(
            file_path,
            self.image_data,
            self.load_image,
            cache_setter=lambda key, image: self.image_data.__setitem__(key, image),
        )
        if cv2_image is None:
            raise FileNotFoundError(
                f"Immagine non disponibile per load_image_state: {file_path}"
            )
        if source != "cache_direct":
            logger.info(
                "[IMAGE_CACHE] load_image_state ha risolto %s via %s (matched=%s)",
                file_path,
                source,
                matched_key,
            )

        if update_ui:
            self.set_cv2_image(cv2_image)

        if file_path in self.image_states:
            state = self.image_states[file_path]
            if state.get('viewer_state', {}).get('overlays_hidden', False):
                show_overlays = False

            # Carica blk_list o text_blocks (fallback)
            loaded_blocks = []
            if 'blk_list' in state and state['blk_list']:
                loaded_blocks = state['blk_list']
                logger.info(f"[BLK_LIST_UPDATE] Caricata blk_list con {len(loaded_blocks)} elementi per {os.path.basename(file_path)}")
            elif 'text_blocks' in state and state['text_blocks']:
                loaded_blocks = state['text_blocks']
                logger.info(f"[BLK_LIST_UPDATE] Fallback a text_blocks con {len(loaded_blocks)} elementi per {os.path.basename(file_path)}")
            else:
                if self.project_file:
                    logger.warning(f"[BLK_LIST_UPDATE] Nessuna blk_list o text_blocks trovata per {os.path.basename(file_path)}")

            self.blk_list = loaded_blocks.copy() if hasattr(loaded_blocks, 'copy') else list(loaded_blocks)

            if update_ui:
                self.image_viewer.clear_rectangles()
                self.image_viewer.load_state(state['viewer_state'], show_overlays=show_overlays)
                self.s_combo.setCurrentText(state.get('source_lang', ''))
                self.t_combo.setCurrentText(state.get('target_lang', ''))
                # .get(): gli stati creati dai worker non hanno sempre brush_strokes
                self.image_viewer.load_brush_strokes(state.get('brush_strokes', []))
                restore_svg_items(
                    self.image_viewer,
                    state.get('svg_items_data', []),
                    os.path.join(self.temp_dir, "ctpr_svg_cache", os.path.basename(file_path)),
                )

                # Se abbiamo blocchi ma non rettangoli (es. dopo Detect All), caricali ora
                if show_overlays and self.blk_list and not self.image_viewer.rectangles and hasattr(self, 'pipeline'):
                    logger.info(f"[UI_SYNC] Generazione rettangoli mancanti per {os.path.basename(file_path)}")
                    self.pipeline.load_box_coords(self.blk_list)

            if update_ui:
                for text_item in self.image_viewer.text_items[:]:
                    if text_item.scene():
                        text_item.scene().removeItem(text_item)
                self.image_viewer.text_items.clear()

            text_items_to_load = []
            if 'text_items_data' in state and state['text_items_data']:
                text_items_to_load = state['text_items_data']
            elif 'viewer_state' in state and 'text_items_state' in state['viewer_state'] and state['viewer_state']['text_items_state']:
                text_items_to_load = state['viewer_state']['text_items_state']

            if update_ui:
                created_count = 0
                for i, item_data in enumerate(text_items_to_load):
                    try:
                        text_item = create_text_item_from_data(item_data, self.image_viewer.photo)
                        self.image_viewer._scene.addItem(text_item)
                        self.image_viewer.text_items.append(text_item)
                        self.connect_text_item_signals(text_item)

                        created_count += 1

                    except Exception as e:
                        print(f"[WARNING] Errore nel ripristino text_item {i+1}: {str(e)}")
                        import traceback
                        print(f"[DEBUG] Traceback: {traceback.format_exc()}")

                if show_overlays:
                    for rect_item in self.image_viewer.rectangles:
                        self.connect_rect_item_signals(rect_item)

                self._link_text_items_to_blocks()

        if update_ui:
            refresh_text_edits_for_current_block(self)
            # Sincronizza l'etichetta del pulsante toggle text boxes con lo
            # stato persistito per l'immagine appena caricata.
            if hasattr(self, "sync_toggle_text_boxes_label"):
                self.sync_toggle_text_boxes_label()

    # ------------------------------------------------------------------ #
    #  Project Save
    # ------------------------------------------------------------------ #

    def save_current_image(self, file_path: str):
        deactivate_viewer_selections(self.image_viewer)
        curr_image = self.image_viewer.get_cv2_image(paint_all=True)
        success = cv2.imwrite(file_path, curr_image)
        if not success:
            raise ValueError(f"cv2.imwrite ha restituito False per: {file_path}")
        try:
            if hasattr(self, 'pipeline') and hasattr(self.pipeline, '_cleanup_stray_translated_files'):
                self.pipeline._cleanup_stray_translated_files()
        except Exception:
            pass

    def save_and_make(self, output_path: str):
        deactivate_viewer_selections(self.image_viewer)
        self.save_current_image_state()
        self.run_threaded(self.save_and_make_worker, None, self.default_error_handler, None, output_path)

    def save_and_make_worker(self, output_path: str):
        from modules.utils.archives import make
        temp_dir = tempfile.mkdtemp()
        try:
            for file_path in self.image_files:
                bname = os.path.basename(file_path)
                cv2_img = self.load_image(file_path)
                renderer = ImageSaveRenderer(cv2_img)
                viewer_state = self.image_states[file_path]['viewer_state']
                renderer.add_state_to_image(viewer_state)
                sv_pth = os.path.join(temp_dir, bname)
                renderer.save_image(sv_pth)
            comic_xml = None
            try:
                from app.controllers.comic_info_controller import get_comic_info_xml
                comic_xml = get_comic_info_xml(self)
            except Exception:
                comic_xml = None
            make(temp_dir, output_path, comic_info_xml=comic_xml)
        finally:
            shutil.rmtree(temp_dir)
            try:
                if hasattr(self, 'pipeline') and hasattr(self.pipeline, '_cleanup_stray_translated_files'):
                    self.pipeline._cleanup_stray_translated_files()
            except Exception:
                pass

    def launch_save_proj_dialog(self, save_type="single"):
        """Apre il dialog di salvataggio con memorizzazione dell'ultima cartella e suggerimenti nomi file"""
        settings = QSettings("ComicLabs", "KomicTranslate")
        last_save_dir = settings.value("last_save_directory", os.path.expanduser("~"))
        suggested_name = self._get_suggested_filename(save_type)
        suggested_path = os.path.join(last_save_dir, suggested_name)

        file_dialog = QtWidgets.QFileDialog()
        file_name, _ = file_dialog.getSaveFileName(
            self,
            "Salva Progetto Come",
            suggested_path,
            "File Progetto (*.ctpr);;Tutti i File (*)"
        )

        if file_name:
            file_name = normalize_ctpr_path(file_name)
            selected_dir = os.path.dirname(file_name)
            settings.setValue("last_save_directory", selected_dir)
            settings.sync()

        return file_name

    def _get_suggested_filename(self, save_type):
        """Genera il nome file suggerito basato sul tipo di salvataggio"""
        if save_type == "single":
            if self.curr_img_idx >= 0 and self.curr_img_idx < len(self.image_files):
                current_file = self.image_files[self.curr_img_idx]
                base_name = os.path.splitext(os.path.basename(current_file))[0]
                return f"{base_name}.ctpr"
            else:
                return "immagine_corrente.ctpr"
        else:
            if len(self.image_files) >= 2:
                first_file = os.path.splitext(os.path.basename(self.image_files[0]))[0]
                last_file = os.path.splitext(os.path.basename(self.image_files[-1]))[0]
                return f"{first_file}-{last_file}.ctpr"
            elif len(self.image_files) == 1:
                single_file = os.path.splitext(os.path.basename(self.image_files[0]))[0]
                return f"{single_file}.ctpr"
            else:
                return "tutte_immagini.ctpr"

    def run_save_proj(self, file_name):
        self.project_file = file_name
        self.loading.setVisible(True)
        self.disable_hbutton_group()
        self.run_threaded(self.save_project, None,
                          self.default_error_handler, self.on_manual_finished, file_name)

    def thread_save_project(self):
        """Thread per salvare il progetto con popup di scelta"""
        if self.image_files and len(self.image_files) > 0:
            deactivate_viewer_selections(self.image_viewer)
            self.save_current_image_state()
        else:
            print("[WARNING] Nessuna immagine caricata, salto il salvataggio dello stato")

        choice = self.show_save_choice_dialog()
        if choice is None:
            return

        file_name = ""
        if self.project_file and choice == "single":
            file_name = self.project_file
        else:
            file_name = self.launch_save_proj_dialog(choice)

        if file_name:
            save_callback = self.save_project_new if choice == "single" else self.save_project_all_images
            success, saved_path = execute_ctpr_save(
                self,
                file_name,
                save_callback,
                f"thread_save_project:{choice}",
            )

            if success:
                self.project_file = saved_path
                print(f"[DEBUG] Progetto salvato con successo: {saved_path}")
            else:
                print(f"[ERROR] Errore nel salvataggio del progetto")

    def thread_save_as_project(self):
        """Thread per salvare il progetto come nuovo file"""
        choice = self.show_save_choice_dialog()
        if choice is None:
            return

        file_name = self.launch_save_proj_dialog(choice)
        if file_name:
            deactivate_viewer_selections(self.image_viewer)
            self.save_current_image_state()

            save_callback = self.save_project_new if choice == "single" else self.save_project_all_images
            success, saved_path = execute_ctpr_save(
                self,
                file_name,
                save_callback,
                f"thread_save_as_project:{choice}",
            )

            if success:
                self.project_file = saved_path
                print(f"[DEBUG] Progetto salvato come: {saved_path}")
            else:
                print(f"[ERROR] Errore nel salvataggio del progetto")

    def _is_batch_safe_for_save(self):
        """Verifica se è sicuro salvare tutte le immagini dopo operazioni batch"""
        if hasattr(self, 'progress_bar') and self.progress_bar.isVisible():
            return False

        if hasattr(self, '_batch_completed_shown'):
            if not self._batch_completed_shown:
                return False

        if (hasattr(self, '_total_images_in_batch') and hasattr(self, '_images_updated_visually') and
            self._total_images_in_batch > 0):
            if len(self._images_updated_visually) < self._total_images_in_batch:
                return False

        if hasattr(self, 'image_files') and hasattr(self, 'image_states'):
            for image_file in self.image_files:
                if image_file not in self.image_states:
                    return False

        if not hasattr(self, 'image_files') or len(self.image_files) <= 1:
            return False

        missing_images = []
        for image_file in self.image_files:
            if image_file not in self.image_data and not os.path.exists(image_file):
                missing_images.append(os.path.basename(image_file))

        if missing_images:
            return False

        return True

    def show_save_choice_dialog(self):
        """Mostra dialog per scegliere tra salvare immagine singola o tutte le immagini"""
        if len(self.image_files) <= 1:
            return "single"

        from PySide6.QtWidgets import QMessageBox

        batch_safe = self._is_batch_safe_for_save()

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Salva Progetto")

        if batch_safe:
            msg_box.setText(f"Hai {len(self.image_files)} immagini caricate.\nCome vuoi salvare il progetto?")
        else:
            msg_box.setText(f"Hai {len(self.image_files)} immagini caricate.\nCome vuoi salvare il progetto?\n\nNOTA: 'Tutte le immagini' sarà disponibile dopo il completamento delle operazioni batch.")

        single_button = msg_box.addButton("Solo immagine corrente", QMessageBox.ButtonRole.ActionRole)
        all_button = msg_box.addButton("Tutte le immagini", QMessageBox.ButtonRole.ActionRole)
        cancel_button = msg_box.addButton("Annulla", QMessageBox.ButtonRole.RejectRole)

        if not batch_safe:
            all_button.setEnabled(False)
            msg_box.setDefaultButton(single_button)
        else:
            msg_box.setDefaultButton(all_button)

        msg_box.exec()

        clicked_button = msg_box.clickedButton()
        if clicked_button == single_button:
            return "single"
        elif clicked_button == all_button and batch_safe:
            return "all"
        else:
            return None

    def save_project(self, file_name):
        """Wrapper che usa il nuovo sistema di salvataggio"""
        return self.save_project_new(file_name)

    def _sanitize_viewer_state_for_project(self, viewer_state):
        rectangles = []
        for rect in viewer_state.get('rectangles', []):
            rectangles.append({
                'rect': [float(v) for v in rect.get('rect', (0, 0, 0, 0))],
                'rotation': float(rect.get('rotation', 0.0)),
                'is_rectangle': bool(rect.get('is_rectangle', True)),
                'visible': bool(rect.get('visible', True)),
                'enabled': bool(rect.get('enabled', True)),
                'z_value': float(rect.get('z_value', 0.0)),
                'transform_origin': [float(v) for v in rect.get('transform_origin', (0, 0))],
            })
        return {
            'transform': [float(v) for v in viewer_state.get('transform', (1, 0, 0, 0, 1, 0, 0, 0, 1))],
            'center': [float(v) for v in viewer_state.get('center', (0, 0))],
            'scene_rect': [float(v) for v in viewer_state.get('scene_rect', (0, 0, 0, 0))],
            'rectangles': rectangles,
            'text_items_state': [],
            # Queste due flag venivano scartate: image_viewer.save_state() le
            # produce e load_state() le rilegge, quindi senza di esse gli overlay
            # ricomparivano al riaprire il progetto e il label del toggle era errato.
            'overlays_hidden': bool(viewer_state.get('overlays_hidden', False)),
            'text_boxes_hidden': bool(viewer_state.get('text_boxes_hidden', False)),
        }

    def _build_ctpr_page(self, image_file, page_index, display_relpath, original_relpath=None):
        state = self.image_states.get(image_file, {})
        text_blocks = []
        for blk in state.get('blk_list', []):
            if blk and hasattr(blk, 'xyxy') and blk.xyxy is not None:
                ensure_block_id(blk)
                block_data = serialize_text_block(blk)
                if block_data is not None:
                    text_blocks.append(block_data)
        page = {
            'page_id': f"page_{page_index:03d}",
            'index': int(page_index),
            'source_name': os.path.basename(image_file),
            'image': {
                'display_relpath': display_relpath,
                'original_relpath': original_relpath,
            },
            'viewer_state': self._sanitize_viewer_state_for_project(state.get('viewer_state', {})),
            'brush_strokes': serialize_brush_strokes(state.get('brush_strokes', [])),
            'text_blocks': text_blocks,
            'text_items': list(state.get('text_items_data', [])),
            'svg_items': list(state.get('svg_items_data', [])),
        }
        logger.info(
            "[CTPR_SAVE] page=%s blocks=%d text_items=%d svg=%d brush=%d rects=%d",
            page['page_id'],
            len(page['text_blocks']),
            len(page['text_items']),
            len(page['svg_items']),
            len(page['brush_strokes']),
            len(page['viewer_state'].get('rectangles', [])),
        )
        return page

    def _prepare_project_extract_dir(self):
        extract_dir = os.path.join(self.temp_dir, "loaded_ctpr")
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        os.makedirs(extract_dir, exist_ok=True)
        self.project_extract_dir = extract_dir
        return extract_dir

    def save_project_new(self, file_name):
        """Nuovo sistema di salvataggio pulito per file .ctpr"""
        print(f"[DEBUG] Inizio salvataggio nuovo progetto: {file_name}")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Inizializzate PRIMA dell'if: sotto erano assegnate solo dentro
                # 'if 0 <= curr_img_idx < len(image_files)' ma usate piu' fuori,
                # causando UnboundLocalError con nessuna pagina selezionata
                # (curr_img_idx == -1). L'eccezione veniva catturata dal
                # blocco generico sotto e il salvataggio falliva in silenzio.
                current_file = None
                base_name = ""
                cleaned_path = None

                # Senza pagina corrente non c'è un progetto da salvare: esci subito
                # con un motivo chiaro invece di costruire dati incoerenti.
                if not (0 <= self.curr_img_idx < len(self.image_files)):
                    print(
                        "[ERROR] Salvataggio annullato: nessuna pagina selezionata "
                        f"(curr_img_idx={self.curr_img_idx}, "
                        f"immagini caricate={len(self.image_files)})"
                    )
                    return False

                images_dir = os.path.join(temp_dir, "images")
                originals_dir = os.path.join(temp_dir, "originals")
                os.makedirs(images_dir, exist_ok=True)
                os.makedirs(originals_dir, exist_ok=True)

                self.save_current_image_state()

                if self.curr_img_idx >= 0 and self.curr_img_idx < len(self.image_files):
                    current_file = self.image_files[self.curr_img_idx]
                    base_name = os.path.splitext(os.path.basename(current_file))[0]
                    cleaned_name = f"{base_name}.jpg"
                    cleaned_path = os.path.join(images_dir, cleaned_name)

                    if current_file in self.image_data:
                        cleaned_image = self.image_data[current_file]
                        success = cv2.imwrite(
                            cleaned_path,
                            cv2.cvtColor(cleaned_image, cv2.COLOR_RGB2BGR),
                        )
                        if not success:
                            raise ValueError(f"cv2.imwrite ha restituito False per: {cleaned_path}")
                        print(f"[DEBUG] Salvata immagine pulita: {cleaned_name}")
                    elif os.path.exists(current_file):
                        shutil.copy2(current_file, cleaned_path)
                        print(f"[DEBUG] Salvata immagine originale (fallback): {current_file}")
                    else:
                        print(f"[ERROR] Nessuna immagine disponibile per il salvataggio")
                        return False

                def color_to_string(color, default_color=DEFAULT_FONT_COLOR):
                    """Converte un QColor in stringa esadecimale"""
                    if hasattr(color, 'name'):
                        return color.name()
                    elif isinstance(color, str):
                        return color
                    else:
                        return default_color
                original_relpath = None
                if current_file in self.original_images:
                    original_path = os.path.join(originals_dir, cleaned_name)
                    success = cv2.imwrite(
                        original_path,
                        cv2.cvtColor(self.original_images[current_file], cv2.COLOR_RGB2BGR),
                    )
                    if not success:
                        raise ValueError(f"cv2.imwrite ha restituito False per: {original_path}")
                    original_relpath = os.path.relpath(original_path, temp_dir).replace("\\", "/")

                page = self._build_ctpr_page(
                    current_file,
                    0,
                    os.path.relpath(cleaned_path, temp_dir).replace("\\", "/"),
                    original_relpath,
                )

                project_data = {
                    'version': '4.0',
                    'created_with': 'KomicTranslate',
                    'save_type': 'pages',
                    'pages': [page],
                    'source_lang': str(self.s_combo.currentText()),
                    'target_lang': str(self.t_combo.currentText()),
                    'current_image_index': int(self.curr_img_idx),
                    'total_images': 1,
                    'comic_info': dict(getattr(self, 'comic_info', {}) or {}),
                }

                project_path = os.path.join(temp_dir, "project_data.json")
                with open(project_path, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, ensure_ascii=False, indent=2)

                print(f"[DEBUG] Salvati dati progetto in JSON")

                # Scrittura ATOMICA: prima si scriveva direttamente su file_name, quindi un
                # crash (Ctrl+C, disco pieno) a meta' troncava il progetto
                # precedente già salvato. Ora si scrive su un .tmp e si rinomina.
                tmp_zip_path = file_name + ".tmp"
                try:
                    with zipfile.ZipFile(tmp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, _, files in os.walk(temp_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, temp_dir)
                                zipf.write(file_path, arcname)
                                print(f"[DEBUG] Aggiunto al ZIP: {arcname}")
                    os.replace(tmp_zip_path, file_name)
                except Exception:
                    try:
                        if os.path.exists(tmp_zip_path):
                            os.remove(tmp_zip_path)
                    except Exception:
                        pass
                    raise

                print(f"[DEBUG] Progetto salvato con successo: {file_name}")
                try:
                    if hasattr(self, 'pipeline') and hasattr(self.pipeline, '_cleanup_stray_translated_files'):
                        self.pipeline._cleanup_stray_translated_files()
                except Exception:
                    pass
                return True

            except Exception as e:
                print(f"[ERROR] Errore durante il salvataggio: {str(e)}")
                import traceback
                traceback.print_exc()
                return False

    def save_project_all_images(self, file_name):
        """Salva tutte le immagini caricate nel progetto"""
        print(f"[DEBUG] Inizio salvataggio progetto multi-immagine: {file_name}")

        if not hasattr(self, 'image_files') or not self.image_files:
            print(f"[ERROR] Nessuna immagine caricata da salvare")
            return False

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                images_dir = os.path.join(temp_dir, "images")
                original_dir = os.path.join(temp_dir, "originals")
                os.makedirs(images_dir, exist_ok=True)
                os.makedirs(original_dir, exist_ok=True)
                self.save_current_image_state()

                valid_images = []
                for img in self.image_files:
                    if (
                        os.path.exists(img)
                        or img in self.image_data
                        or img in self.image_history
                        or img in self.original_images
                    ):
                        valid_images.append(img)
                        if img in self.image_data and not os.path.exists(img):
                            print(f"[DEBUG] Immagine trovata in memoria: {os.path.basename(img)}")

                if not valid_images:
                    print(f"[ERROR] Nessuna immagine valida trovata per il salvataggio")
                    print(f"[DEBUG] image_files: {[os.path.basename(f) for f in self.image_files]}")
                    print(f"[DEBUG] image_data keys: {[os.path.basename(k) for k in self.image_data.keys()]}")
                    print(f"[DEBUG] original_images keys: {[os.path.basename(k) for k in self.original_images.keys()]}")
                    return False

                saved_images = 0
                saved_originals = 0
                image_manifest = []
                for idx, image_file in enumerate(self.image_files):
                    original_file_name = os.path.basename(image_file)
                    image_subdir = os.path.join(images_dir, f"{idx:03d}")
                    original_subdir = os.path.join(original_dir, f"{idx:03d}")
                    os.makedirs(image_subdir, exist_ok=True)
                    os.makedirs(original_subdir, exist_ok=True)

                    cleaned_name = original_file_name
                    cleaned_path = os.path.join(images_dir, cleaned_name)
                    cleaned_image = None
                    try:
                        cleaned_image = self.load_image(image_file)
                    except Exception as exc:
                        print(f"[WARNING] load_image fallito per {image_file}: {exc}")

                    cleaned_path = os.path.join(image_subdir, cleaned_name)
                    cleaned_relpath = os.path.relpath(cleaned_path, temp_dir).replace("\\", "/")
                    original_relpath = None

                    if cleaned_image is not None:
                        success = cv2.imwrite(
                            cleaned_path,
                            cv2.cvtColor(cleaned_image, cv2.COLOR_RGB2BGR),
                        )
                        if not success:
                            raise ValueError(f"cv2.imwrite ha restituito False per: {cleaned_path}")
                        print(f"[DEBUG] Salvata immagine pulita: {cleaned_name}")
                        saved_images += 1
                    elif os.path.exists(image_file):
                        shutil.copy2(image_file, cleaned_path)
                        print(f"[DEBUG] Salvata immagine da disco (fallback): {cleaned_name}")
                        saved_images += 1
                    elif image_file in self.original_images:
                        original_fallback = self.original_images[image_file]
                        success = cv2.imwrite(
                            cleaned_path,
                            cv2.cvtColor(original_fallback, cv2.COLOR_RGB2BGR),
                        )
                        if not success:
                            raise ValueError(f"cv2.imwrite ha restituito False per: {cleaned_path}")
                        print(f"[DEBUG] Salvata immagine da original_images (fallback): {cleaned_name}")
                        saved_images += 1
                    else:
                        print(f"[WARNING] Immagine {idx} non disponibile in memoria: {image_file}")

                    original_image = self.original_images.get(image_file)
                    if original_image is not None:
                        original_path = os.path.join(original_subdir, original_file_name)
                        success = cv2.imwrite(
                            original_path,
                            cv2.cvtColor(original_image, cv2.COLOR_RGB2BGR),
                        )
                        if not success:
                            raise ValueError(f"cv2.imwrite ha restituito False per: {original_path}")
                        original_relpath = os.path.relpath(original_path, temp_dir).replace("\\", "/")
                        print(f"[DEBUG] Salvata immagine originale: {original_file_name}")
                        saved_originals += 1

                    image_manifest.append({
                        'index': int(idx),
                        'source_name': original_file_name,
                        'display_relpath': cleaned_relpath,
                        'original_relpath': original_relpath,
                    })

                if saved_images == 0:
                    raise ValueError("Nessuna immagine e' stata materializzata nel progetto multi-immagine")
                if saved_images != len(self.image_files):
                    raise ValueError(
                        f"Salvataggio multi-immagine incompleto: {saved_images}/{len(self.image_files)} immagini materializzate"
                    )
                print(
                    f"[DEBUG] Immagini salvate nel progetto multi-immagine: "
                    f"{saved_images}/{len(self.image_files)}, originali={saved_originals}"
                )

                def color_to_string(color):
                    if hasattr(color, 'name'):
                        return color.name()
                    elif isinstance(color, str):
                        return color
                    else:
                        return DEFAULT_FONT_COLOR

                pages = []
                manifest_by_index = {
                    entry['index']: entry
                    for entry in image_manifest
                }

                original_index = self.curr_img_idx

                try:
                    for idx, image_file in enumerate(self.image_files):
                        if idx != self.curr_img_idx:
                            print(f"[DEBUG] Sincronizzazione UI temporanea immagine {idx} per salvataggio multi-pagina")
                            self.curr_img_idx = idx
                            self.load_image_state(image_file, update_ui=True)
                        self.save_current_image_state()

                        if image_file in self.image_states:
                            state = self.image_states[image_file]
                            manifest_entry = manifest_by_index.get(idx, {})
                            pages.append(
                                self._build_ctpr_page(
                                    image_file,
                                    idx,
                                    manifest_entry.get('display_relpath'),
                                    manifest_entry.get('original_relpath'),
                                )
                            )
                            print(
                                f"[DEBUG] Salvata pagina {idx}: "
                                f"text_items={len(state.get('text_items_data', []))}, "
                                f"svg={len(state.get('svg_items_data', []))}"
                            )
                        else:
                            print(f"[WARNING] Nessun dato salvato per l'immagine {idx}: {image_file}")
                finally:
                    if (
                        self.image_files
                        and 0 <= original_index < len(self.image_files)
                        and self.curr_img_idx != original_index
                    ):
                        print(f"[DEBUG] Ripristino immagine originale {original_index}")
                        try:
                            self.curr_img_idx = original_index
                            self.load_image_state(self.image_files[original_index], update_ui=True)
                        except Exception as restore_exc:
                            logger.exception(
                                "[CTPR_SAVE] Ripristino UI fallito dopo salvataggio multi-immagine: %s",
                                restore_exc,
                            )

                project_data = {
                    'version': '4.0',
                    'created_with': 'KomicTranslate',
                    'save_type': 'pages',
                    'pages': pages,
                    'source_lang': str(self.s_combo.currentText()),
                    'target_lang': str(self.t_combo.currentText()),
                    'current_image_index': int(self.curr_img_idx),
                    'total_images': int(len(self.image_files)),
                    'image_manifest': image_manifest,
                    'comic_info': dict(getattr(self, 'comic_info', {}) or {}),
                }

                project_path = os.path.join(temp_dir, "project_data.json")
                with open(project_path, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, ensure_ascii=False, indent=2)

                print(f"[DEBUG] Salvati dati progetto multi-immagine in JSON")

                with zipfile.ZipFile(file_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)

                print(f"[DEBUG] Progetto multi-immagine salvato con successo: {file_name}")
                try:
                    if hasattr(self, 'pipeline') and hasattr(self.pipeline, '_cleanup_stray_translated_files'):
                        self.pipeline._cleanup_stray_translated_files()
                except Exception:
                    pass
                return True

            except Exception as e:
                print(f"[ERROR] Errore durante il salvataggio multi-immagine: {str(e)}")
                import traceback
                traceback.print_exc()
                return False

    # ------------------------------------------------------------------ #
    #  Project Load
    # ------------------------------------------------------------------ #

    def create_text_items_from_data(self):
        """Crea i text_items nel thread principale dopo il caricamento"""
        if not hasattr(self, '_pending_text_items'):
            return

        try:
            for item_data in self._pending_text_items:
                try:
                    text_item = TextBlockItem(
                        text=item_data['text'],
                        parent_item=self.image_viewer.photo,
                        font_family=item_data.get('font_family', 'Arial'),
                        font_size=item_data.get('font_size', 12),
                        render_color=item_data.get('text_color', '#000000'),
                        alignment=item_data.get('alignment', 'left'),
                        line_spacing=item_data.get('line_spacing', 1.0),
                        outline_color=outline_color_for_loading(item_data, '#FFFFFF'),
                        outline_width=item_data.get('outline_width', 0) if outline_enabled_from_data(item_data) else 0,
                        bold=item_data.get('bold', False),
                        italic=item_data.get('italic', False),
                        underline=item_data.get('underline', False),
                        outline_enabled=outline_enabled_from_data(item_data),
                    )

                    if 'direction' in item_data:
                        text_item.set_direction(item_data['direction'])

                    if 'width' in item_data:
                        text_item.set_text(item_data['text'], item_data['width'])

                    text_item.setPos(item_data['position'][0], item_data['position'][1])
                    text_item.setRotation(item_data['rotation'])
                    text_item.setScale(item_data.get('scale', 1.0))

                    self.image_viewer._scene.addItem(text_item)
                    text_item.setZValue(TEXT_BOX_Z)
                    self.image_viewer.text_items.append(text_item)
                    self.connect_text_item_signals(text_item)

                    print(f"[DEBUG] Ripristinato text_item: pos=({item_data['position'][0]:.1f}, {item_data['position'][1]:.1f})")

                except Exception as e:
                    print(f"[WARNING] Errore nel ripristino text_item: {str(e)}")

            print(f"[DEBUG] Ripristinati {len(self.image_viewer.text_items)} text_items")
            delattr(self, '_pending_text_items')
            # Use default font size or from settings if available
            font_size = parse_font_size(self.font_size_dropdown.currentText()) if hasattr(self, 'font_size_dropdown') else 20
            self.image_viewer.update_all_markers(font_size=font_size)
            self.image_viewer.viewport().update()
            self._link_text_items_to_blocks()

        except Exception as e:
            print(f"[ERROR] Errore nella creazione text_items: {str(e)}")
            import traceback
            traceback.print_exc()

    def update_ui_from_project(self):
        """Aggiorna l'interfaccia dopo il caricamento del progetto"""
        if hasattr(self, 'image_files') and self.image_files:
            for file in self.image_files:
                if file not in self.undo_stacks:
                    stack = QUndoStack(self)
                    self.undo_stacks[file] = stack
                    self.undo_group.addStack(stack)

            self.page_list.blockSignals(True)
            self.update_image_cards()
            current_row = self.curr_img_idx if 0 <= self.curr_img_idx < len(self.image_files) else 0
            self.page_list.setCurrentRow(current_row)
            self.page_list.blockSignals(False)

            if self.image_files[0] not in self.loaded_images:
                self.loaded_images.append(self.image_files[0])
            if hasattr(self, 'reset_batch_action_gate'):
                self.reset_batch_action_gate()

        if hasattr(self, 'image_viewer') and self.image_viewer.hasPhoto():
            self.central_stack.setCurrentWidget(self.image_viewer)

        print(f"[DEBUG] UI aggiornata dopo caricamento progetto")

    def _apply_project_open_visual_defaults(self):
        """Alla riapertura di un .ctpr mostra solo immagine di fondo e testo vettoriale."""
        if hasattr(self, 'image_states'):
            # list(): il worker batch puo' inserire nuove immagini in
            # image_states mentre iteriamo -> "RuntimeError: dictionary changed
            # size during iteration".
            for state in list(self.image_states.values()):
                viewer_state = state.setdefault('viewer_state', {})
                viewer_state['overlays_hidden'] = True
        if hasattr(self, 'image_viewer') and self.image_viewer:
            self.image_viewer.set_markers_visible(False)
            self.image_viewer.clear_rectangles(page_switch=True)
        if hasattr(self, 'markers_button'):
            self.markers_button.setChecked(False)

    def thread_load_project(self, file_name):
        """Carica il progetto direttamente nel thread principale per evitare problemi di threading"""
        if file_name:
            self._remember_last_open_path(file_name)
        self.clear_state()
        self.clear_all_highlights()
        success = self.load_project(file_name)
        if success:
            self._apply_project_open_visual_defaults()
            self.update_ui_from_project()
            print(f"[DEBUG] Progetto caricato con successo: {file_name}")
        else:
            print(f"[ERROR] Errore nel caricamento del progetto: {file_name}")
            QtWidgets.QMessageBox.critical(self, "Error", "Errore nel caricamento del progetto")

    def log_object_state(self, obj, obj_name):
        """Stampa informazioni dettagliate su un oggetto per il debug."""
        pass

    def rebuild_scene_after_load(self):
        """Ricostruisce gli elementi grafici nella scena dopo il caricamento del progetto."""
        try:
            if hasattr(self, 'curr_img_idx') and hasattr(self, 'image_files'):
                if 0 <= self.curr_img_idx < len(self.image_files):
                    current_file = self.image_files[self.curr_img_idx]
                    cv2_image = self.load_image(current_file)
                    if cv2_image is not None:
                        self.image_viewer.display_cv2_image(cv2_image)

            if hasattr(self, 'rect_items') and self.rect_items:
                for rect_key, rect_item in self.rect_items.items():
                    if rect_item is not None:
                        try:
                            self.image_viewer._scene.addItem(rect_item)
                            self.connect_rect_item_signals(rect_item)
                        except Exception:
                            pass

            if hasattr(self, 'text_blocks') and self.text_blocks:
                for text_block_key, text_block in self.text_blocks.items():
                    if text_block is not None:
                        try:
                            self.image_viewer._scene.addItem(text_block)
                        except Exception:
                            pass

            if hasattr(self, 'text_items') and self.text_items:
                for text_item_key, text_item in self.text_items.items():
                    if text_item is not None:
                        try:
                            self.image_viewer._scene.addItem(text_item)
                            if text_item not in self.image_viewer.text_items:
                                self.image_viewer.text_items.append(text_item)
                            self.connect_text_item_signals(text_item)
                        except Exception:
                            pass
                # Aggiorna i marker dopo aver aggiunto tutti i text items
                font_size = parse_font_size(self.font_size_dropdown.currentText()) if hasattr(self, 'font_size_dropdown') else 20
                self.image_viewer.update_all_markers(font_size=font_size)

            if hasattr(self, 'image_viewer') and self.image_viewer:
                try:
                    self.image_viewer.viewport().update()
                except Exception:
                    pass

        except Exception:
            pass

    def load_project(self, file_name):
        """Wrapper che usa il nuovo sistema di caricamento"""
        print(f"[DEBUG] Inizio caricamento progetto: {file_name}")
        self.project_file = file_name
        return self.load_project_new(file_name)

    def load_project_new(self, file_name):
        """Nuovo sistema di caricamento pulito per file .ctpr - eseguito nel thread principale"""
        print(f"[DEBUG] Inizio caricamento nuovo progetto: {file_name}")

        try:
            temp_dir = self._prepare_project_extract_dir()
            with zipfile.ZipFile(file_name, 'r') as zipf:
                zipf.extractall(temp_dir)
                print(f"[DEBUG] File .ctpr estratto in: {temp_dir}")

            self.clear_all_items_new()
            print(f"[DEBUG] Stato precedente pulito")

            project_path = os.path.join(temp_dir, "project_data.json")
            if not os.path.exists(project_path):
                print(f"[ERROR] File project_data.json non trovato")
                return False

            with open(project_path, 'r', encoding='utf-8') as f:
                project_data = json.load(f)

            print(f"[DEBUG] Dati progetto caricati, versione: {project_data.get('version', 'unknown')}")
            project_data = adapt_project_data_to_pages(temp_dir, project_data)

            if project_data.get('save_type') == 'pages' or 'pages' in project_data:
                return self._load_pages_project(temp_dir, project_data, file_name)

            save_type = project_data.get('save_type', 'single')
            if save_type == 'all_images':
                return self._load_multi_image_project(temp_dir, project_data, file_name)
            else:
                return self._load_single_image_project(temp_dir, project_data, file_name)

        except Exception as e:
            print(f"[ERROR] Errore durante il caricamento: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def _load_pages_project(self, temp_dir, project_data, file_name):
        try:
            pages = project_data.get('pages', [])
            if not pages:
                print("[ERROR] Nessuna pagina trovata nel progetto CTPR")
                return False

            self.image_files = []
            self.image_data = {}
            self.original_images = {}
            self.image_states = {}
            self.image_history = {}
            self.in_memory_history = {}
            self.current_history_index = {}
            self.loaded_images = []
            self.displayed_images = set()

            for page in sorted(pages, key=lambda entry: int(entry.get('index', 0))):
                image_info = page.get('image', {})
                display_relpath = image_info.get('display_relpath')
                if not display_relpath:
                    continue
                display_path = os.path.join(temp_dir, display_relpath)
                display_image = cv2.imread(display_path)
                if display_image is None:
                    print(f"[WARNING] Impossibile caricare immagine pagina: {display_relpath}")
                    continue
                display_image = cv2.cvtColor(display_image, cv2.COLOR_BGR2RGB)
                self.image_files.append(display_path)
                self.image_data[display_path] = display_image

                original_relpath = image_info.get('original_relpath')
                if original_relpath:
                    original_path = os.path.join(temp_dir, original_relpath)
                    original_image = cv2.imread(original_path)
                    if original_image is not None:
                        self.original_images[display_path] = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB)

                blk_list_for_image = []
                for block_data in page.get('text_blocks', []):
                    try:
                        blk_list_for_image.append(deserialize_text_block(block_data))
                    except Exception as e:
                        print(f"[WARNING] Errore nel ripristino text_block: {str(e)}")

                self.image_states[display_path] = {
                    'viewer_state': page.get('viewer_state', {}),
                    'source_lang': project_data.get('source_lang', ''),
                    'target_lang': project_data.get('target_lang', ''),
                    'brush_strokes': deserialize_brush_strokes(page.get('brush_strokes', [])),
                    'blk_list': blk_list_for_image,
                    'text_items_data': page.get('text_items', []),
                    'svg_items_data': page.get('svg_items', []),
                }
                logger.info(
                    "[CTPR_LOAD] page=%s blocks=%d text_items=%d svg=%d brush=%d rects=%d",
                    page.get('page_id', f"page_{len(self.image_files)-1:03d}"),
                    len(blk_list_for_image),
                    len(page.get('text_items', [])),
                    len(page.get('svg_items', [])),
                    len(page.get('brush_strokes', [])),
                    len(page.get('viewer_state', {}).get('rectangles', [])),
                )

            if not self.image_files:
                print("[ERROR] Nessuna immagine valida trovata nel progetto CTPR")
                return False

            current_index = project_data.get('current_image_index', 0)
            self.curr_img_idx = current_index if 0 <= current_index < len(self.image_files) else 0

            for image_file in self.image_files:
                self.current_history_index[image_file] = 0
                self.image_history[image_file] = [image_file]
                self.in_memory_history[image_file] = [self.image_data[image_file].copy()]
                self.loaded_images.append(image_file)
                if image_file not in self.undo_stacks:
                    stack = QUndoStack(self)
                    self.undo_stacks[image_file] = stack
                    self.undo_group.addStack(stack)

            current_file = self.image_files[self.curr_img_idx]
            self.image_viewer.display_cv2_image(self.image_data[current_file])
            if current_file in self.undo_stacks:
                self.undo_group.setActiveStack(self.undo_stacks[current_file])
            self.load_image_state(current_file)
            self._link_text_items_to_blocks()

            if 'source_lang' in project_data:
                self.s_combo.setCurrentText(project_data['source_lang'])
            if 'target_lang' in project_data:
                self.t_combo.setCurrentText(project_data['target_lang'])
            try:
                self.comic_info = dict(project_data.get('comic_info', {}) or {})
            except Exception:
                self.comic_info = {}
            if hasattr(self, 'central_stack') and hasattr(self, 'image_viewer'):
                self.central_stack.setCurrentWidget(self.image_viewer)

            self.project_file = file_name
            print(f"[DEBUG] Progetto CTPR pages caricato con successo")
            return True
        except Exception as e:
            print(f"[ERROR] Errore durante il caricamento progetto pages: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def _load_single_image_project(self, temp_dir, project_data, file_name):
        """Carica un progetto con una singola immagine"""
        try:
            images_dir = os.path.join(temp_dir, "images")

            if not os.path.exists(images_dir):
                print(f"[ERROR] Cartella images/ non trovata nel progetto")
                return False

            search_dir = images_dir

            cleaned_files = glob.glob(os.path.join(search_dir, "*_cleaned.jpg"))
            original_files = [f for f in os.listdir(search_dir) if f.endswith('.jpg') and not f.endswith('_cleaned.jpg')]

            cv2_image = None
            image_path = None

            if cleaned_files:
                cleaned_path = cleaned_files[0]
                cv2_image = cv2.imread(cleaned_path)
                if cv2_image is not None:
                    cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
                    base_name = os.path.basename(cleaned_path).replace('_cleaned.jpg', '.jpg')
                    original_path = os.path.join(images_dir, base_name)
                    if os.path.exists(original_path):
                        image_path = original_path
                    else:
                        image_path = cleaned_path
                    print(f"[DEBUG] Immagine pulita caricata: {cleaned_path}")
            elif original_files:
                original_path = os.path.join(images_dir, original_files[0])
                cv2_image = cv2.imread(original_path)
                if cv2_image is not None:
                    cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
                    image_path = original_path
                    print(f"[DEBUG] Immagine originale caricata come fallback: {original_path}")

            if cv2_image is not None and image_path is not None:
                self.image_files = [image_path]
                self.curr_img_idx = 0
                self.image_data[image_path] = cv2_image
                self.image_viewer.display_cv2_image(cv2_image)
            else:
                print(f"[ERROR] Nessuna immagine valida trovata in {images_dir}")
                return False

            self.blk_list = []
            for block_data in project_data.get('text_blocks', []):
                try:
                    text_block = deserialize_text_block(block_data)
                    self.blk_list.append(text_block)
                except Exception as e:
                    print(f"[WARNING] Errore nel ripristino text_block: {str(e)}")

            print(f"[DEBUG] Ripristinati {len(self.blk_list)} text_blocks")

            for item_data in project_data.get('text_items', []):
                try:
                    direction = item_data.get('direction', 'ltr')
                    if isinstance(direction, str):
                        if direction.lower() in ['rtl', 'righttoleft']:
                            qt_direction = Qt.LayoutDirection.RightToLeft
                        else:
                            qt_direction = Qt.LayoutDirection.LeftToRight
                    else:
                        qt_direction = direction
                    outline_enabled = outline_enabled_from_data(item_data)

                    text_item = TextBlockItem(
                        text=item_data['text'],
                        parent_item=self.image_viewer.photo,
                        font_family=item_data.get('font_family', 'Arial'),
                        font_size=item_data.get('font_size', 12),
                        render_color=item_data.get('text_color', '#000000'),
                        alignment=item_data.get('alignment', 'left'),
                        line_spacing=item_data.get('line_spacing', 1.0),
                        outline_color=outline_color_for_loading(item_data, '#FFFFFF'),
                        outline_width=item_data.get('outline_width', 0) if outline_enabled else 0,
                        bold=item_data.get('bold', False),
                        italic=item_data.get('italic', False),
                        underline=item_data.get('underline', False),
                        direction=qt_direction,
                        outline_enabled=outline_enabled,
                    )

                    if 'width' in item_data:
                        text_item.set_text(item_data['text'], item_data['width'])

                    text_item.setPos(item_data['position'][0], item_data['position'][1])
                    text_item.setRotation(item_data['rotation'])
                    text_item.setScale(item_data.get('scale', 1.0))

                    self.image_viewer._scene.addItem(text_item)
                    text_item.setZValue(TEXT_BOX_Z)
                    self.image_viewer.text_items.append(text_item)
                    self.connect_text_item_signals(text_item)

                    print(f"[DEBUG] Ripristinato text_item: pos=({item_data['position'][0]:.1f}, {item_data['position'][1]:.1f})")

                except Exception as e:
                    print(f"[WARNING] Errore nel ripristino text_item: {str(e)}")

            print(f"[DEBUG] Ripristinati {len(self.image_viewer.text_items)} text_items")
            self.image_viewer.set_markers_visible(False)
            if hasattr(self, 'markers_button'):
                self.markers_button.setChecked(False)

            self._link_text_items_to_blocks()

            if hasattr(self, 'central_stack') and hasattr(self, 'image_viewer'):
                self.central_stack.setCurrentWidget(self.image_viewer)

            if 'source_lang' in project_data:
                self.s_combo.setCurrentText(project_data['source_lang'])
            if 'target_lang' in project_data:
                self.t_combo.setCurrentText(project_data['target_lang'])
            try:
                self.comic_info = dict(project_data.get('comic_info', {}) or {})
            except Exception:
                self.comic_info = {}

            if self.image_files and cv2_image is not None:
                self.save_image_state(self.image_files[0])
                self.image_states[self.image_files[0]]['viewer_state']['overlays_hidden'] = True

            if 'current_image_index' in project_data:
                self.curr_img_idx = project_data['current_image_index']
            else:
                self.curr_img_idx = 0

            try:
                self.image_viewer.viewport().update()
                if hasattr(self.image_viewer, 'photo') and self.image_viewer.photo is not None:
                    self.image_viewer.resetTransform()
                    self.image_viewer.smartFit()
            except Exception as e:
                print(f"[WARNING] Errore nell'aggiornamento viewport: {str(e)}")

            self.project_file = file_name

            print(f"[DEBUG] Progetto singola immagine caricato con successo")
            return True

        except Exception as e:
            print(f"[ERROR] Errore durante il caricamento progetto singola immagine: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def _load_multi_image_project(self, temp_dir, project_data, file_name):
        """Carica un progetto con multiple immagini dalla cartella images/"""
        try:
            images_dir = os.path.join(temp_dir, "images")
            if not os.path.exists(images_dir):
                print(f"[ERROR] Cartella images/ non trovata nel progetto multi-immagine")
                return False

            manifest_entries = project_data.get('image_manifest', [])
            if not manifest_entries:
                all_files = glob.glob(os.path.join(images_dir, "*.jpg"))
                if not all_files:
                    all_files = glob.glob(os.path.join(images_dir, "*", "*.jpg"))
                if not all_files:
                    print(f"[ERROR] Nessuna immagine trovata nella cartella images/ del progetto")
                    return False

            def load_rgb_image(image_path):
                image = cv2.imread(image_path)
                if image is None:
                    return None
                return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            if manifest_entries:
                manifest_entries = sorted(manifest_entries, key=lambda entry: int(entry.get('index', 0)))
                self.image_files = []
                self.image_data = {}
                self.original_images = {}

                for entry in manifest_entries:
                    display_relpath = entry.get('display_relpath')
                    original_relpath = entry.get('original_relpath')
                    if not display_relpath:
                        print(f"[WARNING] Entry manifest senza display_relpath: {entry}")
                        continue

                    display_path = os.path.join(temp_dir, display_relpath)
                    display_image = load_rgb_image(display_path)
                    if display_image is None:
                        print(f"[WARNING] Impossibile caricare immagine display da manifest: {display_relpath}")
                        continue

                    self.image_files.append(display_path)
                    self.image_data[display_path] = display_image

                    if original_relpath:
                        original_path = os.path.join(temp_dir, original_relpath)
                        original_image = load_rgb_image(original_path)
                        if original_image is not None:
                            self.original_images[display_path] = original_image

                if not self.image_files:
                    print(f"[ERROR] Nessuna immagine valida caricata dal manifest del progetto")
                    return False
            else:

                original_matches = [f for f in all_files if not f.endswith('_cleaned.jpg') and not os.path.basename(f).startswith('original_')]
                cleaned_matches = [f for f in all_files if f.endswith('_cleaned.jpg')]

                def extract_index(filename):
                    match = re.search(r'(\d{3})_', os.path.basename(filename))
                    return int(match.group(1)) if match else 0

                original_matches.sort(key=extract_index)
                cleaned_matches.sort(key=extract_index)

                print(f"[DEBUG] Trovate {len(original_matches)} immagini originali e {len(cleaned_matches)} immagini pulite")

                self.image_files = []
                self.image_data = {}
                self.original_images = {}

                for i, original_path in enumerate(original_matches):
                    cleaned_path = None
                    original_index = extract_index(original_path)

                    expected_cleaned_pattern = f"{original_index:03d}_*_cleaned.jpg"
                    potential_cleaned_files = glob.glob(os.path.join(images_dir, expected_cleaned_pattern))
                    potential_cleaned = potential_cleaned_files[0] if potential_cleaned_files else None

                    if potential_cleaned and os.path.exists(potential_cleaned):
                        cleaned_path = potential_cleaned

                    original_file_pattern = f"original_{original_index:03d}_*.jpg"
                    original_files = glob.glob(os.path.join(images_dir, original_file_pattern))

                    if not original_files:
                        all_original_files = glob.glob(os.path.join(images_dir, "original_*.jpg"))
                        original_files = [f for f in all_original_files if f"original_{original_index:03d}_" in os.path.basename(f)]

                    temp_original_image = None
                    print(f"[DEBUG] Cercando pattern: {original_file_pattern} in {images_dir}")
                    print(f"[DEBUG] File trovati: {[os.path.basename(f) for f in original_files]}")
                    if original_files:
                        original_file_path = original_files[0]
                        print(f"[DEBUG] Tentativo di caricare: {original_file_path}")
                        print(f"[DEBUG] File esiste: {os.path.exists(original_file_path)}")
                        original_image = cv2.imread(original_file_path)
                        print(f"[DEBUG] cv2.imread risultato: {original_image is not None}")
                        if original_image is not None:
                            print(f"[DEBUG] Dimensioni immagine: {original_image.shape}")
                            temp_original_image = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB)
                            print(f"[DEBUG] Caricata immagine originale per indice {original_index}: {original_file_path}")
                        else:
                            print(f"[ERROR] Impossibile caricare l'immagine: {original_file_path}")
                    else:
                        print(f"[DEBUG] Nessun file original trovato per pattern: {original_file_pattern}")

                    display_image = None
                    if cleaned_path:
                        display_image = cv2.imread(cleaned_path)
                        print(f"[DEBUG] Caricata immagine pulita per indice {original_index}")
                        if display_image is not None:
                            display_image = cv2.cvtColor(display_image, cv2.COLOR_BGR2RGB)
                    else:
                        display_image = cv2.imread(original_path)
                        print(f"[DEBUG] Caricata immagine originale per indice {original_index}")
                        if display_image is not None:
                            display_image = cv2.cvtColor(display_image, cv2.COLOR_BGR2RGB)

                    if display_image is not None:
                        self.image_files.append(original_path)
                        self.image_data[original_path] = display_image

                        if temp_original_image is not None:
                            self.original_images[original_path] = temp_original_image
                            print(f"[DEBUG] Aggiunta immagine originale a self.original_images con chiave: {os.path.basename(original_path)}")

                if not self.image_files:
                    print(f"[ERROR] Nessuna immagine valida trovata")
                    print(f"[DEBUG] original_matches: {[os.path.basename(f) for f in original_matches]}")
                    print(f"[DEBUG] cleaned_matches: {[os.path.basename(f) for f in cleaned_matches]}")
                    return False

            current_index = project_data.get('current_image_index', 0)
            if 0 <= current_index < len(self.image_files):
                self.curr_img_idx = current_index
            else:
                self.curr_img_idx = 0

            current_file = self.image_files[self.curr_img_idx]
            current_image = self.image_data[current_file]
            self.image_viewer.display_cv2_image(current_image)

            print(f"[DEBUG] Visualizzata immagine {self.curr_img_idx + 1}/{len(self.image_files)}")

            all_text_blocks = project_data.get('all_text_blocks', {})
            all_text_items = project_data.get('all_text_items', {})

            self.image_states = {}

            for idx, image_file in enumerate(self.image_files):
                image_key = str(idx)

                blk_list_for_image = []
                if image_key in all_text_blocks:
                    for block_data in all_text_blocks[image_key]:
                        try:
                            text_block = deserialize_text_block(block_data)
                            blk_list_for_image.append(text_block)
                        except Exception as e:
                            print(f"[WARNING] Errore nel ripristino text_block per immagine {idx}: {str(e)}")

                text_items_data = all_text_items.get(image_key, [])

                self.image_states[image_file] = {
                    'viewer_state': {'overlays_hidden': True},
                    'source_lang': project_data.get('source_lang', ''),
                    'target_lang': project_data.get('target_lang', ''),
                    'brush_strokes': [],
                    'blk_list': blk_list_for_image,
                    'text_items_data': text_items_data
                }

                print(f"[DEBUG] Caricati {len(blk_list_for_image)} text_blocks e {len(text_items_data)} text_items per immagine {idx}")

            current_index = project_data.get('current_image_index', 0)
            if 0 <= current_index < len(self.image_files):
                self.curr_img_idx = current_index
            else:
                self.curr_img_idx = 0

            for image_file in self.image_files:
                if image_file not in self.current_history_index:
                    self.current_history_index[image_file] = 0

                if image_file not in self.image_history:
                    self.image_history[image_file] = [image_file]

                if image_file not in self.in_memory_history:
                    if image_file in self.image_data:
                        self.in_memory_history[image_file] = [self.image_data[image_file].copy()]
                    else:
                        self.in_memory_history[image_file] = []

                if image_file not in self.undo_stacks:
                    stack = QUndoStack(self)
                    self.undo_stacks[image_file] = stack
                    self.undo_group.addStack(stack)

            current_file = self.image_files[self.curr_img_idx]
            current_image = self.image_data[current_file]
            self.image_viewer.display_cv2_image(current_image)

            if current_file in self.undo_stacks:
                self.undo_group.setActiveStack(self.undo_stacks[current_file])

            self.load_image_state(current_file)

            self._link_text_items_to_blocks()

            print(f"[DEBUG] Visualizzata immagine {self.curr_img_idx + 1}/{len(self.image_files)}")

            if 'source_lang' in project_data:
                self.s_combo.setCurrentText(project_data['source_lang'])
            if 'target_lang' in project_data:
                self.t_combo.setCurrentText(project_data['target_lang'])
            try:
                self.comic_info = dict(project_data.get('comic_info', {}) or {})
            except Exception:
                self.comic_info = {}

            if hasattr(self, 'central_stack') and hasattr(self, 'image_viewer'):
                self.central_stack.setCurrentWidget(self.image_viewer)

            if self.image_files and current_image is not None:
                self.save_image_state(self.image_files[self.curr_img_idx])

            try:
                self.image_viewer.viewport().update()
                if hasattr(self.image_viewer, 'photo') and self.image_viewer.photo is not None:
                    self.image_viewer.resetTransform()
                    self.image_viewer.smartFit()
            except Exception as e:
                print(f"[WARNING] Errore nell'aggiornamento viewport: {str(e)}")

            self.project_file = file_name

            print(f"[DEBUG] Progetto multi-immagine caricato con successo: {len(self.image_files)} immagini")
            return True

        except Exception as e:
            print(f"[ERROR] Errore durante il caricamento progetto multi-immagine: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    # ------------------------------------------------------------------ #
    #  Keyboard Event
    # ------------------------------------------------------------------ #

    def keyPressEvent(self, event):
        if (
            event.matches(QtGui.QKeySequence.StandardKey.Delete)
            or event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace)
        ):
            if hasattr(self, "delete_button"):
                self.delete_button.click()
                event.accept()
                return
        if event.key() == QtCore.Qt.Key_Left:
            self.navigate_images(-1)
        elif event.key() == QtCore.Qt.Key_Right:
            self.navigate_images(1)
        elif event.key() == QtCore.Qt.Key_PageUp:
            self._handle_page_navigation(-1, event)
        elif event.key() == QtCore.Qt.Key_PageDown:
            self._handle_page_navigation(1, event)
        else:
            super().keyPressEvent(event)

    def _is_focus_on_text_input(self):
        """Verifica se il focus corrente è su un widget di input testo.
        
        Questo previene che Page Up/Down interferiscano con la digitazione
        in campi di testo, combobox o altri widget interattivi.
        """
        focus_widget = QtWidgets.QApplication.focusWidget()
        if focus_widget is None:
            return False
        text_input_types = (
            QtWidgets.QLineEdit,
            QtWidgets.QTextEdit,
            QtWidgets.QPlainTextEdit,
            QtWidgets.QSpinBox,
            QtWidgets.QDoubleSpinBox,
        )
        return isinstance(focus_widget, text_input_types)

    def _handle_page_navigation(self, direction: int, event):
        """Gestisce la navigazione Page Up/Down con debounce e controllo focus.
        
        Args:
            direction: -1 per Page Up (immagine precedente), 1 per Page Down (successiva)
            event: L'evento tastiera da processare
        """
        # Evita interferenze con widget di input testo
        if self._is_focus_on_text_input():
            super().keyPressEvent(event)
            return
        
        # Debounce: ignora se è passato meno di 100ms dall'ultima navigazione
        now = time.time()
        if not hasattr(self, '_last_page_nav_time'):
            self._last_page_nav_time = 0.0
        if now - self._last_page_nav_time < 0.1:
            return
        self._last_page_nav_time = now
        
        # Verifica limiti sequenza prima di navigare
        if not self.image_files:
            return
        new_index = self.curr_img_idx + direction
        if not (0 <= new_index < len(self.image_files)):
            return
        
        # Effetto fade opzionale per transizione fluida
        self._fade_transition(direction)

    def _fade_transition(self, direction: int):
        """Esegue una transizione fade-out/fade-in sull'image viewer.
        
        Crea un effetto di dissolvenza di 300ms diviso in due fasi:
        1. Fade-out (150ms): riduce l'opacità dell'viewer
        2. Cambio immagine + Fade-in (150ms): ripristina l'opacità
        
        Args:
            direction: Direzione di navigazione (-1 o 1)
        """
        viewer = self.image_viewer
        if viewer is None:
            self.navigate_images(direction)
            return
        
        fade_duration = 150  # ms per ogni fase (fade-out e fade-in)
        
        # Fase 1: Fade-out
        fade_out = QtCore.QPropertyAnimation(viewer, b"windowOpacity")
        fade_out.setDuration(fade_duration)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.3)
        fade_out.setEasingCurve(QtCore.QEasingCurve.Type.InQuad)
        
        # Fase 2: Cambio immagine + Fade-in
        def on_fade_out_finished():
            self.navigate_images(direction)
            fade_in = QtCore.QPropertyAnimation(viewer, b"windowOpacity")
            fade_in.setDuration(fade_duration)
            fade_in.setStartValue(0.3)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QtCore.QEasingCurve.Type.OutQuad)
            fade_in.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        
        fade_out.finished.connect(on_fade_out_finished)
        fade_out.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    # ------------------------------------------------------------------ #
    #  Settings
    # ------------------------------------------------------------------ #

    def process_group(self, group_key, group_value, settings_obj: QSettings):
        """Helper function to process a group and its nested values."""
        if is_dataclass(group_value):
            group_value = asdict(group_value)
        if isinstance(group_value, dict):
            settings_obj.beginGroup(group_key)
            for sub_key, sub_value in group_value.items():
                self.process_group(sub_key, sub_value, settings_obj)
            settings_obj.endGroup()
        else:
            mapped_value = self.settings_page.ui.value_mappings.get(group_value, group_value)
            settings_obj.setValue(group_key, mapped_value)

    def render_settings(self):
        from modules.rendering.render import TextRenderingSettings
        target_lang = self.lang_mapping.get(self.t_combo.currentText(), None)
        direction = get_layout_direction(target_lang)

        return TextRenderingSettings(
            alignment_id = 0,
            font_family = self.font_dropdown.currentText(),
            min_font_size = int(self.settings_page.ui.min_font_spinbox.value()),
            max_font_size = int(self.settings_page.ui.max_font_spinbox.value()),
            color = self.block_font_color_button.property('selected_color'),
            upper_case = self.settings_page.ui.uppercase_checkbox.isChecked(),
            outline = self.outline_enabled,
            outline_color = self.outline_font_color_button.property('selected_color'),
            outline_width = self.outline_width_dropdown.currentText(),
            bold = self.bold_button.isChecked(),
            italic = self.italic_button.isChecked(),
            underline = self.underline_button.isChecked(),
            line_spacing = self.line_spacing_dropdown.currentText(),
            direction = direction
        )

    def save_main_page_settings(self):
        settings = QSettings("ComicLabs", "KomicTranslate")

        self.process_group('text_rendering', self.render_settings(), settings)

        settings.beginGroup("main_page")
        # .get(..., "") invece di []: la lingua caricata da un progetto puo'
        # non essere una chiave di lang_mapping, e un KeyError qui (chiamato da
        # closeEvent) impediva la chiusura della finestra.
        settings.setValue("source_language", self.lang_mapping.get(self.s_combo.currentText(), ""))
        settings.setValue("target_language", self.lang_mapping.get(self.t_combo.currentText(), ""))

        settings.setValue("mode", "manual" if self.manual_radio.isChecked() else "automatic")

        settings.setValue("brush_size", self.image_viewer.brush_size)
        settings.setValue("eraser_size", self.image_viewer.eraser_size)

        # Painting panel: Dim Penna e Tol Secchiello
        if hasattr(self, "pen_size_spinbox"):
            settings.setValue("pen_size", self.pen_size_spinbox.value())
        if hasattr(self, "bucket_tolerance_spinbox"):
            settings.setValue("bucket_tolerance", self.bucket_tolerance_spinbox.value())
        if hasattr(self, "painting_color_button"):
            settings.setValue("painting_color", self.painting_color_button.color().name())

        settings.endGroup()

        settings.beginGroup("MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("state", self.saveState())
        if hasattr(self, "main_splitter") and self.main_splitter is not None:
            settings.setValue("main_splitter_state", self.main_splitter.saveState())
        settings.endGroup()

    def load_main_page_settings(self):
        settings = QSettings("ComicLabs", "KomicTranslate")
        settings.beginGroup("main_page")

        source_lang = settings.value("source_language", "Korean")
        target_lang = settings.value("target_language", "English")

        self.s_combo.setCurrentText(self.reverse_lang_mapping.get(source_lang, self.tr("Korean")))
        self.t_combo.setCurrentText(self.reverse_lang_mapping.get(target_lang, self.tr("English")))

        mode = settings.value("mode", "manual")
        if mode == "manual":
            self.manual_radio.setChecked(True)
            self.manual_mode_selected()
        else:
            self.automatic_radio.setChecked(True)
            self.batch_mode_selected()

        brush_size = int(settings.value("brush_size", 10))
        eraser_size = int(settings.value("eraser_size", 20))
        self.image_viewer.set_br_er_size(brush_size, brush_size, tool_type='brush')
        self.image_viewer.set_br_er_size(eraser_size, eraser_size, tool_type='eraser')

        # Painting panel: ripristina Dim Penna e Tol Secchiello
        pen_size = int(settings.value("pen_size", 5))
        if hasattr(self, "pen_size_spinbox"):
            self.pen_size_spinbox.blockSignals(True)
            self.pen_size_spinbox.setValue(pen_size)
            self.pen_size_spinbox.blockSignals(False)
        self.image_viewer.set_br_er_size(pen_size, pen_size, tool_type='pen')

        bucket_tolerance = int(settings.value("bucket_tolerance", 32))
        if hasattr(self, "bucket_tolerance_spinbox"):
            self.bucket_tolerance_spinbox.blockSignals(True)
            self.bucket_tolerance_spinbox.setValue(bucket_tolerance)
            self.bucket_tolerance_spinbox.blockSignals(False)
        self.image_viewer.bucket_fill_tolerance = bucket_tolerance

        painting_color = settings.value("painting_color", "#000000")
        if hasattr(self, "painting_color_button"):
            self.painting_color_button.set_color(QColor(painting_color))
            self.image_viewer.set_painting_color(QColor(painting_color))

        settings.endGroup()

        settings.beginGroup("MainWindow")
        geometry = settings.value("geometry")
        state = settings.value("state")
        main_splitter_state = settings.value("main_splitter_state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)
        if main_splitter_state is not None and hasattr(self, "main_splitter"):
            # Rimanda il restore di un tick: geometry/state della finestra
            # possono ancora ridistribuire gli spazi subito dopo il load.
            QtCore.QTimer.singleShot(
                0,
                lambda: self.main_splitter.restoreState(main_splitter_state)
            )
        settings.endGroup()

        settings.beginGroup('text_rendering')
        alignment = settings.value('alignment_id', 1, type=int)
        # alignment_tool_group is now momentary, no checked state

        self.font_dropdown.setCurrentText(settings.value('font_family', ''))
        min_font_size = settings.value('min_font_size', 12)
        max_font_size = settings.value('max_font_size', 40)
        try:
            _min_v = int(float(str(min_font_size).replace(',', '.')))
            _max_v = int(float(str(max_font_size).replace(',', '.')))
        except (ValueError, TypeError):
            _min_v, _max_v = 12, 40
        if hasattr(self, '_set_min_max_no_signal'):
            self._set_min_max_no_signal(_min_v, _max_v)
        else:
            self.settings_page.ui.min_font_spinbox.setValue(_min_v)
            self.settings_page.ui.max_font_spinbox.setValue(_max_v)
            if hasattr(self, 'refresh_font_size_dropdown'):
                self.refresh_font_size_dropdown()

        color = settings.value('color', '#000000')
        self.block_font_color_button.setStyleSheet(f"background-color: {color}; border: none; border-radius: 5px;")
        self.block_font_color_button.setProperty('selected_color', color)
        self.settings_page.ui.uppercase_checkbox.setChecked(settings.value('upper_case', False, type=bool))
        if hasattr(self.settings_page.ui, 'pre_ocr_filter_checkbox'):
            self.settings_page.ui.pre_ocr_filter_checkbox.setChecked(
                settings.value('pre_ocr_filter', False, type=bool)
            )
        # outline_button is now momentary, no checked state

        self.line_spacing_dropdown.setCurrentText(settings.value('line_spacing', '1.0'))
        self.outline_width_dropdown.setCurrentText(settings.value('outline_width', '1.0'))
        outline_color = settings.value('outline_color', '#FFFFFF')
        self.outline_font_color_button.setStyleSheet(f"background-color: {outline_color}; border: none; border-radius: 5px;")
        self.outline_font_color_button.setProperty('selected_color', outline_color)

        # style buttons are now momentary, no checked state
        settings.endGroup()

    def closeEvent(self, event):
        self.settings_page.save_settings()
        self.save_main_page_settings()

        for archive in self.file_handler.archive_info:
            temp_dir = archive.get('temp_dir')
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

        if hasattr(self, 'temp_dir') and self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.error(f"Error deleting temp directory {self.temp_dir} in ProjectMixin: {e}")

        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    #  Misc Features
    # ------------------------------------------------------------------ #

    def export_to_pdf(self):
        """Esporta l'immagine corrente come PDF con immagine pulita + testo vettoriale"""
        if self.curr_img_idx < 0 or self.curr_img_idx >= len(self.image_files):
            from app.ui.messages import show_error
            show_error(self.tr("Nessuna immagine caricata"),
                      self.tr("Carica un'immagine prima di esportare in PDF"))
            return

        from PySide6.QtWidgets import QFileDialog
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Esporta come PDF"),
            "",
            "PDF files (*.pdf);;All files (*.*)"
        )

        if not output_path:
            return

        try:
            deactivate_viewer_selections(self.image_viewer)
            current_file = self.image_files[self.curr_img_idx]
            cleaned_image = self.image_data.get(current_file)

            if cleaned_image is None:
                from app.ui.messages import show_error
                show_error(self.tr("Immagine non disponibile"),
                          self.tr("L'immagine pulita non è disponibile. Esegui prima l'inpainting."))
                return

            text_items = [item for item in self.image_viewer.text_items
                         if item.isVisible() and item.scene() is not None]

            if not text_items:
                from app.ui.messages import show_warning
                result = show_warning(self.tr("Nessun testo trovato"),
                                    self.tr("Non ci sono elementi di testo visibili. Continuare comunque?"))
                if not result:
                    return

            scene_rect = self.image_viewer.scene().itemsBoundingRect()
            viewer_width = int(scene_rect.width())
            viewer_height = int(scene_rect.height())

            if viewer_width <= 0 or viewer_height <= 0:
                if hasattr(self.image_viewer, 'photo') and self.image_viewer.photo:
                    pixmap_rect = self.image_viewer.photo.boundingRect()
                    viewer_width = int(pixmap_rect.width())
                    viewer_height = int(pixmap_rect.height())
                else:
                    viewer_height, viewer_width = cleaned_image.shape[:2]

            print(f"[DEBUG] Dimensioni viewer: {viewer_width}x{viewer_height}")
            print(f"[DEBUG] Dimensioni reali: {cleaned_image.shape[1]}x{cleaned_image.shape[0]}")

            from modules.utils.pdf_export import PDFExporter
            pdf_exporter = PDFExporter()

            success = pdf_exporter.export_to_pdf(
                output_path=output_path,
                cleaned_image=cleaned_image,
                text_items=text_items,
                image_width=viewer_width,
                image_height=viewer_height,
                image_quality=85
            )

            if success:
                pass
            else:
                from app.ui.messages import show_error
                show_error(self.tr("Errore nell'esportazione"),
                          self.tr("Si è verificato un errore durante l'esportazione del PDF"))

        except Exception as e:
            print(f"[ERROR] Errore nell'esportazione PDF: {e}")
            from app.ui.messages import show_error
            show_error(self.tr("Errore nell'esportazione"),
                      self.tr(f"Si è verificato un errore: {str(e)}"))

    def join_ctpr_files(self):
        """Apre un dialogo per selezionare più file .ctpr da unire"""
        try:
            from app.ui.dayu_widgets.browser import get_last_open_directory
            file_dialog = QtWidgets.QFileDialog()
            file_dialog.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
            file_dialog.setNameFilter("CTPR files (*.ctpr)")
            file_dialog.setWindowTitle("Seleziona file CTPR da unire")
            file_dialog.setDirectory(get_last_open_directory())

            if file_dialog.exec_() == QtWidgets.QFileDialog.Accepted:
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    self._remember_last_open_path(selected_files)

                if len(selected_files) < 2:
                    QtWidgets.QMessageBox.warning(
                        self, "Avviso",
                        "Seleziona almeno 2 file CTPR da unire."
                    )
                    return

                from app.ui.join_ctpr_dialog import JoinCtprDialog
                join_dialog = JoinCtprDialog(selected_files, self)
                join_dialog.exec_()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Errore",
                f"Errore durante l'unione dei file CTPR: {str(e)}"
            )

    def _get_original_rgb_image(self):
        """Restituisce l'immagine originale (RGB) per la pagina corrente, o None."""
        if not self.image_viewer.hasPhoto() or self.curr_img_idx < 0:
            return None
        current_file = self.image_files[self.curr_img_idx]
        original_filename = f"original_{self.curr_img_idx:03d}.jpg"
        original_path = os.path.join(self.originals_temp_dir, original_filename)
        if os.path.exists(original_path):
            bgr = cv2.imread(original_path)
            if bgr is not None:
                return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        if current_file in self.original_images:
            return self.original_images[current_file].copy()
        if current_file in self.image_data:
            return self.image_data[current_file].copy()
        return None

    def _set_original_button_checked(self, checked: bool):
        btn = getattr(self, 'original_button', None)
        if btn is None:
            return
        try:
            btn.blockSignals(True)
            if hasattr(btn, 'setChecked'):
                btn.setChecked(bool(checked))
        finally:
            btn.blockSignals(False)

    def toggle_original_view(self, checked: bool):
        if checked:
            original_image = self._get_original_rgb_image()
            if original_image is None:
                self._set_original_button_checked(False)
                from app.ui.dayu_widgets.message import MMessage
                MMessage.warning(
                    text=self.tr("Immagine originale non disponibile"),
                    parent=self,
                    duration=3000,
                    closable=True
                )
                return
            if not self.image_viewer.show_original_overlay(original_image):
                self._set_original_button_checked(False)
                return
        else:
            self.image_viewer.hide_original_overlay()

    def show_original_image(self, checked: bool = False):
        """Compat: il pulsante 'Originale' ora e' un toggle on/off."""
        self.toggle_original_view(bool(checked))

    def get_app_settings(self):
        """Restituisce l'oggetto SettingsPage per l'accesso alle impostazioni dell'applicazione"""
        return self.settings_page

    def detect_fonts(self):
        """Rileva i font nei blocchi di testo utilizzando i modelli LLM Vision"""
        try:
            if not self.image_viewer.hasPhoto() or self.curr_img_idx < 0:
                from app.ui.dayu_widgets.message import MMessage
                MMessage.info(
                    text=self.tr("Carica un'immagine prima di rilevare i font"),
                    parent=self,
                    duration=3000,
                    closable=True
                )
                return

            if not self.blk_list:
                from app.ui.dayu_widgets.message import MMessage
                MMessage.info(
                    text=self.tr("Non ci sono blocchi di testo da analizzare. Esegui prima l'OCR o disegna dei text box per rilevare i blocchi di testo."),
                    parent=self,
                    duration=3000,
                    closable=True
                )
                return

            valid_blocks = [blk for blk in self.blk_list
                           if blk and hasattr(blk, 'xyxy') and blk.xyxy is not None]

            if not valid_blocks:
                from app.ui.dayu_widgets.message import MMessage
                MMessage.info(
                    text=self.tr("Non ci sono blocchi di testo validi da analizzare. Esegui prima l'OCR o disegna dei text box."),
                    parent=self,
                    duration=3000,
                    closable=True
                )
                return

            from modules.font_detection.font_detector import FontDetector

            font_detector = FontDetector(self.settings_page)

            available_models = font_detector.get_available_models()

            if not available_models:
                from app.ui.messages import show_error
                show_error(self.tr("Nessun modello Vision disponibile"),
                          self.tr("Non sono disponibili modelli Vision per il rilevamento dei font. Configura un modello GPT, Gemini, Claude o Qwen nelle impostazioni."))
                return

            from modules.font_detection.model_selection_dialog import ModelSelectionDialog
            from PySide6.QtWidgets import QDialog

            model_dialog = ModelSelectionDialog(available_models, self)
            if model_dialog.exec() != QDialog.Accepted:
                return

            selected_model = model_dialog.get_selected_model()
            if not selected_model:
                from app.ui.messages import show_error
                show_error(self.tr("Nessun modello selezionato"),
                          self.tr("Seleziona un modello per continuare"))
                return

            print(f"[DEBUG] self.blk_list contiene {len(self.blk_list)} blocchi")
            for i, blk in enumerate(self.blk_list):
                if blk and hasattr(blk, 'xyxy') and blk.xyxy is not None:
                    print(f"[DEBUG] Blocco {i}: xyxy={blk.xyxy}, angle={getattr(blk, 'angle', 0.0)}")
                else:
                    print(f"[DEBUG] Blocco {i}: invalido o senza coordinate")

            print(f"[DEBUG] Trovati {len(valid_blocks)} blocchi validi")
            for i, blk in enumerate(valid_blocks):
                print(f"[DEBUG] Blocco valido {i}: xyxy={blk.xyxy}, angle={getattr(blk, 'angle', 0.0)}")

            current_file = self.image_files[self.curr_img_idx]
            current_image = None

            if current_file in self.original_images:
                current_image = self.original_images[current_file]
            elif current_file in self.image_data:
                current_image = self.image_data[current_file]

            if current_image is None:
                from app.ui.dayu_widgets.message import MMessage
                MMessage.info(
                    text=self.tr("L'immagine non è disponibile per l'analisi"),
                    parent=self,
                    duration=3000,
                    closable=True
                )
                return

            text_blocks = valid_blocks

            from PySide6.QtWidgets import QProgressDialog
            from PySide6.QtCore import Qt as QtCoreQt

            progress = QProgressDialog(self.tr("Analizzando font..."),
                                      self.tr("Annulla"), 0, len(text_blocks), self)
            progress.setWindowModality(QtCoreQt.WindowModal)
            progress.show()

            font_results = []
            for i, block in enumerate(text_blocks):
                if progress.wasCanceled():
                    break

                progress.setValue(i)
                progress.setLabelText(self.tr(f"Analizzando blocco {i+1} di {len(text_blocks)}..."))

                try:
                    result = font_detector.detect_font_single_block(current_image, block, selected_model)
                    if result:
                        font_results.append(result)
                except Exception as e:
                    print(f"Errore nell'analisi del blocco {i}: {e}")
                    continue

            progress.setValue(len(text_blocks))
            progress.close()

            if not font_results:
                from app.ui.messages import show_warning
                show_warning(self.tr("Nessun font rilevato"),
                           self.tr("Non è stato possibile rilevare font nei blocchi selezionati"))
                return

            from modules.font_detection.font_detection_dialog import FontDetectionDialog

            dialog = FontDetectionDialog(font_results, self)
            dialog.font_list_update_requested.connect(self._on_font_list_update_requested)
            dialog.exec_()

        except Exception as e:
            print(f"Errore nel rilevamento font: {e}")
            from app.ui.messages import show_error
            show_error(self.tr("Errore"),
                      self.tr(f"Si è verificato un errore durante il rilevamento dei font: {str(e)}"))

    def _on_font_list_update_requested(self):
        """Gestisce la richiesta di aggiornamento della lista font dalle impostazioni."""
        try:
            if hasattr(self, 'update_font_dropdown'):
                self.update_font_dropdown()
            else:
                main_window = self.parent()
                if main_window and hasattr(main_window, 'update_font_dropdown'):
                    main_window.update_font_dropdown()
        except Exception as e:
            print(f"Errore durante l'aggiornamento della lista font: {e}")

    def auto_center_text(self):
        """Centra automaticamente tutti i testi nei loro blocchi"""

        print(f"[TIMING] Inizio centratura automatica")
        if hasattr(self, 'start_time_display'):
            self.start_time_display()

        start_time = time.time()

        try:
            if not self.image_viewer.hasPhoto() or self.curr_img_idx < 0:
                if hasattr(self, 'stop_time_display'):
                    self.stop_time_display()
                from app.ui.dayu_widgets.message import MMessage
                MMessage.info(
                    text=self.tr("Carica un'immagine prima di centrare i testi"),
                    parent=self,
                    duration=3,
                    closable=True
                )
                return

            if not self.blk_list:
                if hasattr(self, 'stop_time_display'):
                    self.stop_time_display()
                from app.ui.dayu_widgets.message import MMessage
                MMessage.info(
                    text=self.tr("Non ci sono blocchi di testo da centrare. Esegui prima l'OCR o disegna dei text box."),
                    parent=self,
                    duration=3,
                    closable=True
                )
                return

            valid_blocks = [blk for blk in self.blk_list
                           if blk and hasattr(blk, 'xyxy') and blk.xyxy is not None
                           and hasattr(blk, 'translation') and blk.translation]

            if not valid_blocks:
                if hasattr(self, 'stop_time_display'):
                    self.stop_time_display()
                from app.ui.dayu_widgets.message import MMessage
                MMessage.info(
                    text=self.tr("Non ci sono blocchi di testo con traduzione da centrare."),
                    parent=self,
                    duration=3,
                    closable=True
                )
                return

            centered_count = 0

            for blk in valid_blocks:
                try:
                    x1, y1, x2, y2 = blk.xyxy

                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2

                    text_item = None
                    for item in self.image_viewer.text_items:
                        if hasattr(item, 'blk') and item.blk == blk:
                            text_item = item
                            break

                    if text_item:
                        text_rect = text_item.boundingRect()
                        new_x = center_x - text_rect.width() / 2
                        new_y = center_y - text_rect.height() / 2

                        text_item.setPos(new_x, new_y)
                        centered_count += 1

                        print(f"[DEBUG] Centrato blocco: centro=({center_x}, {center_y}), nuova pos=({new_x}, {new_y})")

                except Exception as e:
                    print(f"Errore nel centrare il blocco: {e}")
                    continue

            end_time = time.time()
            duration = end_time - start_time

            if hasattr(self, 'stop_time_display'):
                self.stop_time_display()

            if centered_count > 0:
                from app.ui.dayu_widgets.message import MMessage
                MMessage.success(
                    text=self.tr(f"Centrati {centered_count} blocchi di testo in {duration:.2f} secondi"),
                    parent=self,
                    duration=3,
                    closable=True
                )
                print(f"[TIMING] Centratura automatica completata: {centered_count} blocchi in {duration:.2f} secondi")
            else:
                from app.ui.dayu_widgets.message import MMessage
                MMessage.warning(
                    text=self.tr("Nessun blocco di testo è stato centrato"),
                    parent=self,
                    duration=3,
                    closable=True
                )

        except Exception as e:
            if hasattr(self, 'stop_time_display'):
                self.stop_time_display()

            end_time = time.time()
            duration = end_time - start_time
            print(f"[TIMING] Centratura automatica fallita dopo {duration:.2f} secondi - Errore: {str(e)}")
            from app.ui.messages import show_error
            show_error(self.tr("Errore"),
                      self.tr(f"Si è verificato un errore durante la centratura automatica: {str(e)}"))

    def set_inpainter_model(self, model_name):
        """Imposta il modello inpainter selezionato."""
        try:
            from modules.utils.model_manager import model_manager

            active_models = model_manager.get_active_models()
            inpainting_names = [
                name for name in active_models
                if (model_manager.get_model_data(name)
                    and model_manager.is_inpainting_capable(model_manager.get_model_data(name)))
            ]
            if model_name in inpainting_names:
                self.current_inpainter_model = model_name
                print(f"[DEBUG] Modello inpainter impostato: {model_name}")

                if hasattr(self, 'settings'):
                    self.settings.setValue('inpainter/selected_model', model_name)
            else:
                print(f"[WARNING] Modello {model_name} non disponibile")

        except Exception as e:
            print(f"Errore nell'impostazione del modello inpainter: {e}")

    def refresh_inpainter_models(self):
        """Aggiorna la lista dei modelli inpainter disponibili utilizzando solo modelli locali già caricati."""
        try:
            from modules.utils.model_manager import model_manager, ModelInfo, ModelStatus

            active_models = model_manager.get_active_models()

            if hasattr(self, 'update_inpainter_models'):
                model_objects = []
                for model_name in active_models:
                    model_data = model_manager.get_model_data(model_name)
                    if model_data and model_manager.is_inpainting_capable(model_data):
                        model_info = ModelInfo(
                            name=model_name,
                            version=model_data.get('api_name', model_name),
                            description=model_data.get('description', f'Modello {model_name}'),
                            status=ModelStatus.AVAILABLE,
                            last_checked=0.0,
                            capabilities=model_data.get('capabilities', [])
                        )
                        model_objects.append(model_info)

                self.update_inpainter_models(model_objects)

            print(f"[DEBUG] Aggiornati {len(active_models)} modelli inpainter utilizzando solo modelli locali")

        except Exception as e:
            print(f"Errore nell'aggiornamento dei modelli inpainter: {e}")

    def initialize_inpainter_models(self):
        """Inizializza i modelli inpainter all'avvio utilizzando solo modelli locali già caricati."""
        try:
            from modules.utils.model_manager import model_manager, ModelInfo, ModelStatus

            active_models = model_manager.get_active_models()

            inpainting_models = []
            for model_name in active_models:
                model_data = model_manager.get_model_data(model_name)
                if model_data and model_manager.is_inpainting_capable(model_data):
                    model_info = ModelInfo(
                        name=model_name,
                        version=model_data.get('api_name', model_name),
                        description=model_data.get('description', f'Modello {model_name}'),
                        status=ModelStatus.AVAILABLE,
                        last_checked=0.0,
                        capabilities=model_data.get('capabilities', [])
                    )
                    inpainting_models.append(model_info)

            if hasattr(self, 'update_inpainter_models'):
                self.update_inpainter_models(inpainting_models)

            if hasattr(self, 'settings'):
                saved_model = self.settings.value('inpainter/selected_model', '')

                # Confronto per NOME: inpainting_models è una lista di oggetti
                # ModelInfo, quindi 'saved_model in inpainting_models' (stringa
                # dentro lista di oggetti) era sempre False e si entrava
                # SEMPRE nell'elif che azzerava la scelta dell'utente.
                available_names = {
                    getattr(m, "name", None) for m in inpainting_models
                }
                available_names.discard(None)

                if saved_model and saved_model in available_names:
                    self.current_inpainter_model = saved_model
                    print(f"[DEBUG] Modello inpainter ripristinato: {saved_model}")

                    if hasattr(self, 'inpainter_model_dropdown'):
                        index = self.inpainter_model_dropdown.findData(saved_model)
                        if index >= 0:
                            self.inpainter_model_dropdown.setCurrentIndex(index)
                elif saved_model:
                    print(f"[INFO] Modello salvato '{saved_model}' non disponibile, resettando selezione")
                    self.settings.setValue('inpainter/selected_model', '')

            print(f"[DEBUG] Inizializzati {len(inpainting_models)} modelli inpainter locali (senza sincronizzazione automatica)")

        except Exception as e:
            print(f"Errore nell'inizializzazione dei modelli inpainter locali: {e}")


