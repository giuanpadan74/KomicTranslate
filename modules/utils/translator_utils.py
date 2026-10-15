import cv2
import base64
import json
import re
import numpy as np
import warnings
# OpenAI, google.generativeai, anthropic lazy-loaded in functions that use them
from .textblock import TextBlock
from typing import List, Dict, Any, Optional
from PIL import Image
import io
from .model_manager import model_manager

# Silenzia i warning di google-generativeai per il passaggio al nuovo SDK
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# Dynamic MODEL_MAP using ModelManager
MODEL_MAP = model_manager.get_model_map()

def refresh_model_map():
    """Refresh the MODEL_MAP from ModelManager."""
    global MODEL_MAP
    MODEL_MAP = model_manager.get_model_map()

def encode_image_array(img_array: np.ndarray):
    if img_array is None:
        return None
    try:
        if not hasattr(img_array, 'size') or img_array.size == 0:
            return None
        success, img_bytes = cv2.imencode('.png', img_array)
        if not success:
            return None
        return base64.b64encode(img_bytes).decode('utf-8')
    except Exception:
        return None

def get_raw_text(blk_list: List[TextBlock]):
    rw_txts_dict = {}
    for idx, blk in enumerate(blk_list):
        block_key = f"block_{idx}"
        # Assicurati che il testo non sia None, usa stringa vuota se necessario
        text = getattr(blk, 'text', '') or ""
        rw_txts_dict[block_key] = text
    
    raw_texts_json = json.dumps(rw_txts_dict, ensure_ascii=False, indent=4)
    
    return raw_texts_json

def get_raw_translation(blk_list: List[TextBlock]):
    rw_translations_dict = {}
    for idx, blk in enumerate(blk_list):
        block_key = f"block_{idx}"
        rw_translations_dict[block_key] = blk.translation
    
    raw_translations_json = json.dumps(rw_translations_dict, ensure_ascii=False, indent=4)
    
    return raw_translations_json

def _extract_json_object(text: str) -> Optional[str]:
    fence_match = re.search(r"```(?:json|JSON)?\s*([\s\S]*?)\s*```", text)
    if fence_match:
        inner = fence_match.group(1)
        start = inner.find("{")
        if start != -1:
            brace = 0
            in_str = False
            esc = False
            for i, ch in enumerate(inner[start:], start):
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        brace += 1
                    elif ch == '}':
                        brace -= 1
                        if brace == 0:
                            return inner[start:i+1]
    start = text.find("{")
    if start == -1:
        return None
    brace = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '{':
                brace += 1
            elif ch == '}':
                brace -= 1
                if brace == 0:
                    return text[start:i+1]
    return None


def _repair_truncated_json(text: str) -> Optional[dict]:
    """
    Soluzione 4 (difensiva): estrae coppie block_N/valore tramite regex anche
    quando il JSON è troncato (parentesi finale mancante, code-fence non chiusa).
    Viene chiamato solo se _extract_json_object fallisce.

    Returns:
        dict con le chiavi block_N trovate, oppure None se non trova nulla.
    """
    # Prima prova con regex standard per JSON corretto
    pattern = re.compile(
        r'"block_(\d+)"\s*:\s*"((?:[^"\\]|\\.)*)"',
        re.DOTALL
    )
    result = {}
    for match in pattern.finditer(text):
        idx = match.group(1)
        raw_value = match.group(2)
        value = _unescape_json_string(raw_value)
        result[f"block_{idx}"] = value

    repaired_quotes = _repair_json_with_unescaped_quotes(text) or {}
    repaired_last_block = _repair_truncated_last_block(text) or {}

    merged = {}
    for candidate in (result, repaired_quotes, repaired_last_block):
        for key, value in candidate.items():
            if key not in merged or (value and len(str(value).strip()) >= len(str(merged[key]).strip())):
                merged[key] = value

    return merged if merged else None


def _repair_truncated_last_block(text: str) -> Optional[dict]:
    """
    Ripara JSON con ultimo blocco troncato senza chiusura.
    Esempio: "block_5": "Testo trunc
    """
    result = {}

    block_start_pattern = re.compile(r'"block_(\d+)"\s*:\s*"')

    pos = 0
    while pos < len(text):
        match = block_start_pattern.search(text, pos)
        if not match:
            break

        idx = match.group(1)
        value_start = match.end()

        remaining = text[value_start:]

        next_block_match = re.search(r'"\s*,\s*"block_(\d+)"\s*:', remaining)
        closing_brace_match = re.search(r'"\s*}', remaining)
        end_of_text_match = re.search(r'["\']?\s*$', remaining)

        if next_block_match and closing_brace_match:
            next_block_pos = next_block_match.start()
            closing_brace_pos = closing_brace_match.start()
            if next_block_pos < closing_brace_pos:
                value_end = value_start + next_block_pos
            else:
                value_end = value_start + closing_brace_pos
        elif next_block_match:
            value_end = value_start + next_block_match.start()
        elif closing_brace_match:
            value_end = value_start + closing_brace_match.start()
        elif end_of_text_match:
            value_end = value_start + end_of_text_match.start()
        else:
            value_end = len(text)

        raw_value = text[value_start:value_end]
        result[f"block_{idx}"] = _unescape_json_string(raw_value)

        pos = value_end

    return result if result else None


def _unescape_json_string(s: str) -> str:
    """Unescape common JSON escape sequences."""
    return (
        s.replace('\\n', '\n')
        .replace('\\r', '\r')
        .replace('\\t', '\t')
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace('\\\\', '\\')
    )


def _repair_json_with_unescaped_quotes(text: str) -> Optional[dict]:
    """
    Ripara JSON in cui le virgolette doppie all'interno delle stringhe
    non sono state escaped (es. "IRXA" invece di \"IRXA\").
    Il LLM a volte produce questo tipo di output malformato.
    """
    result = {}

    block_start_pattern = re.compile(r'"block_(\d+)"\s*:\s*"')

    pos = 0
    while pos < len(text):
        match = block_start_pattern.search(text, pos)
        if not match:
            break

        idx = match.group(1)
        value_start = match.end()

        remaining = text[value_start:]

        next_block_match = re.search(r'"\s*,\s*"block_(\d+)"\s*:', remaining)
        closing_brace_match = re.search(r'"\s*}', remaining)

        if next_block_match and closing_brace_match:
            next_block_pos = next_block_match.start()
            closing_brace_pos = closing_brace_match.start()
            if next_block_pos < closing_brace_pos:
                value_end = value_start + next_block_pos
            else:
                value_end = value_start + closing_brace_pos
        elif next_block_match:
            value_end = value_start + next_block_match.start()
        elif closing_brace_match:
            value_end = value_start + closing_brace_match.start()
        else:
            value_end = len(text)

        raw_value = text[value_start:value_end]
        result[f"block_{idx}"] = _unescape_json_string(raw_value)

        pos = value_end

    return result if result else None


def _escape_newlines_in_strings(s: str) -> str:
    out = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
        out.append(ch)
        if esc:
            esc = False
        else:
            if ch == "\\":
                esc = True
            elif ch == '"':
                in_str = not in_str
    return ''.join(out)

def validate_translation_integrity(data: Any, expected_count: int) -> Dict[str, Any]:
    """
    Valida l'integrità del risultato della traduzione.
    Verifica che siano presenti tutti i blocchi e che non ci siano troncamenti.
    """
    report = {
        "is_valid": True,
        "missing_blocks": [],
        "empty_blocks": [],
        "total_found": 0,
        "expected": expected_count,
        "error": None
    }

    try:
        if isinstance(data, str):
            data = json.loads(data)
        
        if not isinstance(data, dict):
            report["is_valid"] = False
            report["error"] = "Il risultato non è un dizionario JSON valido."
            return report

        # Se il JSON è incapsulato in un campo "translation"
        if "translation" in data and isinstance(data["translation"], dict):
            data = data["translation"]

        # Verifica i blocchi (supporta sia 0-based che 1-based per flessibilità)
        found_blocks = {}
        for k, v in data.items():
            match = re.search(r"block_(\d+)", str(k))
            if match:
                idx = int(match.group(1))
                found_blocks[idx] = v

        report["total_found"] = len(found_blocks)

        # Determina se la numerazione è 0-based o 1-based
        is_one_based = 0 not in found_blocks and expected_count in found_blocks
        start_idx = 1 if is_one_based else 0
        end_idx = expected_count + 1 if is_one_based else expected_count

        for i in range(start_idx, end_idx):
            if i not in found_blocks:
                report["missing_blocks"].append(f"block_{i}")
                report["is_valid"] = False
            else:
                val = str(found_blocks[i]).strip()
                if not val or val.lower() in ["null", "none", "n/a"]:
                    report["empty_blocks"].append(f"block_{i}")
                    report["is_valid"] = False

    except Exception as e:
        report["is_valid"] = False
        report["error"] = str(e)

    return report

def _sanitize_placeholder_translations(blk_list: List[TextBlock]):
    """Svuota le traduzioni placeholder su sorgente vuota.

    I modelli copiano spesso l'esempio del prompt ("...") quando il valore
    sorgente e' "" (OCR mancato, tipico delle caselle disegnate a mano prima
    del fix OCR). Senza questo filtro il rendering stampa letteralmente '...'.
    """
    _placeholders = {'...', '…', '..', '.', '--', '-', 'null', 'none', 'n/a'}
    for blk in blk_list:
        try:
            src = (getattr(blk, 'text', '') or '').strip()
            tr = (getattr(blk, 'translation', '') or '')
            if not src:
                blk.translation = ""
            elif isinstance(tr, str) and tr.strip().lower() in _placeholders:
                blk.translation = ""
        except Exception:
            continue


def set_texts_from_json(blk_list: List[TextBlock], json_string: str, img_used: bool = True):
    extracted_json = _extract_json_object(json_string)
    if extracted_json:
        try:
            extracted_json = _escape_newlines_in_strings(extracted_json.strip())
            data = json.loads(extracted_json)
            if isinstance(data, dict) and "translation" in data and isinstance(data["translation"], dict):
                data = data["translation"]
            for idx, blk in enumerate(blk_list):
                key = f"block_{idx}"
                if key in data:
                    blk.translation = data[key]
                    print(f"TextBlock {idx} tradotto: '{blk.translation[:50]}...'")
                else:
                    print(f"Warning: {key} not found in JSON string.")
            _sanitize_placeholder_translations(blk_list)
        except json.JSONDecodeError as e:
            print(f"Errore nel parsing JSON: {e}")
            print(f"JSON estratto: {extracted_json[:200]}...")
            # Prova il repair anche per JSON estratto ma non parsabile
            repaired_data = _repair_truncated_json(json_string)
            if repaired_data:
                print(f"[JSON REPAIR] Repair su JSONDecodeError: recuperati {len(repaired_data)} blocchi tramite regex")
                for idx, blk in enumerate(blk_list):
                    key = f"block_{idx}"
                    if key in repaired_data:
                        blk.translation = repaired_data[key]
                        print(f"TextBlock {idx} tradotto (repair): '{blk.translation[:50]}...'")
                _sanitize_placeholder_translations(blk_list)
    else:
        # Se non trova JSON e l'immagine non è stata usata, prova a trattare come JSON incompleto
        if not img_used:
            print("JSON non trovato, ma immagine non usata. Provo a riparare aggiungendo parentesi graffe...")
            # Prova ad aggiungere { } attorno alla risposta
            repaired_json = f"{{{json_string}}}"
            extracted_json = _extract_json_object(repaired_json)
            if extracted_json:
                try:
                    extracted_json = _escape_newlines_in_strings(extracted_json.strip())
                    data = json.loads(extracted_json)
                    if isinstance(data, dict) and "translation" in data and isinstance(data["translation"], dict):
                        data = data["translation"]
                    for idx, blk in enumerate(blk_list):
                        key = f"block_{idx}"
                        if key in data:
                            blk.translation = data[key]
                            print(f"TextBlock {idx} tradotto (riparato): '{blk.translation[:50]}...'")
                        else:
                            print(f"Warning: {key} not found in repaired JSON string.")
                    _sanitize_placeholder_translations(blk_list)
                    return  # Successo, esci
                except json.JSONDecodeError as e:
                    print(f"Errore nel parsing JSON riparato: {e}")

        # Soluzione 4: ultimo fallback — regex rescue su JSON troncato o malformato
        repaired_data = _repair_truncated_json(json_string)
        if repaired_data:
            print(f"[JSON REPAIR] Recuperati {len(repaired_data)}/{len(blk_list)} blocchi tramite regex (JSON troncato)")
            for idx, blk in enumerate(blk_list):
                key = f"block_{idx}"
                if key in repaired_data:
                    blk.translation = repaired_data[key]
                    print(f"TextBlock {idx} tradotto (regex rescue): '{blk.translation[:50]}...'")
                else:
                    print(f"[JSON REPAIR] Warning: {key} non trovato nemmeno con regex.")
            _sanitize_placeholder_translations(blk_list)
        else:
            print("No JSON found in the input string.")
            print(f"Contenuto ricevuto (primi 300 caratteri): {json_string[:300]}...")


def set_upper_case(blk_list: List[TextBlock], upper_case: bool):
    for blk in blk_list:
        translation = blk.translation
        if upper_case and not translation.isupper():
            blk.translation = translation.upper() 
        elif not upper_case and translation.isupper():
            blk.translation = translation.capitalize()
        else:
            blk.translation = translation

def format_translations(blk_list: List[TextBlock], trg_lng_cd: str, upper_case: bool =True):
    for blk in blk_list:
        translation = blk.translation
        if any(lang in trg_lng_cd.lower() for lang in ['zh', 'ja', 'th']):

            if trg_lng_cd == 'zh-TW':
                trg_lng_cd = 'zh-Hant'
            elif trg_lng_cd == 'zh-CN':
                trg_lng_cd = 'zh-Hans'
            else:
                trg_lng_cd = trg_lng_cd

            # import lazy: stanza pesa molto e serve solo per la segmentazione CJK
            import stanza
            stanza.download(trg_lng_cd, processors='tokenize')
            nlp = stanza.Pipeline(trg_lng_cd, processors='tokenize')
            doc = nlp(translation)
            seg_result = []
            for sentence in doc.sentences:
                for word in sentence.words:
                    seg_result.append(word.text)
            translation = ''.join(word if word in ['.', ','] else f' {word}' for word in seg_result).lstrip()
            blk.translation = translation
        else:
            set_upper_case(blk_list, upper_case)

def is_there_text(blk_list: List[TextBlock]) -> bool:
    return any(blk.text and blk.text.strip() for blk in blk_list)

def encode_image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Encode PIL Image to base64 string."""
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return img_str

def preprocess_text(text: str) -> str:
    """Preprocess text before translation."""
    # Add any text preprocessing logic here
    return text.strip()

def format_translation_result(result: str) -> str:
    """Format the translation result."""
    # Add any result formatting logic here
    return result.strip()
