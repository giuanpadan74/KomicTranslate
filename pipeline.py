import os, json
import cv2, shutil
import numpy as np
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)

# TextBlockDetector imported locally in methods that use it (lazy-load for faster startup)
from modules.utils.textblock import TextBlock, sort_blk_list, adjust_text_line_coordinates
from modules.utils.pipeline_utils import get_inpaint_map, get_config
from modules.utils.paths import get_model_path
from modules.utils.download import ensure_models_downloaded
from modules.rendering.render import get_best_render_area, pyside_word_wrap
from modules.utils.pipeline_utils import generate_mask, get_language_code, is_directory_empty
from modules.utils.translator_utils import get_raw_translation, get_raw_text, format_translations, set_upper_case
from modules.utils.archives import make
from modules.pre_ocr_filter import filter_blocks_by_text
from modules.cjk_filter import filter_cjk_for_non_asian
from modules.logging.auto_logger import (
    log_api_error, log_ocr_error, log_translation_error, log_textblock_error,
    log_encoding_error, log_performance_warning, log_fallback_activation,
    log_batch_operation
)
from modules.utils.exceptions import QuotaExhaustedException, GeminiamoSaturationError
from modules.api_fallback import SimpleFallbackManager, FallbackReason
from modules.browser_sites import is_browser_site, get_site
from app.ui.settings.settings_page import SettingsPage
from app.ui.dayu_widgets import MToast

from app.ui.canvas.rectangle import MoveableRectItem, MoveableEllipseItem
from app.ui.canvas.text_item import OutlineInfo, OutlineType
from app.ui.canvas.save_renderer import ImageSaveRenderer

class ComicTranslatePipeline:
    def __init__(self, main_page):
        self.main_page = main_page
        self.block_detector_cache = None
        self.inpainter_cache = None
        self.cached_inpainter_key = None
        # Inizializzazione OCR rimandata per evitare import pesanti durante i test/unit
        try:
            from modules.ocr.processor import OCRProcessor
            self.ocr = OCRProcessor()
        except Exception:
            self.ocr = None
        self.text_detector = None  # Inizializza text_detector
        self.inpainter = None  # Inizializza inpainter
        
        # Percorsi dei file '*_translated.*' prodotti dal run corrente.
        # _cleanup_stray_translated_files() cammina nelle stesse cartelle delle
        # immagini sorgente, dove il renderer salva anche l'output finale: senza
        # questo set la cleanup cancellava il risultato appena prodotto.
        self._saved_paths = set()
        
        # Inizializza il sistema di fallback semplificato
        self.fallback_manager = self._initialize_fallback_manager()

    def cache_ui_snapshot(self):
        """
        Da chiamare dal THREAD GUI, prima di avviare un batch.
        batch_process gira in un QThreadPool: leggere i widget Qt da li' e'
        comportamento indefinito (QFont/QTextDocument devono essere creati e
        usati solo nel thread GUI) e la lingua impostata poteva cambiare a
        meta' batch. Qui si congela lo stato della UI in valori semplici.
        """
        try:
            self._ui_snapshot = {
                'source_lang': self.main_page.s_combo.currentText(),
                'target_lang': self.main_page.t_combo.currentText(),
                'render_settings': self.main_page.render_settings(),
            }
        except Exception as e:
            logger.warning(f"[BATCH] Snapshot UI non disponibile: {e}")
            self._ui_snapshot = None

    def _ui_snapshot_value(self, key):
        snap = getattr(self, '_ui_snapshot', None)
        if not isinstance(snap, dict):
            return None
        return snap.get(key)

    def _ui_source_lang(self):
        value = self._ui_snapshot_value('source_lang')
        return value if value else self.main_page.s_combo.currentText()

    def _ui_target_lang(self):
        value = self._ui_snapshot_value('target_lang')
        return value if value else self.main_page.t_combo.currentText()

    def _register_saved_path(self, path):
        """Registra un file di output prodotto dal run corrente (non deve essere ripulito)."""
        try:
            if path:
                self._saved_paths.add(os.path.normcase(os.path.abspath(path)))
        except Exception:
            pass

    def _is_protected_saved_path(self, path):
        try:
            return os.path.normcase(os.path.abspath(path)) in self._saved_paths
        except Exception:
            return False
        
    def _cleanup_stray_translated_files(self):
        try:
            exts = ['.jpg', '.jpeg', '.png', '.webp', '.tif', '.bmp']
            base_dirs = set(os.path.dirname(p) for p in getattr(self.main_page, 'image_files', []) or [])
            base_dirs.update(getattr(self, '_last_run_dirs', set()) or set())
            for d in base_dirs:
                for root, _, files in os.walk(d):
                    for f in files:
                        name, ext = os.path.splitext(f)
                        if ext.lower() in exts and name.endswith('_translated'):
                            fp = os.path.join(root, f)
                            # Non toccare l'output prodotto dal run corrente
                            if self._is_protected_saved_path(fp):
                                continue
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
                ts = getattr(self, '_last_batch_timestamp', None)
                if ts:
                    ws_root = os.path.join(d, f"comic_translate_{ts}")
                    if os.path.exists(ws_root):
                        for root, _, files in os.walk(ws_root):
                            for f in files:
                                name, ext = os.path.splitext(f)
                                if ext.lower() in exts and name.endswith('_translated'):
                                    fp = os.path.join(root, f)
                                    if self._is_protected_saved_path(fp):
                                        continue
                                    try:
                                        os.remove(fp)
                                    except Exception:
                                        pass
        except Exception:
            pass

    def _cleanup_temp_folders(self):
        """Elimina tutte le cartelle temporanee comic_translate_* create durante il processo.
        Queste cartelle vengono usate per contenere file intermedi (cleaned_images,
        translated_images, archivi estratti) e devono essere eliminate a fine procedura.
        """
        try:
            ts = getattr(self, '_last_batch_timestamp', None)
            base_dirs = set(os.path.dirname(p) for p in getattr(self.main_page, 'image_files', []) or [])
            base_dirs.update(getattr(self, '_last_run_dirs', set()) or set())

            for d in base_dirs:
                # Elimina la cartella corrente con questo timestamp
                if ts:
                    ws_root = os.path.join(d, f"comic_translate_{ts}")
                    if os.path.exists(ws_root):
                        try:
                            shutil.rmtree(ws_root)
                            print(f"[CLEANUP] Rimossa cartella temporanea: {ws_root}")
                        except Exception as e:
                            print(f"[CLEANUP] Errore rimozione {ws_root}: {e}")

                # Backup: elimina tutte le cartelle comic_translate_* che potrebbero essere rimaste
                try:
                    if os.path.isdir(d):
                        for entry in os.listdir(d):
                            entry_path = os.path.join(d, entry)
                            if os.path.isdir(entry_path) and entry.startswith('comic_translate_'):
                                try:
                                    shutil.rmtree(entry_path)
                                    print(f"[CLEANUP] Rimossa cartella temporanea: {entry_path}")
                                except Exception as e:
                                    print(f"[CLEANUP] Errore rimozione {entry_path}: {e}")
                except Exception as e:
                    print(f"[CLEANUP] Errore listing {d}: {e}")
        except Exception as e:
            print(f"[CLEANUP] Errore generale pulizia cartelle: {e}")

    def _initialize_fallback_manager(self):
        """Inizializza il SimpleFallbackManager con DocTR come fallback.

        NOTE: fallback_engine era passato come None, quindi la funzione
        DocTR non veniva mai eseguita e ogni fallback falliva con
        'Nessuna API key disponibile'. Il fallback era di fatto spento.
        """
        def doctr_fallback_function():
            """Attiva DocTR OCR come engine di fallback.

            image e blk_list sono presi dallo stato corrente, cosi' la
            firma e' compatibile con execute_with_fallback(func).
            """
            try:
                from modules.ocr.doctr_ocr import DocTROCREngine
                doctr_engine = DocTROCREngine()
                device = 'cuda' if self.main_page.settings_page.is_gpu_enabled() else 'cpu'
                doctr_engine.initialize(device=device)
                image = self.main_page.image_viewer.get_cv2_image()
                blk_list = self.main_page.blk_list
                return doctr_engine.process_image(image, blk_list)
            except Exception as e:
                print(f"[FALLBACK ERROR] DocTR fallito: {str(e)}")
                raise e

        return SimpleFallbackManager(fallback_engine=doctr_fallback_function)

    def load_box_coords(self, blk_list: List[TextBlock]):
        self.main_page.image_viewer.clear_rectangles(page_switch=True)
        use_rectangle = self.main_page.settings_page.is_rectangle_enabled()
        
        if self.main_page.image_viewer.hasPhoto() and blk_list:
            for blk in blk_list:
                x1, y1, x2, y2 = blk.xyxy
                rect = QtCore.QRectF(0, 0, x2 - x1, y2 - y1)
                
                # Usa la preferenza utente se non c'è una forma specifica salvata
                shape_type = getattr(blk, 'shape_type', None)
                if shape_type is None:
                    shape_type = 'rectangle' if use_rectangle else 'ellipse'
                
                if shape_type == 'rectangle':
                    rect_item = MoveableRectItem(rect, self.main_page.image_viewer.photo, text_block=blk)
                else:
                    rect_item = MoveableEllipseItem(rect, self.main_page.image_viewer.photo, text_block=blk)
                if blk.tr_origin_point:
                    rect_item.setTransformOriginPoint(QtCore.QPointF(*blk.tr_origin_point))
                rect_item.setPos(x1,y1)
                rect_item.setRotation(blk.angle)
                self.main_page.connect_rect_item_signals(rect_item)
                # CORREZIONE: Aggiungi il rectangle alla scena grafica - RIMOSSO perché già aggiunto tramite parent
                # self.main_page.image_viewer._scene.addItem(rect_item)
                self.main_page.image_viewer.rectangles.append(rect_item)

            rect = self.main_page.find_corresponding_rect(self.main_page.blk_list[0], 0.5)
            self.main_page.image_viewer.select_rectangle(rect)
            self.main_page.set_tool('pan')
            # Rispetta il toggle 'Caselle di testo'
            if not getattr(self.main_page.image_viewer, 'rect_boxes_visible', True):
                self.main_page.image_viewer.set_rect_boxes_visible(False)
            # Get font size for markers
            font_size = int(self.main_page.font_size_dropdown.currentText())
            self.main_page.image_viewer.update_all_markers(font_size=font_size)

    def detect_blocks(self, load_rects=True):
        if self.main_page.image_viewer.hasPhoto():
            try:
                if self.block_detector_cache is None:
                    from modules.detection import TextBlockDetector
                    # Assicura che i modelli siano presenti
                    ensure_models_downloaded(['comic-speech-bubble-detector', 'comic-text-segmenter', 'manga-text-detector'])
                    
                    device = 0 if self.main_page.settings_page.is_gpu_enabled() else 'cpu'
                    self.block_detector_cache = TextBlockDetector(
                        get_model_path('models/detection/comic-speech-bubble-detector.pt'), 
                        get_model_path('models/detection/comic-text-segmenter.pt'),
                        get_model_path('models/detection/manga-text-detector.pt'),
                        device
                    )
                image = self.main_page.image_viewer.get_cv2_image()
                blk_list = self.block_detector_cache.detect(image)
                blk_list = self._ocr_and_filter_blocks(blk_list, image)
                try:
                    from modules.utils.text_color_enrichment import enrich_blocks_with_text_color
                    blk_list = enrich_blocks_with_text_color(image, blk_list)
                except Exception:
                    pass
                
                # Log se non vengono rilevati blocchi
                if not blk_list:
                    log_textblock_error(
                        'current_image',
                        'block_detection',
                        Exception("Nessun blocco di testo rilevato nell'immagine corrente")
                    )

                return blk_list, load_rects
            except Exception as e:
                log_textblock_error(
                    'current_image',
                    'block_detection',
                    e
                )
                print(f"Errore rilevamento blocchi: {str(e)}")
                return [], load_rects

    def _ocr_and_filter_blocks(self, blk_list, image, source_lang=None):
        """Esegue OCR sui blocchi e filtra quelli vuoti o con solo numeri di pagina."""
        if not blk_list or image is None:
            return blk_list
        settings_page = getattr(self.main_page, "settings_page", None)
        if settings_page is None or not settings_page.is_pre_ocr_filter_enabled():
            return blk_list
        try:
            if self.ocr is None:
                from modules.ocr.processor import OCRProcessor
                self.ocr = OCRProcessor()
            if source_lang is None:
                source_lang = self.main_page.s_combo.currentText()
            self.ocr.initialize(self.main_page, source_lang, use_combined_mode=False)
            before_count = len(blk_list)
            self.ocr.process(image, blk_list)
            blk_list = filter_blocks_by_text(blk_list)
            source_lang_english = self.main_page.lang_mapping.get(source_lang, source_lang)
            blk_list = filter_cjk_for_non_asian(blk_list, source_lang_english)
            removed = before_count - len(blk_list)
            if removed > 0:
                print(f"[PRE_OCR] {removed} blocchi rimossi dopo OCR + filtro "
                      f"(da {before_count} a {len(blk_list)})")
            return blk_list
        except Exception as e:
            print(f"[PRE_OCR] Errore durante OCR pre-filtro: {e}")
            return blk_list

    def _are_blocks_valid(self, image_path):
        """Verifica se i blocchi esistenti per un'immagine sono validi e utilizzabili"""
        if image_path not in self.main_page.image_states:
            return False
        
        image_state = self.main_page.image_states[image_path]
        
        # Priorità a blk_list. Fallback a text_blocks solo se blk_list non è presente nello stato.
        if 'blk_list' in image_state:
            blocks = image_state['blk_list']
        else:
            blocks = image_state.get('text_blocks', [])
        
        if not blocks:
            return False
        
        # Verifica che almeno un blocco abbia proprietà valide
        valid_count = 0
        for block in blocks:
            if (hasattr(block, 'xyxy') and block.xyxy is not None and len(block.xyxy) > 0 and 
                len(block.xyxy) >= 4 and all(coord >= 0 for coord in block.xyxy)):
                valid_count += 1
        
        # Considera valido se almeno il 50% dei blocchi sono validi
        return valid_count > 0 and (valid_count / len(blocks)) >= 0.5

    def should_skip_detection(self, image_path: str) -> bool:
        """Verifica se saltare il rilevamento usando lo stato centrale"""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        return sm.should_skip_detection(image_path)

    def should_skip_ocr(self, image_path: str) -> bool:
        """Verifica se saltare OCR usando stato centrale"""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        return sm.should_skip_ocr(image_path)

    def should_skip_translation(self, image_path: str) -> bool:
        """Verifica se saltare la traduzione usando stato centrale"""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        return sm.should_skip_translation(image_path)

    def can_skip_to_rendering(self, image_path: str) -> bool:
        """Verifica se saltare direttamente al rendering"""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        return sm.can_skip_to_rendering(image_path)

    def get_operation_status(self, image_path: str) -> Dict[str, bool]:
        """Ottieni stato delle operazioni per debug"""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        return sm.get_operation_status(image_path)

    def mark_detection_completed(self, image_path: str, blocks):
        """Marca il rilevamento come completato."""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        sm.mark_detection_completed(image_path, blocks)

    def mark_ocr_done(self, image_path: str):
        """Marca OCR come completato."""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        sm.mark_ocr_done(image_path)

    def mark_translation_completed(self, image_path: str):
        """Marca la traduzione come completata."""
        from modules.pipeline.state_machine import get_state_manager
        sm = get_state_manager(self.main_page.image_states)
        sm.mark_translation_completed(image_path)

    def _should_skip_text_detection(self, image_path, skip_detection=False, existing_blk_list=None):
        """Determina se saltare il rilevamento delle caselle di testo"""
        image_name = os.path.basename(image_path)
        
        # 1. Se skip_detection è True e abbiamo existing_blk_list
        if skip_detection and existing_blk_list:
            print(f"[BATCH_SKIP] {image_name}: Skip richiesto con blk_list fornita ({len(existing_blk_list)} blocchi)")
            return True
        
        # 2. Se esistono blocchi validi salvati per questa immagine
        if self._are_blocks_valid(image_path):
            existing_blocks = self._get_existing_blocks(image_path)
            if existing_blocks and len(existing_blocks) > 0:
                # Verifica che almeno un blocco abbia coordinate valide
                valid_blocks = [b for b in existing_blocks 
                              if hasattr(b, 'xyxy') and b.xyxy is not None and len(b.xyxy) > 0 and len(b.xyxy) >= 4]
                if len(valid_blocks) > 0:
                    print(f"[BATCH_SKIP] {image_name}: Skip - trovati {len(valid_blocks)} blocchi validi esistenti")
                    return True
                else:
                    print(f"[BATCH_SKIP] {image_name}: Blocchi esistenti non validi - procedo con rilevamento")
        else:
            print(f"[BATCH_SKIP] {image_name}: Nessun blocco valido esistente - procedo con rilevamento")
        
        return False

    def _get_existing_blocks(self, image_path, fallback_list=None, apply_filter=True):
        """Recupera i blocchi esistenti per un'immagine"""
        image_name = os.path.basename(image_path)
        if fallback_list:
            print(f"[BATCH_BLOCKS] {image_name}: Utilizzando fallback_list fornita ({len(fallback_list)} blocchi)")
            if apply_filter:
                return self._filter_visible_blocks_for_image(image_path, fallback_list)
            return fallback_list
        if image_path in self.main_page.image_states:
            image_state = self.main_page.image_states[image_path]
            # Priorità a blk_list. Fallback a text_blocks solo se blk_list non è presente.
            if 'blk_list' in image_state:
                blocks = image_state['blk_list']
                print(f"[BATCH_BLOCKS] {image_name}: Recuperati {len(blocks)} blocchi da blk_list")
            else:
                blocks = image_state.get('text_blocks', [])
                if blocks:
                    print(f"[BATCH_BLOCKS] {image_name}: Recuperati {len(blocks)} blocchi da text_blocks (fallback)")
            if apply_filter:
                return self._filter_visible_blocks_for_image(image_path, blocks)
            return blocks
        print(f"[BATCH_BLOCKS] {image_name}: Nessuno stato immagine trovato")
        return []

    def _is_image_current(self, image_path):
        if self.main_page.curr_img_idx < 0 or not self.main_page.image_files:
            return False
        return self.main_page.image_files[self.main_page.curr_img_idx] == image_path

    def _filter_visible_blocks_for_image(self, image_path, blocks):
        if not blocks:
            return []
            
        # Salta il filtro se non siamo nel thread principale (es. batch process in background)
        # L'accesso a self.main_page.image_viewer.rectangles non è thread-safe
        if QtCore.QThread.currentThread() != QtCore.QCoreApplication.instance().thread():
            # print(f"[VISIBLE_FILTER] {os.path.basename(image_path)}: In background thread, salto filtro visibilità ({len(blocks)} blocchi)")
            return blocks

        if not self._is_image_current(image_path):
            print(f"[VISIBLE_FILTER] {os.path.basename(image_path)}: immagine non corrente, nessun filtro applicato ({len(blocks)} blocchi)")
            return blocks
        viewer = self.main_page.image_viewer
        rects = getattr(viewer, 'rectangles', [])
        rects = [r for r in rects if (r is not None and r.isVisible() and r.scene() is not None and r.scene() == viewer._scene)]
        filtered = []
        tol = 25
        for blk in blocks:
            if not hasattr(blk, 'xyxy') or blk.xyxy is None or len(blk.xyxy) < 4:
                continue
            bx, by = int(blk.xyxy[0]), int(blk.xyxy[1])
            bang = int(getattr(blk, 'angle', 0))
            found = False
            for rect in rects:
                rx, ry = int(rect.pos().x()), int(rect.pos().y())
                rang = int(rect.rotation())
                if abs(rx - bx) <= tol and abs(ry - by) <= tol and abs(rang - bang) <= 5:
                    found = True
                    break
            if found:
                filtered.append(blk)
        print(f"[VISIBLE_FILTER] {os.path.basename(image_path)}: {len(filtered)}/{len(blocks)} blocchi visibili")
        return filtered

    def _perform_text_detection(self, image):
        """Esegue il rilevamento delle caselle di testo"""
        from modules.detection import TextBlockDetector
        
        print(f"[BATCH_DETECTION] Inizializzazione rilevamento caselle di testo")
        
        if self.block_detector_cache is None:
            # Assicura che i modelli siano presenti
            ensure_models_downloaded(['comic-speech-bubble-detector', 'comic-text-segmenter', 'manga-text-detector'])
            
            device = 0 if self.main_page.settings_page.is_gpu_enabled() else 'cpu'
            device_type = 'GPU' if device == 0 else 'CPU'
            print(f"[BATCH_DETECTION] Inizializzazione detector su {device_type}")
            self.block_detector_cache = TextBlockDetector(
                get_model_path('models/detection/comic-speech-bubble-detector.pt'),
                get_model_path('models/detection/comic-text-segmenter.pt'),
                get_model_path('models/detection/manga-text-detector.pt'),
                device
            )
        
        print(f"[BATCH_DETECTION] Esecuzione rilevamento...")
        blk_list = self.block_detector_cache.detect(image)
        blk_list = self._ocr_and_filter_blocks(blk_list, image)
        try:
            from modules.utils.text_color_enrichment import enrich_blocks_with_text_color
            blk_list = enrich_blocks_with_text_color(image, blk_list)
        except Exception:
            pass
        
        if blk_list:
            print(f"[BATCH_DETECTION] Rilevamento completato - {len(blk_list)} blocchi trovati")
        else:
            print(f"[BATCH_DETECTION] Nessun blocco rilevato")
        
        return blk_list
    
    def _mark_detection_completed(self, image_path, blocks):
        """Marca il rilevamento come completato per un'immagine specifica"""
        if image_path not in self.main_page.image_states:
            return
            
        self.main_page.image_states[image_path].update({
            'blk_list': blocks,
            'text_blocks': blocks,
            'detection_completed': True,
            'detection_timestamp': datetime.now().isoformat(),
            'detection_method': 'detect_all_text_boxes'
        })
        
        print(f"[DETECTION_MARKER] Rilevamento marcato come completato per {os.path.basename(image_path)} con {len(blocks)} blocchi")
    
    def detect_all_text_boxes(self):
        """Rileva le caselle di testo su tutte le immagini caricate"""
        if not self.main_page.image_files:
            print("[BATCH_DETECT] Nessuna immagine caricata")
            return {}
        
        # Inizializza il rilevatore se necessario
        if self.block_detector_cache is None:
            from modules.detection import TextBlockDetector
            
            # Assicura che i modelli siano presenti
            ensure_models_downloaded(['comic-speech-bubble-detector', 'comic-text-segmenter', 'manga-text-detector'])
            
            device = 0 if self.main_page.settings_page.is_gpu_enabled() else 'cpu'
            self.block_detector_cache = TextBlockDetector(
                get_model_path('models/detection/comic-speech-bubble-detector.pt'),
                get_model_path('models/detection/comic-text-segmenter.pt'),
                get_model_path('models/detection/manga-text-detector.pt'),
                device
            )
        
        results = {}
        total_images = len(self.main_page.image_files)
        
        print(f"[BATCH_DETECT] Inizio rilevamento su {total_images} immagini")
        
        for index, image_path in enumerate(self.main_page.image_files):
            # Aggiorna progresso
            self.main_page.progress_update.emit(index, total_images, 1, 3, False)
            
            try:
                # Assicura che lo stato dell'immagine sia inizializzato
                # Inizializza image_states se non esiste
                if image_path not in self.main_page.image_states:
                    self.main_page.image_states[image_path] = {
                        'viewer_state': {},
                        'source_lang': self.main_page.s_combo.currentText(),
                        'target_lang': self.main_page.t_combo.currentText()
                    }
                
                # Verifica se esistono già blocchi validi
                if self._are_blocks_valid(image_path):
                    blk_list = self._get_existing_blocks(image_path, apply_filter=False)
                    print(f"[BATCH_DETECT] Riutilizzo {len(blk_list)} blocchi per {os.path.basename(image_path)}")
                else:
                    # Carica e processa l'immagine
                    image = cv2.imread(image_path)
                    if image is None:
                        print(f"[BATCH_DETECT] Errore caricamento: {image_path}")
                        continue
                    
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    
                    # Rileva i blocchi di testo
                    blk_list = self.block_detector_cache.detect(image)
                    
                    if blk_list:
                        # Pre-OCR: esegui OCR e filtra blocchi vuoti/numeri pagina
                        source_lang = self.main_page.image_states[image_path]['source_lang']
                        blk_list = self._ocr_and_filter_blocks(blk_list, image, source_lang)
                        try:
                            from modules.utils.text_color_enrichment import enrich_blocks_with_text_color
                            blk_list = enrich_blocks_with_text_color(image, blk_list, image_is_bgr=False)
                        except Exception:
                            pass
                    
                    if blk_list:
                        # Ordina i blocchi secondo la lingua
                        source_lang = self.main_page.image_states[image_path]['source_lang']
                        source_lang_english = self.main_page.lang_mapping.get(source_lang, source_lang)
                        rtl = True if source_lang_english == 'Japanese' else False
                        blk_list = sort_blk_list(blk_list, rtl)
                        
                        # Marca il rilevamento come completato
                        self._mark_detection_completed(image_path, blk_list)
                        
                        print(f"[BATCH_DETECT] Rilevati {len(blk_list)} blocchi per {os.path.basename(image_path)}")
                    else:
                        print(f"[BATCH_DETECT] Nessun blocco rilevato per {os.path.basename(image_path)}")
                
                results[image_path] = blk_list
                
            except Exception as e:
                print(f"[BATCH_DETECT] Errore processando {image_path}: {str(e)}")
                results[image_path] = []
        
        # Aggiorna progresso finale
        self.main_page.progress_update.emit(total_images, total_images, 3, 3, True)
        
        print(f"[BATCH_DETECT] Completato rilevamento su {len(results)} immagini")
        return results

    # ocr_batch_process removed as per user request

    def on_blk_detect_complete(self, result): 
        start_time = time.perf_counter()
        blk_list, load_rects = result
        source_lang = self.main_page.s_combo.currentText()
        source_lang_english = self.main_page.lang_mapping.get(source_lang, source_lang)
        rtl = True if source_lang_english == 'Japanese' else False
        blk_list = sort_blk_list(blk_list, rtl)
        self.main_page.blk_list = blk_list
        if load_rects:
            self.load_box_coords(blk_list)
        
        self.main_page._schedule_save_current_image_state(100)
        
        elapsed = (time.perf_counter() - start_time) * 1000
        print(f"[BLOCK_DETECT] on_blk_detect_complete completato in {elapsed:.2f}ms")
        logger.info(f"[SAVE_PERF] on_blk_detect_complete completato in {elapsed:.2f}ms")
        
        # Aggiungi al log
        if hasattr(self.main_page, 'add_log_message'):
            self.main_page.add_log_message(f"Rilevamento completato: {len(blk_list)} caselle di testo in {elapsed:.0f}ms")


    def manual_inpaint(self):
        image_viewer = self.main_page.image_viewer
        settings_page = self.main_page.settings_page
        mask = image_viewer.get_mask_for_inpainting()
        image = image_viewer.get_cv2_image()

        # Nessuna casella selezionata (o nessun tratto): la maschera e' vuota e
        # non ha senso far girare l'inpainter su tutta l'immagine. Prima questa
        # situazione era impossibile perche' la maschera includeva ogni
        # casella; ora che il filtro e' corretto va gestita esplicitamente.
        if mask is None or not np.any(mask):
            logger.warning("[INPAINT] Nessuna caselle selezionata: inpainting saltato")
            return image

        if self.inpainter_cache is None or self.cached_inpainter_key != settings_page.get_tool_selection('inpainter'):
            device = 'cuda' if settings_page.is_gpu_enabled() else 'cpu'
            inpainter_key = settings_page.get_tool_selection('inpainter')
            
            # Use InpainterFactory for all models (both static and dynamic)
            try:
                from modules.inpainting.factory import InpainterFactory
                self.inpainter_cache = InpainterFactory.get_inpainter(inpainter_key, device)
            except (ImportError, Exception) as e:
                print(f"Errore caricamento inpainter {inpainter_key}: {e}")
                print("Fallback a LaMa...")
                # Fallback to LaMa if factory fails
                from modules.inpainting.lama import LaMa
                self.inpainter_cache = LaMa(device)
                inpainter_key = 'lama'
            
            self.cached_inpainter_key = inpainter_key
        
        # Pass blk_list and original image size to the config
        config = get_config(
            settings_page, 
            blk_list=self.main_page.blk_list, 
            original_size=image.shape[:2]
        )
        
        # Timer per misurare il tempo di esecuzione dell'inpainting
        start_time = time.time()
        inpaint_input_img = self.inpainter_cache(image, mask, config)
        end_time = time.time()
        duration = end_time - start_time
        
        # Log del tempo di esecuzione
        device = 'GPU' if settings_page.is_gpu_enabled() else 'CPU'
        print(f"[INPAINT_TIMER] Modello: {self.cached_inpainter_key} | Dispositivo: {device} | Tempo: {duration:.2f}s")
        
        inpaint_input_img = cv2.convertScaleAbs(inpaint_input_img) 

        return inpaint_input_img
    
    def inpaint_complete(self, result):
        inpainted, original_image = result
        self.main_page.set_cv2_image(inpainted)
        get_best_render_area(self.main_page.blk_list, original_image, inpainted)
    
    def inpaint(self):
        image = self.main_page.image_viewer.get_cv2_image()
        inpainted = self.manual_inpaint()
        return inpainted, image
    
    def _check_batch_cancellation(self) -> bool:
        """
        Verifica se è stata richiesta la cancellazione del batch.
        
        Returns:
            True se la cancellazione è stata richiesta, False altrimenti
        """
        try:
            from app.controllers.batch_controller.cancellation_manager import get_cancellation_manager
            
            if hasattr(self.main_page, '_cancellation_manager'):
                cancellation_manager = self.main_page._cancellation_manager
            else:
                cancellation_manager = get_cancellation_manager()
            
            if cancellation_manager.check():
                logger.info(f"[BATCH_CANCEL] Cancellazione rilevata durante batch_process")
                return True

            return False
            
        except Exception as e:
            logger.error(f"[BATCH_CANCEL] Errore controllo cancellazione: {e}")
            return False
    
    def _handle_batch_cancelled(self, total_images: int, current_index: int):
        """
        Gestisce l'interruzione del batch per cancellazione.
        
        Args:
            total_images: Numero totale di immagini nel batch
            current_index: Indice corrente dell'immagine in elaborazione
        """
        logger.info(
            f"[BATCH_CANCEL] Batch interrotto: "
            f"immagini processate {current_index}/{total_images}"
        )

        # Nota: niente snapshot dello stato parziale. Il PartialStateManager
        # scriveva file che nessuno rileggeva (nessuna UI di ripresa) e il
        # log dichiarava un "checkpoint salvato" che non avveniva mai.
        if hasattr(self.main_page, '_cancellation_manager') and self.main_page._cancellation_manager:
            self.main_page._cancellation_manager.update_progress(
                current_index, total_images
            )
        
        self._cleanup_stray_translated_files()


    

    

    

    
    def get_selected_block(self):
        rect = self.main_page.image_viewer.selected_rect
        srect = rect.mapRectToScene(rect.rect())
        srect_coords = srect.getCoords()
        blk = self.main_page.find_corresponding_text_block(srect_coords)
        return blk

    def OCR_image(self, single_block=False, use_combined_mode=False):
        """Esegue OCR sull'immagine corrente
        
        Args:
            single_block: Se True, elabora solo il blocco selezionato
            use_combined_mode: Se True, esegue OCR + rilevamento colore font; se False, solo OCR
        """
        source_lang = self.main_page.s_combo.currentText()
        start_time = time.perf_counter()
        if self.main_page.image_viewer.hasPhoto():
            image = self.main_page.image_viewer.get_cv2_image()
            
            try:
                if self.ocr is None:
                    from modules.ocr.processor import OCRProcessor
                    self.ocr = OCRProcessor()
                self.ocr.initialize(self.main_page, source_lang, use_combined_mode=use_combined_mode)
                
                if single_block:
                    blk = self.get_selected_block()
                    if blk:
                        self.ocr.process(image, [blk])
                        mode_text = "OCR+Colore" if use_combined_mode else "OCR"
                        print(f"{mode_text} completato su blocco selezionato")
                        elapsed = (time.perf_counter() - start_time) * 1000
                        if hasattr(self.main_page, 'add_log_message'):
                            self.main_page.add_log_message(f"{mode_text} completato su 1 casella in {elapsed:.0f}ms")
                    else:
                        log_ocr_error("OCR", {"path": "current_image"}, Exception("Nessun blocco selezionato"), "no_block_selected")
                else:
                    if self.main_page.blk_list:
                        self.ocr.process(image, self.main_page.blk_list)
                        mode_text = "OCR+Colore" if use_combined_mode else "OCR"
                        print(f"{mode_text} completato su {len(self.main_page.blk_list)} blocchi")
                        elapsed = (time.perf_counter() - start_time) * 1000
                        if hasattr(self.main_page, 'add_log_message'):
                            self.main_page.add_log_message(f"{mode_text} completato su {len(self.main_page.blk_list)} caselle in {elapsed:.0f}ms")
                    else:
                        log_ocr_error("OCR", {"path": "current_image"}, Exception("Nessun blocco disponibile"), "no_blocks_available")
            except QuotaExhaustedException as e:
                # Quota API superata - usa SimpleFallbackManager
                print(f"[QUOTA SUPERATA] Attivazione fallback DocTR: {str(e)}")
                
                def ocr_function():
                    if single_block:
                        blk = self.get_selected_block()
                        if blk:
                            self.ocr.process(image, [blk])
                            return [blk]
                    else:
                        if self.main_page.blk_list:
                            self.ocr.process(image, self.main_page.blk_list)
                            return self.main_page.blk_list
                    return []
                
                result = self.fallback_manager.execute_with_fallback(
                    ocr_function,
                    FallbackReason.QUOTA_EXCEEDED
                )
                
                if result.success:
                    if single_block:
                        print(f"[FALLBACK SUCCESS] DocTR completato su blocco selezionato")
                    else:
                        if self.main_page.blk_list:
                            self.main_page.blk_list = result.result
                            print(f"[FALLBACK SUCCESS] DocTR completato su {len(self.main_page.blk_list)} blocchi")
                else:
                    log_ocr_error("DocTR_Fallback", {"path": "current_image"}, Exception(result.error), "fallback_failed")
                    print(f"Errore fallback DocTR: {result.error}")
            except Exception as e:
                log_ocr_error("OCR", {"path": "current_image"}, e, "ocr_processing_failed")
                print(f"Errore OCR: {str(e)}")

    def translate_image(self, single_block=False):
        """Esegue traduzione sull'immagine corrente"""
        source_lang = self.main_page.s_combo.currentText()
        target_lang = self.main_page.t_combo.currentText()
        start_time = time.perf_counter()
        if self.main_page.image_viewer.hasPhoto():
            settings_page = self.main_page.settings_page
            image = self.main_page.image_viewer.get_cv2_image()
            translator_model = settings_page.get_tool_selection('translator')
            if hasattr(settings_page, 'get_translate_prompt_for_model'):
                extra_context = settings_page.get_translate_prompt_for_model(translator_model)
            else:
                extra_context = settings_page.get_llm_settings()['extra_context']
            upper_case = settings_page.ui.uppercase_checkbox.isChecked()

            try:
                from modules.translator.processor import Translator
                translator = Translator(self.main_page, source_lang, target_lang)
                if single_block:
                    blk = self.get_selected_block()
                    if blk:
                        translator.translate([blk], image, extra_context)
                        set_upper_case([blk], upper_case)
                        print(f"Traduzione completata su blocco selezionato")
                        elapsed = (time.perf_counter() - start_time) * 1000
                        if hasattr(self.main_page, 'add_log_message'):
                            self.main_page.add_log_message(f"Traduzione completata su 1 casella in {elapsed:.0f}ms")
                    else:
                        log_translation_error(
                            error_type="no_block_selected",
                            image_path="current_image",
                            details="Nessun blocco selezionato per traduzione"
                        )
                else:
                    if self.main_page.blk_list:
                        translator.translate(self.main_page.blk_list, image, extra_context)
                        set_upper_case(self.main_page.blk_list, upper_case)
                        print(f"Traduzione completata su {len(self.main_page.blk_list)} blocchi")
                        elapsed = (time.perf_counter() - start_time) * 1000
                        if hasattr(self.main_page, 'add_log_message'):
                            self.main_page.add_log_message(f"Traduzione completata su {len(self.main_page.blk_list)} caselle in {elapsed:.0f}ms")
                    else:
                        log_translation_error(
                            error_type="no_blocks_available",
                            image_path="current_image",
                            details="Nessun blocco di testo disponibile per traduzione"
                        )
            except Exception as e:
                log_translation_error(
                    error_type="translation_processing_failed",
                    image_path="current_image",
                    details=f"Errore durante traduzione: {str(e)}"
                )
                print(f"Errore traduzione: {str(e)}")

    def skip_save(self, directory, timestamp, base_name, extension, archive_bname, image):
        if not base_name or base_name == "_":
            return
        export_settings = self.main_page.settings_page.get_export_settings()
        archive_mode = bool(archive_bname)
        needs_workspace = (
            archive_mode or
            export_settings.get('export_inpainted_image', False) or
            export_settings.get('export_raw_text', False) or
            export_settings.get('export_translated_text', False)
        )
        if needs_workspace:
            path = os.path.join(directory, f"comic_translate_{timestamp}", "translated_images", archive_bname)
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            target = os.path.join(path, f"{base_name}_translated{extension}")
        else:
            # Come nel rendering: niente "<nome>_translated.<ext>" accanto
            # all'originale. Serve solo la workspace per costruire l'archivio.
            target = None

        if target is None:
            logger.info(
                "[BATCH] Pagina saltata: nessun salvataggio automatico "
                "(nessun archivio/export). Usa 'Salva' per esportarla."
            )
            return

        cv2.imwrite(target, image)
        # L'output del run corrente non deve essere rimosso dalla cleanup
        self._register_saved_path(target)

    def log_skipped_image(self, directory, timestamp, image_path):
        export_settings = self.main_page.settings_page.get_export_settings()
        needs_workspace = (
            export_settings.get('export_inpainted_image', False) or
            export_settings.get('export_raw_text', False) or
            export_settings.get('export_translated_text', False)
        )
        log_dir = os.path.join(directory, f"comic_translate_{timestamp}") if needs_workspace else directory
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "skipped_images.txt"), 'a', encoding='UTF-8') as file:
            file.write(image_path + "\n")

    def batch_process(self, existing_blk_list=None, skip_detection=False):
        import time
        batch_start_time = time.time()
        
        timestamp = datetime.now().strftime("%b-%d-%Y_%I-%M-%S%p")
        self._last_batch_timestamp = timestamp
        self._last_run_dirs = set()
        total_images = len(self.main_page.image_files)
        
        # Log inizio operazione batch
        log_batch_operation(
            "batch_process_start",
            total_images,
            0,  # successful (iniziale)
            0,  # failed (iniziale)
            0.0  # duration (iniziale)
        )
        
        for index, image_path in enumerate(self.main_page.image_files):

            # Controllo cancellazione batch
            if self._check_batch_cancellation():
                self._handle_batch_cancelled(total_images, index)
                return False

            # index, step, total_steps, change_name
            self.main_page.progress_update.emit(index, total_images, 0, 10, True)

            settings_page = self.main_page.settings_page

            # Lo stato deve esistere PRIMA di leggere source_lang/target_lang:
            # la creazione era piu' in basso nel loop e causava KeyError abortivo.
            # Le lingue vengono dallo snapshot catturato sul thread GUI: leggere
            # i QComboBox da questo thread (QThreadPool) non e' sicuro e permetteva
            # anche di cambiare lingua a meta' batch.
            if image_path not in self.main_page.image_states:
                self.main_page.image_states[image_path] = {
                    'viewer_state': {},
                    'source_lang': self._ui_source_lang(),
                    'target_lang': self._ui_target_lang()
                }
            _state = self.main_page.image_states[image_path]
            # Il dropdown e' l'unica fonte di verita': lo snapshot (catturato
            # sul thread GUI) ha sempre precedenza sullo stato salvato, che
            # puo' contenere una lingua scelta in precedenza. Senza questa
            # forzatura, cambiare il target dopo il caricamento non aveva
            # effetto sulle pagine il cui stato esisteva gia'.
            source_lang = self._ui_source_lang()
            target_lang = self._ui_target_lang()
            _state['source_lang'] = source_lang
            _state['target_lang'] = target_lang

            target_lang_en = self.main_page.lang_mapping.get(target_lang, None)
            trg_lng_cd = get_language_code(target_lang_en)
            
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            extension = os.path.splitext(image_path)[1]
            directory = os.path.dirname(image_path)
            self._last_run_dirs.add(directory)

            archive_bname = ""
            for archive in self.main_page.file_handler.archive_info:
                images = archive['extracted_images']
                archive_path = archive['archive_path']

                for img_pth in images:
                    if img_pth == image_path:
                        directory = os.path.dirname(archive_path)
                        archive_bname = os.path.splitext(os.path.basename(archive_path))[0]
                        self._last_run_dirs.add(directory)

            image = cv2.imread(image_path)

            # Text Block Detection - controlla se esistono già blocchi rilevati
            self.main_page.progress_update.emit(index, total_images, 1, 10, False)

            # Assicura che lo stato dell'immagine sia inizializzato
            if image_path not in self.main_page.image_states:
                self.main_page.image_states[image_path] = {
                    'viewer_state': {},
                    'source_lang': self.main_page.s_combo.currentText(),
                    'target_lang': self.main_page.t_combo.currentText()
                }
            
            # Controllo ottimizzato per utilizzo di caselle di testo esistenti o rilevamento automatico
            print(f"[BATCH_DEBUG] Pagina {index+1}/{total_images}: {os.path.basename(image_path)}")
            print(f"[BATCH_DEBUG] skip_detection={skip_detection}, existing_blk_list is None={existing_blk_list is None}")
            
            if self._should_skip_text_detection(image_path, skip_detection, existing_blk_list):
                # Durante batch NON filtriamo per visibilità -Elaboriamo tutti i blocchi esistenti
                blk_list = self._get_existing_blocks(image_path, existing_blk_list, apply_filter=False)
                print(f"[BATCH_SKIP_DETECTION] Utilizzando {len(blk_list)} caselle di testo esistenti per {os.path.basename(image_path)}")
            else:
                blk_list = self._perform_text_detection(image)
                blk_list = self._filter_visible_blocks_for_image(image_path, blk_list)
                print(f"[BATCH_DETECTION] Rilevamento completato per {os.path.basename(image_path)} - trovati {len(blk_list) if blk_list else 0} blocchi")
            
            print(f"[BATCH_DEBUG] Dopo filtro blk_list ha {len(blk_list) if blk_list else 0} blocchi")
            try:
                from modules.utils.text_color_enrichment import enrich_blocks_with_text_color
                blk_list = enrich_blocks_with_text_color(image, blk_list, image_is_bgr=True)
            except Exception:
                pass
            
            # Log rilevamento blocchi
            if not blk_list:
                log_textblock_error(
                    image_path,
                    'block_detection',
                    Exception("Nessun blocco di testo rilevato nell'immagine")
                )

            self.main_page.progress_update.emit(index, total_images, 2, 10, False)
            
            print(f"[BATCH_DEBUG] Entra in if blk_list: {bool(blk_list)}")
            
            if blk_list:
                # Verifica se l'OCR è già stato eseguito (pre-OCR durante detection)
                ocr_already_done = (
                    self.main_page.image_states.get(image_path, {}).get('ocr_done', False) or
                    all(
                        getattr(blk, 'text', '').strip() for blk in blk_list
                    )
                )
                
                if ocr_already_done:
                    print(f"[OCR] Testo già disponibile per {len(blk_list)} blocchi (pre-OCR), salto OCR")
                    total_chars = sum(len(blk.text) for blk in blk_list if blk.text)
                    source_lang_english = self.main_page.lang_mapping.get(source_lang, source_lang)
                    rtl = True if source_lang_english == 'Japanese' else False
                    blk_list = sort_blk_list(blk_list, rtl)
                    self.main_page.image_states[image_path]['ocr_done'] = True
                else:
                    if self.ocr is None:
                        from modules.ocr.processor import OCRProcessor
                        self.ocr = OCRProcessor()
                    self.ocr.initialize(self.main_page, source_lang, use_combined_mode=False)
                    try:
                        # OCR batch processing: processa tutti i blocchi insieme per ottimizzare le chiamate API
                        print(f"[OCR] Inizio elaborazione batch di {len(blk_list)} blocchi")
                        
                        # Processa tutti i blocchi insieme con una singola chiamata
                        self.ocr.process(image, blk_list)
                        
                        # Controlla la lunghezza del testo riconosciuto e logga i risultati
                        max_safe_chars = 25000
                        total_chars = 0
                        text_too_long = False
                        
                        for blk in blk_list:
                            if blk.text:
                                total_chars += len(blk.text)
                                if len(blk.text) > max_safe_chars:
                                    error_message = f"OCR: testo troppo lungo per il blocco (>{max_safe_chars} caratteri), pagina saltata."
                                    print(error_message)
                                    # Log errore OCR
                                    log_ocr_error(
                                        error_type="text_too_long",
                                        image_path=image_path,
                                        details=error_message
                                    )
                                    text_too_long = True
                                    break
                        
                        if text_too_long:
                            # Pulisci tutti i blocchi e salta l'immagine
                            for blk in blk_list:
                                blk.text = ""
                            self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                            self.main_page.image_skipped.emit(image_path, "OCR", error_message)
                            self.log_skipped_image(directory, timestamp, image_path)
                            continue
                        
                        print(f"[OCR] Totale caratteri riconosciuti in pagina: {total_chars}")
                        
                        logger.info(f"[BATCH DEBUG] OCR completato per {os.path.basename(image_path)}, "
                                    f"blocchi: {len(blk_list)}, caratteri: {total_chars}, "
                                    f"step_progress: 2/10, prossimo: inpainting")
                        
                        source_lang_english = self.main_page.lang_mapping.get(source_lang, source_lang)
                        rtl = True if source_lang_english == 'Japanese' else False
                        blk_list = sort_blk_list(blk_list, rtl)
                    except GeminiamoSaturationError as e:
                        print(f"[GEMINIAMO SATURATION] {str(e)}")
                        # Handle saturation via Controller (UI thread)
                        choice = self.main_page.handle_gemini_saturation()
                        if choice == 'retry':
                            # Riprova con lo stesso engine, rilasciando le credenziali
                            print(f"[GEMINIAMO SATURATION] Utente ha scelto di riprovare. Riprovo...")
                            
                            # Re-initialize OCR processor to pick up new settings
                            if self.ocr:
                                self.ocr.initialize(self.main_page, source_lang, use_combined_mode=False)
                            
                            try:
                                # Retry OCR process with new engine
                                self.ocr.process(image, blk_list)
                                
                                # Controlla la lunghezza del testo riconosciuto e logga i risultati
                                max_safe_chars = 25000
                                total_chars = 0
                                text_too_long = False
                                
                                for blk in blk_list:
                                    if blk.text:
                                        total_chars += len(blk.text)
                                        if len(blk.text) > max_safe_chars:
                                            error_message = f"OCR: testo troppo lungo per il blocco (>{max_safe_chars} caratteri), pagina saltata."
                                            print(error_message)
                                            log_ocr_error("OCR", {"path": image_path}, Exception(error_message), "text_too_long")
                                            text_too_long = True
                                            break
                                
                                if text_too_long:
                                    for blk in blk_list:
                                        blk.text = ""
                                    self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                                    self.main_page.image_skipped.emit(image_path, "OCR", error_message)
                                    self.log_skipped_image(directory, timestamp, image_path)
                                    continue
                                
                                print(f"[OCR] Totale caratteri riconosciuti in pagina: {total_chars}")
                                
                                logger.info(f"[BATCH DEBUG] OCR retry completato per {os.path.basename(image_path)}, "
                                            f"blocchi: {len(blk_list)}, caratteri: {total_chars}")
                                
                                source_lang_english = self.main_page.lang_mapping.get(source_lang, source_lang)
                                rtl = True if source_lang_english == 'Japanese' else False
                                blk_list = sort_blk_list(blk_list, rtl)
                                
                            except Exception as retry_error:
                                error_message = f"Errore durante il retry OCR: {str(retry_error)}"
                                print(error_message)
                                log_ocr_error("OCR_RETRY", {"path": image_path}, retry_error, "ocr_retry_failed")
                                self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                                self.main_page.image_skipped.emit(image_path, "OCR", error_message)
                                self.log_skipped_image(directory, timestamp, image_path)
                                continue
                        else:
                            # Abort processing
                            print(f"[GEMINIAMO SATURATION] Utente ha scelto di continuare. Interruzione processo.")
                            self.main_page.current_worker = None # Stop worker
                            break
                    except QuotaExhaustedException as e:
                        # Quota API superata - usa SimpleFallbackManager
                        print(f"[QUOTA SUPERATA] Attivazione fallback DocTR per {image_path}: {str(e)}")
                        
                        def ocr_function():
                            # Funzione primaria già fallita, restituisce None
                            return None
                        
                        result = self.fallback_manager.execute_with_fallback(
                            ocr_function,
                            FallbackReason.QUOTA_EXCEEDED
                        )
                        
                        if result.success:
                            blk_list = result.result
                            print(f"[FALLBACK SUCCESS] DocTR completato per {image_path}")
                            
                            source_lang_english = self.main_page.lang_mapping.get(source_lang, source_lang)
                            rtl = True if source_lang_english == 'Japanese' else False
                            blk_list = sort_blk_list(blk_list, rtl)
                        else:
                            error_message = f"Fallback DocTR fallito: {result.error}"
                            print(error_message)
                            log_ocr_error("DocTR_Fallback", {"path": image_path}, Exception(result.error), "fallback_failed")
                            self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                            self.main_page.image_skipped.emit(image_path, "OCR", error_message)
                            self.log_skipped_image(directory, timestamp, image_path)
                            continue
                    except Exception as e:
                        error_message = str(e)
                        print(error_message)
                        # Log errore OCR
                        log_ocr_error("OCR", {"path": image_path}, e, "ocr_processing_failed")
                        self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                        self.main_page.image_skipped.emit(image_path, "OCR", error_message)
                        self.log_skipped_image(directory, timestamp, image_path)
                        continue
            else:
                self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                self.main_page.image_skipped.emit(image_path, "Text Blocks", "")
                self.log_skipped_image(directory, timestamp, image_path)
                continue

            self.main_page.progress_update.emit(index, total_images, 3, 10, False)
            
            logger.info(f"[BATCH DEBUG] Step 3/10 completato - Inizio inpainting per {os.path.basename(image_path)}")
            
            # Clean Image of text
            export_settings = settings_page.get_export_settings()
            
            inpainter_key = settings_page.get_tool_selection('inpainter')
            logger.info(f"[BATCH DEBUG] Inpainter selezionato: '{inpainter_key}' (tipo: {type(inpainter_key)})")
            
            if self.inpainter_cache is None or self.cached_inpainter_key != inpainter_key:
                device = 'cuda' if settings_page.is_gpu_enabled() else 'cpu'
                inpainter_key = settings_page.get_tool_selection('inpainter')
                
                try:
                    from modules.inpainting.factory import InpainterFactory
                    self.inpainter_cache = InpainterFactory.get_inpainter(inpainter_key, device)
                    logger.info(f"[BATCH DEBUG] Inpainter caricato: {type(self.inpainter_cache).__name__}, device: {device}")
                except (ImportError, Exception) as e:
                    print(f"Errore caricamento inpainter {inpainter_key}: {e}")
                    print("Fallback a LaMa...")
                    from modules.inpainting.lama import LaMa
                    self.inpainter_cache = LaMa(device)
                    inpainter_key = 'lama'
                    logger.info(f"[BATCH DEBUG] Fallback a LaMa dopo errore: {e}")
                
                self.cached_inpainter_key = inpainter_key

            config = get_config(
                settings_page,
                blk_list=blk_list,
                original_size=image.shape[:2]
            )
            logger.info(f"[BATCH DEBUG] Generazione mask per {os.path.basename(image_path)}...")
            mask = generate_mask(image, blk_list)
            logger.info(f"[BATCH DEBUG] Mask generata, shape: {mask.shape}")
            
            self.main_page.progress_update.emit(index, total_images, 4, 10, False)
            
            logger.info(f"[BATCH DEBUG] Chiamata inpainter_cache() per {os.path.basename(image_path)}...")
            import time
            inpaint_start = time.time()
            
            inpaint_input_img = self.inpainter_cache(image, mask, config)
            
            inpaint_elapsed = time.time() - inpaint_start
            logger.info(f"[BATCH DEBUG] inpainter_cache() completato in {inpaint_elapsed:.2f}s")
            
            inpaint_input_img = cv2.convertScaleAbs(inpaint_input_img)
            
            logger.info(f"[BATCH DEBUG] Inpainting completato per {os.path.basename(image_path)}, "
                        f"step_progress: 4/10, prossimo: emit image_processed")

            # Saving cleaned image
            self.main_page.image_history[image_path] = [image_path]
            self.main_page.current_history_index[image_path] = 0
            self.main_page.image_processed.emit(index, inpaint_input_img, image_path)

            logger.info(f"[BATCH DEBUG] image_processed emesso per {os.path.basename(image_path)}, "
                        f"step_progress: 5/10, prossimo: traduzione")
            
            inpaint_input_img = cv2.cvtColor(inpaint_input_img, cv2.COLOR_BGR2RGB)

            if export_settings['export_inpainted_image']:
                path = os.path.join(directory, f"comic_translate_{timestamp}", "cleaned_images", archive_bname)
                if not os.path.exists(path):
                    os.makedirs(path, exist_ok=True)
                cv2.imwrite(os.path.join(path, f"{base_name}_cleaned{extension}"), inpaint_input_img)

            self.main_page.progress_update.emit(index, total_images, 5, 10, False)

            # Get Translations/ Export if selected
            translator_model = settings_page.get_tool_selection('translator')
            if hasattr(settings_page, 'get_translate_prompt_for_model'):
                extra_context = settings_page.get_translate_prompt_for_model(translator_model)
            else:
                extra_context = settings_page.get_llm_settings()['extra_context']
            from modules.translator.processor import Translator
            translator = Translator(self.main_page, source_lang, target_lang)
            
            logger.info(f"[BATCH DEBUG] Translator inizializzato per {os.path.basename(image_path)}, "
                        f"source: {source_lang}, target: {target_lang}, "
                        f"step_progress: 5/10, prossimo: translator.translate()")
            
            try:
                # Sincronizza l'ordine dei blocchi spazialmente (Dall'alto in basso, sinistra a destra)
                # Questo garantisce che block_1 nel prompt corrisponda a blk_list[0]
                # MA: salviamo l'ordine originale per ripristinarlo dopo la traduzione TXT
                original_blk_list = list(blk_list)
                
                if blk_list:
                    # Usiamo right_to_left=False per un ordinamento standard top-down, left-right
                    blk_list = sort_blk_list(blk_list, right_to_left=False)

                # I siti browser (Gemini, Dola) non traducono via engine Python:
                # l'automator apre il sito in una webview e lo pilota via JS.
                if is_browser_site(translator.translator_key):
                    site = get_site(translator.translator_key)
                    logger.info(
                        f"[BATCH] Sito browser: {site.label} "
                        f"-> automator su {site.url}"
                    )

                    max_retries_for_incomplete = 2
                    retry_delay = 3
                    translation_result = None
                    retry_count = 0

                    while retry_count <= max_retries_for_incomplete:
                        translation_result = self._translate_with_browser_automator(
                            blk_list, image, source_lang, target_lang, image_path,
                            site_key=translator.translator_key
                        )
                        if translation_result is None:
                            # Translation failed completely
                            break

                        # Apply translations temporarily to check completeness
                        from modules.utils.translator_utils import set_texts_from_json
                        normalized_json = self._normalize_json_keys_to_zero_based(translation_result)

                        # Create a temp copy to check without modifying original
                        temp_blk_list = [blk for blk in original_blk_list]
                        set_texts_from_json(temp_blk_list, normalized_json, img_used=False)

                        translated_count = sum(1 for blk in temp_blk_list if blk.translation and blk.translation.strip())

                        if translated_count >= len(blk_list):
                            # All blocks translated, apply to real blk_list
                            set_texts_from_json(blk_list, normalized_json, img_used=False)
                            logger.info(f"[BATCH] Tutti i {translated_count} blocchi tradotti al tentativo {retry_count + 1}")
                            break
                        else:
                            retry_count += 1
                            if retry_count <= max_retries_for_incomplete:
                                logger.warning(
                                    f"[BATCH] Retry {retry_count}/{max_retries_for_incomplete}: "
                                    f"Solo {translated_count}/{len(blk_list)} blocchi tradotti. "
                                    f"Ritentazione tra {retry_delay}s..."
                                )
                                import time
                                time.sleep(retry_delay)
                            else:
                                logger.error(
                                    f"[BATCH] ERRORE: Solo {translated_count}/{len(blk_list)} blocchi tradotti "
                                    f"dopo {max_retries_for_incomplete} retry. "
                                    f"Blocco mancante: block_{translated_count}. Immagine: {os.path.basename(image_path)}"
                                )
                                # Apply what we have and continue
                                set_texts_from_json(blk_list, normalized_json, img_used=False)

                    if translation_result is None:
                        self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                        self.main_page.image_skipped.emit(image_path, "GeminiAutomator", "Translation returned no result")
                        self.log_skipped_image(directory, timestamp, image_path)
                        continue

                    # Ripristina l'ordine originale dei blocchi dopo la traduzione TXT.
                    # sort_blk_list() restituisce una NUOVA lista contenente gli
                    # STESSI oggetti TextBlock, solo riordinati: e' quindi inutile
                    # (e dannoso) rimappare le traduzioni per indice, perché si
                    # finiva per assegnare ogni testo al blocco sbagliato.
                    blk_list = original_blk_list
                    logger.info("[BATCH] Ripristinato ordine originale dei blocchi dopo traduzione TXT")
                else:
                    translator.translate(blk_list, image, extra_context)

                self.main_page.image_states[image_path]['ocr_done'] = True

                logger.info(f"[BATCH DEBUG] translator.translate() completato per {os.path.basename(image_path)}, "
                            f"step_progress: 5-7/10, prossimo: text rendering")
                            
            except Exception as e:
                error_message = str(e)
                print(error_message)
                # Log errore traduzione
                log_translation_error(
                    error_type="translation_failed",
                    image_path=image_path,
                    details=error_message
                )
                self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                self.main_page.image_skipped.emit(image_path, "Translator", error_message)
                self.log_skipped_image(directory, timestamp, image_path)
                continue

            entire_raw_text = get_raw_text(blk_list)
            entire_translated_text = get_raw_translation(blk_list)

            # Parse JSON strings and check if they're empty objects or invalid
            try:
                raw_text_obj = json.loads(entire_raw_text)
                translated_text_obj = json.loads(entire_translated_text)
                
                if (not raw_text_obj) or (not translated_text_obj):
                    self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                    self.main_page.image_skipped.emit(image_path, "Translator", "")
                    self.log_skipped_image(directory, timestamp, image_path)
                    continue
            except json.JSONDecodeError as e:
                # Handle invalid JSON
                error_message = str(e)
                # Log errore encoding JSON
                log_encoding_error(
                    error_type="json_decode_error",
                    image_path=image_path,
                    details=f"Errore decodifica JSON: {error_message}"
                )
                self.skip_save(directory, timestamp, base_name, extension, archive_bname, image)
                self.main_page.image_skipped.emit(image_path, "Translator", error_message)
                self.log_skipped_image(directory, timestamp, image_path)
                continue

            if export_settings['export_raw_text']:
                path = os.path.join(directory, f"comic_translate_{timestamp}", "raw_texts", archive_bname)
                if not os.path.exists(path):
                    os.makedirs(path, exist_ok=True)
                file = open(os.path.join(path, os.path.splitext(os.path.basename(image_path))[0] + "_raw.txt"), 'w', encoding='UTF-8')
                file.write(entire_raw_text)

            if export_settings['export_translated_text']:
                path = os.path.join(directory, f"comic_translate_{timestamp}", "translated_texts", archive_bname)
                if not os.path.exists(path):
                    os.makedirs(path, exist_ok=True)
                file = open(os.path.join(path, os.path.splitext(os.path.basename(image_path))[0] + "_translated.txt"), 'w', encoding='UTF-8')
                file.write(entire_translated_text)

            self.main_page.progress_update.emit(index, total_images, 7, 10, False)
            
            logger.info(f"[BATCH DEBUG] Step 7/10 completato - Inizio text rendering per {os.path.basename(image_path)}")
            
            # Text Rendering. Si usa lo snapshot catturato sul thread GUI: render_settings()
            # legge 10+ widget e va chiamata dal thread principale.
            render_settings = self._ui_snapshot_value('render_settings')
            if render_settings is None:
                render_settings = self.main_page.render_settings()
            upper_case = render_settings.upper_case
            outline = render_settings.outline
            format_translations(blk_list, trg_lng_cd, upper_case=upper_case)
            get_best_render_area(blk_list, image, inpaint_input_img)

            font = render_settings.font_family
            default_font_color = QColor(render_settings.color)

            max_font_size = render_settings.max_font_size
            min_font_size = render_settings.min_font_size
            line_spacing = float(render_settings.line_spacing) 
            outline_width = float(render_settings.outline_width)
            outline_color = QColor(render_settings.outline_color) 
            bold = render_settings.bold
            italic = render_settings.italic
            underline = render_settings.underline
            alignment_id = render_settings.alignment_id
            alignment = self.main_page.button_to_alignment[alignment_id]
            direction = render_settings.direction
                
            text_items_state = []
            for blk in blk_list:
                x1, y1, width, height = blk.xywh

                translation = blk.translation
                if not translation:
                    continue
                
                blk_color_hex = getattr(blk, "font_color", "") or ""
                font_color = QColor(blk_color_hex) if blk_color_hex.strip() else default_font_color

                translation, font_size, render_w, render_h = pyside_word_wrap(translation, font, width, height,
                                                        line_spacing, outline_width, bold, italic, underline,
                                                        alignment, direction, max_font_size, min_font_size)
                
                # Display text if on current page
                if index == self.main_page.curr_img_idx:
                    self.main_page.blk_rendered.emit(translation, font_size, blk)

                if any(lang in trg_lng_cd.lower() for lang in ['zh', 'ja', 'th']):
                    translation = translation.replace(' ', '')

                # Centra la posizione del testo nel blocco
                center_x = x1 + width / 2
                center_y = y1 + height / 2
                pos_x = center_x - render_w / 2
                pos_y = center_y - render_h / 2

                text_items_state.append({
                'text': translation,
                'font_family': font,
                'font_size': font_size,
                'text_color': font_color,
                'detected_text_color': getattr(blk, "detected_text_color", blk_color_hex) or "",
                'detected_text_color_data': getattr(blk, "detected_text_color_data", None),
                'alignment': alignment,
                'line_spacing': line_spacing,
                'outline_color': outline_color,
                'outline_width': outline_width,
                'bold': bold,
                'italic': italic,
                'underline': underline,
                'position': (pos_x, pos_y),
                'rotation': blk.angle,
                'scale': 1.0,
                'transform_origin': blk.tr_origin_point,
                'width': width,
                'direction': direction,
                'selection_outlines': [OutlineInfo(0, len(translation), 
                                                            outline_color, outline_width, 
                                                            OutlineType.Full_Document)] if outline else []
                })

            self.main_page.image_states[image_path]['viewer_state'].update({
                'text_items_state': text_items_state
                })
            
            self.main_page.progress_update.emit(index, total_images, 9, 10, False)
            
            # Saving blocks with texts to history
            self.main_page.image_states[image_path].update({
                'blk_list': blk_list
            })

            if index == self.main_page.curr_img_idx:
                self.main_page.blk_list = blk_list
                
            archive_mode = bool(archive_bname)
            needs_workspace = (
                archive_mode or
                export_settings.get('export_inpainted_image', False) or
                export_settings.get('export_raw_text', False) or
                export_settings.get('export_translated_text', False)
            )
            if needs_workspace:
                render_save_dir = os.path.join(directory, f"comic_translate_{timestamp}", "translated_images", archive_bname)
                if not os.path.exists(render_save_dir):
                    os.makedirs(render_save_dir, exist_ok=True)
            else:
                # Nessun salvataggio automatico: senza archivio né opzioni di
                # export il file finiva accanto all'originale come
                # '<nome>_translated.<ext>'. Ora l'immagine resta solo nel
                # canvas e va esportata con il comando "Salva".
                render_save_dir = None

            sv_pth = (
                os.path.join(render_save_dir, f"{base_name}_translated{extension}")
                if render_save_dir else None
            )

            im = cv2.cvtColor(inpaint_input_img, cv2.COLOR_RGB2BGR)
            renderer = ImageSaveRenderer(im)
            viewer_state = self.main_page.image_states[image_path]['viewer_state']
            renderer.add_state_to_image(viewer_state)
            
            logger.info(f"[BATCH DEBUG] Rendering completato per {os.path.basename(image_path)}, "
                        f"step_progress: 9/10, prossimo: save immagine")
            
            if sv_pth and base_name and base_name != "_":
                renderer.save_image(sv_pth)
                # Output del batch nella workspace: protetto dalla cleanup
                self._register_saved_path(sv_pth)
            else:
                logger.info(
                    "[BATCH] Salvataggio automatico disattivato: "
                    "l'immagine tradotta resta nel canvas. Usa 'Salva' per esportarla."
                )

            self.main_page.progress_update.emit(index, total_images, 10, 10, False)
            
            logger.info(f"[BATCH DEBUG] Immagine {index+1}/{total_images} completata: {os.path.basename(image_path)}")

            # Delay tra immagini per i siti browser, per evitare rate-limiting.
            # Ogni sito ha il suo: Dola e piu' lento di Gemini.
            site = get_site(translator.translator_key)
            if site is not None and index < total_images - 1:
                inter_image_delay = site.delay_between_pages
                logger.info(
                    f"[{site.label} AUTO] Attesa {inter_image_delay}s prima della "
                    f"prossima immagine per evitare rate-limiting..."
                )
                time.sleep(inter_image_delay)
            
        archive_info_list = self.main_page.file_handler.archive_info
        if archive_info_list:
            save_as_settings = settings_page.get_export_settings()['save_as']
            for archive_index, archive in enumerate(archive_info_list):
                archive_index_input = total_images + archive_index

                self.main_page.progress_update.emit(archive_index_input, total_images, 1, 3, True)
                
                archive_path = archive['archive_path']
                archive_ext = os.path.splitext(archive_path)[1]
                archive_bname = os.path.splitext(os.path.basename(archive_path))[0]
                archive_directory = os.path.dirname(archive_path)
                save_as_ext = f".{save_as_settings[archive_ext.lower()]}"

                save_dir = os.path.join(archive_directory, f"comic_translate_{timestamp}", "translated_images", archive_bname)
                check_from = os.path.join(archive_directory, f"comic_translate_{timestamp}")

                self.main_page.progress_update.emit(archive_index_input, total_images, 2, 3, True)
                
                # Create the new archive
                output_base_name = f"{archive_bname}"
                make(save_as_ext=save_as_ext, input_dir=save_dir, 
                    output_dir=archive_directory, output_base_name=output_base_name)

                self.main_page.progress_update.emit(archive_index_input, total_images, 3, 3, True)
                
                # Clean up temporary 
                if os.path.exists(save_dir):
                    shutil.rmtree(save_dir)
                # The temp dir is removed when closing the app

                if is_directory_empty(check_from):
                    shutil.rmtree(check_from)
        
        # Log completamento operazione batch
        batch_end_time = time.time()
        batch_duration = batch_end_time - batch_start_time
        
        log_batch_operation(
            "batch_process_completed",
            total_images,
            total_images,  # successful (assumendo successo completo)
            0,  # failed
            batch_duration  # duration (da calcolare se necessario)
        )
        
        print(f"===========================================================")
        print(f"[BATCH TIMING] Traduci (Tutto) completato in {batch_duration:.2f} secondi")
        print(f"===========================================================")
        
        # Emetti segnale di completamento finale
        self.main_page.progress_update.emit(total_images, total_images, 10, 10, False)
        
        # SOLUZIONE: Return esplicito per assicurare che GenericWorker riconosca il completamento
        print("[BATCH_PROCESS_FIX] Batch process completato, ritornando esplicitamente")
        self._cleanup_stray_translated_files()
        self._cleanup_after_batch()
        return True

    def _translate_with_browser_automator(self, blk_list, image, source_lang, target_lang,
                                            image_path="unknown", site_key=None):
        """
        Traduce i blocchi pilotando un sito web in una webview (Gemini, Dola...).
        Uses QMetaObject.invokeMethod with BlockingQueuedConnection to run on main thread.
        Implements retry logic with exponential backoff for robustness.

        Args:
            blk_list: List of TextBlock objects
            image: Image as numpy array
            source_lang: Source language (UI text)
            target_lang: Target language (UI text)
            image_path: Path to the image (for logging)
            site_key: chiave del sito browser (None = Gemini)

        Returns:
            JSON string with translations, or None if translation failed after all retries
        """
        import json
        import logging
        import time
        from modules.translator.processor import Translator

        logger.info(f"[GEMINI AUTO] Starting batch Gemini translation for {os.path.basename(image_path)}")

        if not blk_list:
            logger.warning("[GEMINI AUTO] No blocks to translate")
            return None

        # Sincronizza l'ordine dei blocchi spazialmente (Dall'alto in basso, sinistra a destra)
        # Questo garantisce che block_1 nel prompt corrisponda a blk_list[0]
        blk_list = sort_blk_list(blk_list, right_to_left=False)

        # Build blocks list with text (including empty ones for integrity)
        blocks = []
        for i, blk in enumerate(blk_list):
            text = (getattr(blk, 'text', '') or "").replace('"', '')
            blocks.append({'id': f'block_{i+1}', 'text': text})

        logger.info(f"[GEMINI AUTO] Prepared {len(blocks)} blocks for translation")

        # Build full_text with system prompt (similar to show_txt_modal)
        full_text = ""
        for i, blk in enumerate(blk_list):
            text = (getattr(blk, 'text', '') or "").replace('"', '')
            full_text += f"block_{i+1}: {text}\n\n"

        # Get target language in English for the prompt
        try:
            translator = Translator(self.main_page, source_lang, target_lang)
            if translator.is_llm_engine:
                t_lang = translator.target_lang_en
            else:
                t_lang = target_lang  # Fallback to UI text
        except Exception as e:
            logger.warning(f"[GEMINI AUTO] Could not get target lang from translator: {e}")
            t_lang = 'Italian'

        # Build system prompt
        prompt = self._build_gemini_system_prompt(t_lang)
        full_text += "\n" + "═"*50 + "\n"
        full_text += "TRANSLATION PROMPT (System Instruction):\n"
        full_text += "═"*50 + "\n\n"
        full_text += prompt

        # Retry configuration
        max_retries = 3
        base_delay = 2  # seconds
        last_error = None

        for attempt in range(max_retries):
            if attempt > 0:
                delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff: 2s, 4s, 8s
                logger.info(f"[GEMINI AUTO] Retry attempt {attempt}/{max_retries} for {os.path.basename(image_path)} after {delay}s delay")
                time.sleep(delay)

            # Store result in a mutable container for closure
            result_container = {'json_result': None, 'error': None}

            # Chiamata sul main thread. NB: Qt documenta che
            # BlockingQueuedConnection DEADLOCKA se l'oggetto appartiene gia'
            # al thread chiamante. Se per sbaglio questa funzione gira sul
            # thread GUI il batch si bloccherebbe per sempre: in quel caso si
            # invoca direttamente il metodo.
            from PySide6.QtCore import QMetaObject, Qt
            blocks_json = json.dumps(blocks)
            self.main_page._gemini_result_container = result_container
            self.main_page._browser_site_key = site_key

            # Controllo preventivo: se il metodo non esiste, o ha una firma
            # diversa, QMetaObject.invokeMethod fallisce in silenzio. Si
            # ottiene un container intatto e un errore che si legge solo come
            # "No JSON result", ripetuto 3 volte: si rischia di diagnosticare
            # un problema di DOM che non esiste. Qui si fallisce subito e con
            # la causa vera. Non ha senso riprovare un errore strutturale.
            slot = getattr(self.main_page, '_run_browser_automation_sync', None)
            if slot is None:
                logger.error(
                    "[BROWSER SITE] _run_browser_automation_sync non esiste su "
                    f"{type(self.main_page).__name__}: automator non eseguibile."
                )
                return None
            if hasattr(slot, '__code__'):
                # 5 = blocks_json, full_text, expected_count, source_lang, target_lang.
                # co_argcount include self perche' slot e' un bound method:
                # va sottratto, altrimenti il controllo fallirebbe sempre
                # (6 != 5) e bloccherebbe ogni traduzione.
                ottenuti = slot.__code__.co_argcount
                if getattr(slot, '__self__', None) is not None:
                    ottenuti -= 1
                if ottenuti != 5:
                    logger.error(
                        "[BROWSER SITE] Firma di _run_browser_automation_sync "
                        f"diversa dal chiamante: {ottenuti} parametri, attesi 5. "
                        "QMetaObject.invokeMethod non riuscirebbe a risolvere "
                        "il metodo. Allinea pipeline.py e ui_controller.py."
                    )
                    return None

            app = QtCore.QCoreApplication.instance()
            on_gui_thread = app is not None and QtCore.QThread.currentThread() == app.thread()

            if on_gui_thread:
                logger.info("[GEMINI AUTO] Gia' sul thread GUI: invocazione diretta")
                self.main_page._run_browser_automation_sync(
                    blocks_json, full_text, len(blocks), source_lang, t_lang)
            else:
                # Solo 5 argomenti nella firma Qt, deliberatamente.
                # Il sito viaggia sull'attributo d'istanza _browser_site_key
                # (impostato sopra), non come sesto argomento: aggiungerlo
                # legherebbe l'arita' del segnale a ogni modifica dei
                # parametri, e QMetaObject non farebbe match, perche' Qt
                # vede solo la firma reale e ignora i default di Python.
                # Inoltre Q_ARG(str, None) non e' un QString valido.
                # Stesso meccanismo gia' usato da _gemini_result_container.
                QMetaObject.invokeMethod(
                    self.main_page,
                    "_run_browser_automation_sync",
                    Qt.BlockingQueuedConnection,
                    QtCore.Q_ARG(str, blocks_json),
                    QtCore.Q_ARG(str, full_text),
                    QtCore.Q_ARG(int, len(blocks)),
                    QtCore.Q_ARG(str, source_lang),
                    QtCore.Q_ARG(str, t_lang)
                )

            # Read result from instance variable
            result_container = getattr(self.main_page, '_gemini_result_container', None)
            if result_container:
                if result_container.get('error'):
                    logger.warning(f"[GEMINI AUTO] Translation error (attempt {attempt+1}/{max_retries}): {result_container['error']}")
                    last_error = result_container['error']
                    continue

                json_result = result_container.get('json_result')
                if json_result:
                    logger.info(f"[GEMINI AUTO] Success! Received {len(json.loads(json_result))} translated blocks for {os.path.basename(image_path)}")
                    return json_result
                else:
                    # Invariante dello slot: scrive sempre json_result oppure
                    # error, senza eccezioni. Quindi "entrambi None" vuol dire
                    # solo che lo slot non e' mai partito (firma Qt non
                    # risolta, thread bloccato). "Nessuna traduzione"
                    # arriva come error, ed e' recuperabile con un retry:
                    # qui no, ritentare darebbe lo stesso risultato.
                    if (result_container.get('json_result') is None
                            and result_container.get('error') is None):
                        logger.error(
                            "[BROWSER SITE] _run_browser_automation_sync non ha "
                            "scritto alcun risultato: lo slot non e' mai stato "
                            "chiamato. Ritentare non serve."
                        )
                        return None
                    logger.warning(f"[GEMINI AUTO] No JSON result (attempt {attempt+1}/{max_retries})")
                    last_error = Exception("No JSON result returned")
                    continue
            else:
                logger.warning(f"[GEMINI AUTO] No result container (attempt {attempt+1}/{max_retries})")
                last_error = Exception("No result container")
                continue

        # All retries exhausted
        logger.error(f"[GEMINI AUTO] All {max_retries} attempts failed for {os.path.basename(image_path)}. Last error: {last_error}")
        return None

    def _build_gemini_system_prompt(self, t_lang: str) -> str:
        """Build the Gemini system prompt for translation.

        Usa il prompt personalizzato dall'utente (editor nelle impostazioni,
        con {t_lang} gia' sostituito) quando disponibile; ripiega sul
        template hardcoded solo se le impostazioni non sono raggiungibili.
        Prima di questa modifica il percorso batch/auto ignorava sempre
        l'editor e usava solo l'hardcoded.
        """
        try:
            settings_page = getattr(getattr(self, 'main_page', None), 'settings_page', None)
            get_prompt = getattr(settings_page, 'get_txt_prompt', None)
            if callable(get_prompt):
                custom = get_prompt(t_lang)
                if isinstance(custom, str) and custom.strip():
                    return custom
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"[GEMINI AUTO] Prompt personalizzato non leggibile ({e}): uso il default.")
        prompt = "═════════════════════════════════════════════════\n"
        prompt += "SYSTEM INSTRUCTION — JSON OUTPUT ONLY (STRICT)\n"
        prompt += "═════════════════════════════════════════════════\n\n"
        prompt += "You are a professional translator specialized in natural language.\n\n"
        prompt += f"Target language is {t_lang}. Use that.\n\n"
        prompt += "You are translating OCR-extracted comic text. The input may contain errors, typos, or incomplete sentences. You must interpret and correct them when needed to produce a natural and fluent language translation.\n\n"
        prompt += "═════════════════════════════════════════════════\n"
        prompt += "OUTPUT FORMAT — MANDATORY\n"
        prompt += "═════════════════════════════════════════════════\n\n"
        prompt += "You MUST return ONLY a valid JSON object.\n\n"
        prompt += "- No explanations\n"
        prompt += "- No extra text\n"
        prompt += "- No markdown\n"
        prompt += "- No code blocks\n"
        prompt += "- No comments\n\n"
        prompt += "If anything other than JSON is included, the response is INVALID.\n\n"
        prompt += "═════════════════════════════════════════════════\n"
        prompt += "REQUIRED STRUCTURE\n"
        prompt += "═════════════════════════════════════════════════\n\n"
        prompt += "You MUST use these keys:\n\n"
        prompt += '"block_1"\n'
        prompt += '"block_2"\n'
        prompt += '"block_3"\n'
        prompt += "etc.\n\n"
        prompt += "All keys MUST be present.\n\n"
        prompt += 'Even if a block is empty, include it with this string "...".\n\n'
        prompt += "═════════════════════════════════════════════════\n"
        prompt += "VALID JSON EXAMPLE\n"
        prompt += "═════════════════════════════════════════════════\n\n"
        prompt += '{\n'
        prompt += '  "block_1": "Text",\n'
        prompt += '  "block_2": "Text",\n'
        prompt += '  "block_3": "Text"\n'
        prompt += "}\n\n"
        prompt += "etc.\n\n"
        prompt += "═════════════════════════════════════════════════\n"
        prompt += "TRANSLATION RULES\n"
        prompt += "═════════════════════════════════════════════════\n\n"
        prompt += "- Translate into natural, fluent language\n"
        prompt += "- Preserve tone, slang, and intent\n"
        prompt += "- Adapt idioms naturally\n"
        prompt += "- Fix OCR mistakes when necessary\n"
        prompt += "- If already target language → return unchanged\n"
        prompt += "- NEVER use Korean or Japanese pronouns (당신, 그녀, 그, etc.)\n\n"
        prompt += "═════════════════════════════════════════════════\n"
        prompt += "CRITICAL CONSTRAINTS\n"
        prompt += "═════════════════════════════════════════════════\n\n"
        prompt += "- Do NOT rename keys\n"
        prompt += "- Do NOT change structure\n"
        prompt += "- Do NOT omit keys\n"
        prompt += "- Do NOT add keys\n"
        prompt += "- Do NOT output arrays\n"
        prompt += "- Do NOT output anything outside the JSON object\n\n"
        prompt += "═════════════════════════════════════════════════\n"
        prompt += "FINAL CHECK (MANDATORY)\n"
        prompt += "═════════════════════════════════════════════════\n\n"
        prompt += "Before responding, verify:\n\n"
        prompt += "1. Is the output valid JSON?\n"
        prompt += "2. Are all keys present?\n"
        prompt += "3. Is there any text outside JSON? → If YES, REMOVE it\n\n"
        prompt += "Only return the JSON object."
        return prompt


    def _normalize_json_keys_to_zero_based(self, json_string: str) -> str:
        """
        Convert 1-based JSON keys (block_1, block_2...) to 0-based (block_0, block_1...)
        for compatibility with set_texts_from_json.

        Args:
            json_string: JSON string with 1-based keys

        Returns:
            JSON string with 0-based keys
        """
        import json
        import re
        try:
            # Try to parse and rebuild with normalized keys
            data = json.loads(json_string)
            normalized = {}
            for key, value in data.items():
                match = re.match(r'block_(\d+)', key)
                if match:
                    new_key = f"block_{int(match.group(1)) - 1}"
                    normalized[new_key] = value
                else:
                    normalized[key] = value
            return json.dumps(normalized, ensure_ascii=False)
        except json.JSONDecodeError:
            # Fallback: regex replacement
            def replace_key(match):
                num = int(match.group(1))
                return f'"block_{num - 1}"'
            return re.sub(r'"block_(\d+)"', replace_key, json_string)

    def _cleanup_between_images(self):
        """
        Cleanup tra l'elaborazione di immagini consecutive nel batch.
        Rilascia risorse accumulate per evitare problemi con >2 pagine.
        """
        import gc
        try:
            # Il container vive su main_page, non su self: hasattr(self, ...)
            # era sempre False e il cleanup non faceva nulla, lasciando il JSON
            # dell'ultima pagina in memoria per tutta la sessione.
            container = getattr(self.main_page, '_gemini_result_container', None)
            if container is not None:
                result = container.get('json_result') or container.get('error')
                if result is None:
                    self.main_page._gemini_result_container = None
        except Exception:
            pass
        
        gc.collect()

    def _cleanup_after_batch(self):
        """Cleanup finale dopo completamento batch."""
        import gc
        try:
            if hasattr(self, 'ocr') and self.ocr:
                from modules.ocr.factory import OCREngineFactory
                OCREngineFactory.clear_cache()
        except Exception as e:
            logger.warning(f"[BATCH_CLEANUP] Errore cleanup OCR: {e}")
        
        try:
            from modules.inpainting.factory import InpainterFactory
            InpainterFactory.clear_cache()
            self.inpainter_cache = None  # Force reload on next batch
        except Exception as e:
            logger.warning(f"[BATCH_CLEANUP] Errore cleanup inpainter: {e}")
        
        try:
            # Il container e' su main_page: hasattr(self, ...) era sempre False e
            # il JSON dell'ultima pagina restava in memoria per tutta la sessione.
            if getattr(self.main_page, '_gemini_result_container', None) is not None:
                self.main_page._gemini_result_container = None
        except Exception:
            pass
        
        gc.collect()
        logger.info("[BATCH_CLEANUP] Cleanup batch completato")
