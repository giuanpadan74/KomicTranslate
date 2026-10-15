import cv2
import logging
import numpy as np
import os
import base64
import time
from .polygon_region import polygon_to_bbox, polygon_to_mask
from .textblock import TextBlock, sort_textblock_rectangles
from ..detection import does_rectangle_fit, is_mostly_contained
from typing import List
from app.ui.messages import Messages
from ..browser_sites import is_browser_site
from PySide6.QtCore import Qt


language_codes = {
    "Korean": "ko",
    "Japanese": "ja",
    "Chinese": "zh",
    "Simplified Chinese": "zh-CN",
    "Traditional Chinese": "zh-TW",
    "English": "en",
    "Russian": "ru",
    "French": "fr",
    "German": "de",
    "Dutch": "nl",
    "Spanish": "es",
    "Italian": "it",
    "Turkish": "tr",
    "Polish": "pl",
    "Portuguese": "pt",
    "Brazilian Portuguese": "pt-br",
    "Thai": "th",
    "Vietnamese": "vi",
    "Indonesian": "id",
    "Hungarian": "hu",
    "Finnish": "fi",
    "Arabic": "ar",
    }

def get_layout_direction(language: str) -> Qt.LayoutDirection:
    return Qt.LayoutDirection.RightToLeft if language == 'Arabic' else Qt.LayoutDirection.LeftToRight


# Lazy-loaded inpaint_map: imports PyTorch-based models only when actually needed
_inpaint_map_cache = None

def get_inpaint_map():
    global _inpaint_map_cache
    if _inpaint_map_cache is None:
        from ..inpainting.lama import LaMa
        from ..inpainting.mi_gan import MIGAN
        from ..inpainting.aot import AOT
        _inpaint_map_cache = {
            "LaMa": LaMa,
            "MI-GAN": MIGAN,
            "AOT": AOT,
        }
    return _inpaint_map_cache

# Keep backward compatibility for code that accesses inpaint_map directly
inpaint_map = None  # Will be populated on first use via get_inpaint_map()

def get_config(settings_page, blk_list=None, original_size=None):
    from ..inpainting.schema import Config
    strategy_settings = settings_page.get_hd_strategy_settings()
    
    # Base configuration with standardized parameters for all models
    config_kwargs = {
        "inpaint_max_res": int(strategy_settings.get('inpaint_max_res', 1024)),
        "inpaint_merge_distance": int(strategy_settings.get('inpaint_merge_distance', 512)),
        "blk_list": blk_list,
        "original_size": original_size
    }

    if strategy_settings['strategy'] == settings_page.ui.tr("Resize"):
        config = Config(
            hd_strategy="Resize", 
            hd_strategy_resize_limit = int(strategy_settings['resize_limit']),
            **config_kwargs
        )
    elif strategy_settings['strategy'] == settings_page.ui.tr("Crop"):
        config = Config(
            hd_strategy="Crop", 
            hd_strategy_crop_margin = int(strategy_settings['crop_margin']),
            hd_strategy_crop_trigger_size = int(strategy_settings['crop_trigger_size']),
            **config_kwargs
        )
    else:
        config = Config(hd_strategy="Original", **config_kwargs)

    return config

def get_language_code(lng: str) -> str:
    lng_cd = language_codes.get(lng, "en")  # Default to English if language not found
    return lng_cd

def rgba2hex(rgba_list):
    r,g,b,a = [int(num) for num in rgba_list]
    return "#{:02x}{:02x}{:02x}{:02x}".format(r, g, b, a)

def encode_image_array(img_array: np.ndarray):
    _, img_bytes = cv2.imencode('.png', img_array)
    return base64.b64encode(img_bytes).decode('utf-8')

def lists_to_blk_list(blk_list: List[TextBlock], texts_bboxes: List, texts_string: List):
    group = list(zip(texts_bboxes, texts_string))  

    for blk in blk_list:
        blk_entries = []
        
        for line, text in group:
            if blk.bubble_xyxy is not None:
                if does_rectangle_fit(blk.bubble_xyxy, line):
                    blk_entries.append((line, text))  
                elif is_mostly_contained(blk.bubble_xyxy, line, 0.5):
                    blk_entries.append((line, text)) 

            elif does_rectangle_fit(blk.xyxy, line):
                blk_entries.append((line, text)) 
            elif is_mostly_contained(blk.xyxy, line, 0.5):
                blk_entries.append((line, text)) 

        # Sort and join text entries
        sorted_entries = sort_textblock_rectangles(blk_entries, blk.source_lang_direction)
        if blk.source_lang in ['ja', 'zh']:
            blk.text = ''.join(text for bbox, text in sorted_entries)
        else:
            blk.text = ' '.join(text for bbox, text in sorted_entries)

    return blk_list

def _safe_print(*args, **kwargs):
    """print() che non solleva mai: sotto pythonw (--noconsole) stdout
    e' assente e flush=True darebbe OSError [Errno 22]."""
    try:
        print(*args, **kwargs)
    except (OSError, ValueError):
        pass


def generate_mask(img: np.ndarray, blk_list: List[TextBlock], default_padding: int = 5) -> np.ndarray:
    import sys
    logger = logging.getLogger(__name__)
    start_time = time.perf_counter()
    _safe_print(f"[generate_mask] AVVIO per {len(blk_list)} block su immagine {img.shape[1]}x{img.shape[0]}", flush=True)
    
    h, w, _ = img.shape
    mask = np.zeros((h, w), dtype=np.uint8)
    LONG_EDGE = 2048

    for blk in blk_list:
        bubble_bbox = (
            blk.get_active_inpaint_bbox() if hasattr(blk, 'get_active_inpaint_bbox') else getattr(blk, 'bubble_xyxy', None)
        )
        bubble_polygon = (
            blk.get_active_inpaint_polygon() if hasattr(blk, 'get_active_inpaint_polygon') else getattr(blk, 'polygon_points', None)
        )
        rectangle_mode = not getattr(blk, 'use_polygon_inpaint', True)
        is_bubble = getattr(blk, 'text_class', None) == 'text_bubble' and (
            bubble_polygon is not None or bubble_bbox is not None
        )

        if rectangle_mode and bubble_bbox is not None:
            bx1, by1, bx2, by2 = [int(v) for v in bubble_bbox]
            if bx1 >= bx2 or by1 >= by2:
                continue
            block_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.rectangle(block_mask, (bx1, by1), (bx2, by2), 255, -1)
            mask = cv2.bitwise_or(mask, block_mask)
            continue

        bboxes = blk.inpaint_bboxes
        if bboxes is None or len(bboxes) == 0:
            continue

        xs = [x for x1, _, x2, _ in bboxes for x in (x1, x2)]
        ys = [y for _, y1, _, y2 in bboxes for y in (y1, y2)]
        min_x, max_x = int(min(xs)), int(max(xs))
        min_y, max_y = int(min(ys)), int(max(ys))
        roi_w, roi_h = max_x - min_x + 1, max_y - min_y + 1

        ds = max(1.0, max(roi_w, roi_h) / LONG_EDGE)
        mw, mh = int(roi_w / ds) + 2, int(roi_h / ds) + 2
        pad_offset = 1

        small = np.zeros((mh, mw), dtype=np.uint8)
        for x1, y1, x2, y2 in bboxes:
            x1i = int((x1 - min_x) / ds) + pad_offset
            y1i = int((y1 - min_y) / ds) + pad_offset
            x2i = int((x2 - min_x) / ds) + pad_offset
            y2i = int((y2 - min_y) / ds) + pad_offset
            cv2.rectangle(small, (x1i, y1i), (x2i, y2i), 255, -1)

        kernel = np.ones((15, 15), np.uint8)
        closed = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue

        polys = []
        for cnt in contours:
            pts = cnt.squeeze(1)
            if pts.ndim != 2 or pts.shape[0] < 3:
                continue
            pts_f = (pts.astype(np.float32) - pad_offset) * ds
            pts_f[:, 0] += min_x
            pts_f[:, 1] += min_y
            polys.append(pts_f.astype(np.int32))
        if not polys:
            continue

        # Create a specific mask for this block
        block_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(block_mask, polys, 255)

        kernel_size = default_padding
        src_lang = getattr(blk, 'source_lang', None)
        if src_lang and src_lang not in ['ja', 'ko']:
            kernel_size = 3
            
        if is_bubble:
            clip_bbox = polygon_to_bbox(bubble_polygon) if bubble_polygon is not None else bubble_bbox
            # Il rettangolo visibile (xyxy, allargabile a mano) fa fede: se
            # esce dal bubble sotto-rilevato, la maschera deve poterlo
            # coprire, altrimenti l'allargamento manuale viene ignorato.
            try:
                tx1, ty1, tx2, ty2 = [int(v) for v in blk.xyxy]
                if tx1 < tx2 and ty1 < ty2:
                    cbx1, cby1, cbx2, cby2 = [int(v) for v in clip_bbox]
                    clip_bbox = (min(cbx1, tx1), min(cby1, ty1),
                                 max(cbx2, tx2), max(cby2, ty2))
            except (TypeError, ValueError):
                pass
            bx1, by1, bx2, by2 = clip_bbox
            valid = [p for p in polys
                     if (p[:, 0] >= bx1).all() and (p[:, 0] <= bx2).all()
                     and (p[:, 1] >= by1).all() and (p[:, 1] <= by2).all()]
            if valid:
                dists = []
                for p in valid:
                    dists.extend([
                        p[:, 0].min() - bx1,
                        bx2 - p[:, 0].max(),
                        p[:, 1].min() - by1,
                        by2 - p[:, 1].max()
                    ])
                min_dist = min(dists)
                if kernel_size >= min_dist:
                    kernel_size = max(1, int(min_dist * 0.8))

        # Dilation: more conservative if it's a bubble to avoid artifacts
        # Using fewer iterations and a more controlled kernel
        dil_kernel = np.ones((kernel_size, kernel_size), np.uint8)
        # iterations=2 is generally enough to cover text borders without excessive leakage
        dilated = cv2.dilate(block_mask, dil_kernel, iterations=2)

        # HARD-CLIP: If it's a bubble, ensure the mask never goes outside the bubble bounding box
        if is_bubble:
            if bubble_polygon is not None:
                clip_mask = polygon_to_mask((h, w), bubble_polygon)
            else:
                bx1, by1, bx2, by2 = bubble_bbox
                clip_mask = np.zeros((h, w), dtype=np.uint8)
                cv2.rectangle(clip_mask, (int(bx1), int(by1)), (int(bx2), int(by2)), 255, -1)
            # Unione con il rettangolo utente (cfr. sopra): copre gli
            # allargamenti manuali oltre un bubble sotto-rilevato.
            try:
                tx1, ty1, tx2, ty2 = [int(v) for v in blk.xyxy]
                if tx1 < tx2 and ty1 < ty2:
                    cv2.rectangle(clip_mask, (tx1, ty1), (tx2, ty2), 255, -1)
            except (TypeError, ValueError):
                pass
            dilated = cv2.bitwise_and(dilated, clip_mask)

        mask = cv2.bitwise_or(mask, dilated)

    elapsed = (time.perf_counter() - start_time) * 1000
    _safe_print(f"[generate_mask] completata in {elapsed:.2f}ms per {len(blk_list)} block su immagine {w}x{h}")
    return mask

def validate_ocr(main_page, source_lang):
    settings_page = main_page.settings_page
    tr = settings_page.ui.tr
    settings = settings_page.get_all_settings()
    credentials = settings.get('credentials', {})
    source_lang_en = main_page.lang_mapping.get(source_lang, source_lang)
    ocr_tool = settings['tools']['ocr']
    
    # Validate OCR API keys
        
    # Validate GPT OCR
    if source_lang_en == "Russian":
        if (ocr_tool == tr('Default') and 
            not credentials.get(tr('Open AI GPT'), {}).get('api_key')):
            Messages.show_api_key_ocr_gpt4v_error(main_page)
            return False
    
    return True

def validate_translator(main_page, source_lang, target_lang):
    settings_page = main_page.settings_page
    tr = settings_page.ui.tr
    settings = settings_page.get_all_settings()
    credentials = settings.get('credentials', {})
    translator_tool = settings['tools']['translator']

    # I siti browser (Gemini, Dola...) non usano API key: si guidano
    # aprendo il sito in una webview e pilotandolo via JS. Nessuna
    # credenziale da verificare.
    #
    # Va detto PRIMA dei controlli legacy qui sotto: usano confronti per
    # sottostringa ('Gemini' in translator_tool), e il sito browser si
    # chiama esattamente 'Gemini'. Senza questo controllo verrebbe scambiato
    # per il modello Gemini via API e si chiederebbe una chiave Google.
    if is_browser_site(translator_tool):
        return True

    # Validate translator API keys
    if (translator_tool == tr("DeepL") and
        not credentials.get(tr("DeepL"), {}).get("api_key")):
        Messages.show_api_key_translator_error(main_page)
        return False
    

    
    # Controllo migliorato per modelli OpenAI
    # Controlla sia i modelli tradizionali che quelli dal model manager
    needs_openai_key = False
    credentials_key = None
    
    if 'GPT' in translator_tool:
        needs_openai_key = True
        credentials_key = 'OpenAI'  # Cambiato da 'Open AI GPT' a 'OpenAI'
    else:
        # Controlla se è un modello OpenAI dal model manager
        try:
            from .model_manager import model_manager  # Correzione import
            if translator_tool in model_manager.models:
                model_data = model_manager.models[translator_tool]
                provider = model_data.get('provider', '').lower()
                if provider == 'openai':
                    needs_openai_key = True
                    credentials_key = model_manager.get_translation_credentials_key(translator_tool)
                elif provider == 'anthropic':
                    credentials_key = 'Anthropic'
                elif provider == 'google':
                    credentials_key = 'Google'
                elif provider == 'deepseek':
                    credentials_key = 'DeepSeek'
                elif provider == 'openrouter':
                    credentials_key = 'OpenRouter'
                    
                # Controlla se serve una API key per questo provider
                if credentials_key and not credentials.get(tr(credentials_key), {}).get('api_key'):
                    Messages.show_api_key_translator_error(main_page)
                    return False
        except Exception as e:
            print(f"Error checking model manager: {e}")
    
    # Controllo specifico per OpenAI
    if needs_openai_key:
        # Usa la chiave corretta dal model manager invece di hardcodare 'Open AI GPT'
        check_key = credentials_key if credentials_key else 'OpenAI'  # Cambiato da 'Open AI GPT' a 'OpenAI'
        if not credentials.get(tr(check_key), {}).get('api_key'):
            Messages.show_api_key_translator_error(main_page)
            return False
        
    # Controlli legacy per modelli tradizionali
    if ('Gemini' in translator_tool and 
        not credentials.get(tr('Google'), {}).get('api_key')):
        Messages.show_api_key_translator_error(main_page)
        return False
        
    if ('Claude' in translator_tool and 
        not credentials.get(tr('Anthropic Claude'), {}).get('api_key')):
        Messages.show_api_key_translator_error(main_page)
        return False
    
    # Check service-specific incompatibilities
    if translator_tool == tr('DeepL'):
        if target_lang == main_page.tr('Traditional Chinese'):
            Messages.show_deepl_ch_error(main_page)
            return False
        if target_lang == main_page.tr('Thai'):
            Messages.show_deepl_th_error(main_page)
            return False
        if target_lang == main_page.tr('Vietnamese'):
            Messages.show_deepl_vi_error(main_page)
            return False
            
    if  translator_tool == tr('Google Translate'):
            if (source_lang == main_page.tr('Brazilian Portuguese') or 
                target_lang == main_page.tr('Brazilian Portuguese')):
                Messages.show_googlet_ptbr_error(main_page)
                return False
    
    return True

def font_selected(main_page):
    if not main_page.render_settings().font_family:
        Messages.select_font_error(main_page)
        return False
    return True

def validate_settings(main_page, source_lang, target_lang):
    if not validate_ocr(main_page, source_lang):
        return False
    if not validate_translator(main_page, source_lang, target_lang):
        return False
    if not font_selected(main_page):
        return False
    
    return True

def is_directory_empty(directory):
    # Walk through the directory
    for root, dirs, files in os.walk(directory):
        # If any file is found, the directory is not empty
        if files:
            return False
    # If no files are found, check if there are any subdirectories
    for root, dirs, files in os.walk(directory):
        if dirs:
            # Recursively check subdirectories
            for dir in dirs:
                if not is_directory_empty(os.path.join(root, dir)):
                    return False
    return True
