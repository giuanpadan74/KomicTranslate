import json
import re
from typing import Any, Dict, Tuple

from modules.utils.translator_utils import (
    _extract_json_object,
    _repair_truncated_json,
    validate_translation_integrity,
)


BLOCK_KEY_PATTERN = re.compile(r"^block_(\d+)$", re.IGNORECASE)
BLOCK_LINE_PATTERN = re.compile(
    r'"?block_(\d+)"?\s*[:=]\s*([\s\S]*?)(?=(?:,\s*"?block_\d+"?\s*[:=])|(?:\n\s*"?block_\d+"?\s*[:=])|(?:\s*}\s*$))',
    re.IGNORECASE,
)

# Chiavi block_N scritte senza virgolette dall'LLM (es. block_11: "testo").
# Non e'Match all'inizio per non toccare chiavi gia' correttamente quotate.
BARE_BLOCK_KEY_PATTERN = re.compile(r'(?<!["\w])block_(\d+)(\s*[:=])')


def _quote_bare_block_keys(text: str) -> str:
    """
    Normalizza le chiavi block_N scritte senza virgolette dall'LLM.

    Esempio:
        {
          "block_1": "CIAO",
          block_11: "OH, HAI RAGIONE,",
        }
    diventa JSON valido. Senza questo, i riparatori basati su regex cercano
    la prossima chiave come '"block_' e non la vedono, quindi il valore di
    block_1 'inghiotte' le righe seguenti corrompendo l'intero payload.
    """
    return BARE_BLOCK_KEY_PATTERN.sub(r'"block_\1"\2', text)


def parse_translation_payload(
    raw_text: str,
    expected_count: int,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    # Fast-path Rust con fallback Python invariato (cfr. modules/_rs_bridge.py).
    try:
        from modules._rs_bridge import rs_parse_translation_payload

        rs_result = rs_parse_translation_payload(raw_text, expected_count)
        if rs_result is not None:
            return rs_result
    except Exception:
        pass
    text = (raw_text or "").strip()
    if not text:
        return {}, _build_report(False, expected_count, "Risposta vuota.", "empty")

    candidates = [text]
    extracted = _extract_json_object(text)
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    for candidate in candidates:
        parsed = _try_json_load(candidate)
        if parsed is None:
            continue
        normalized = normalize_translation_payload(parsed)
        report = _validation_report(normalized, expected_count, "json")
        if normalized:
            return normalized, report

    # Tentativo corretto: il JSON e' valido a parte le chiavi block_N senza
    # virgolette. Va PRIMA dei riparatori regex, altrimenti verrebbe scavalcato
    # da payload corrotti (vedi _repair_truncated_json).
    quoted = _quote_bare_block_keys(text)
    if quoted != text:
        for candidate in (quoted, _extract_json_object(quoted) or ""):
            if not candidate:
                continue
            parsed = _try_json_load(candidate)
            if parsed is None:
                continue
            normalized = normalize_translation_payload(parsed)
            if normalized:
                return normalized, _validation_report(
                    normalized, expected_count, "repair"
                )

    repaired = _repair_truncated_json(text) or {}
    if repaired:
        report = _validation_report(repaired, expected_count, "repair")
        return repaired, report

    regex_payload = _recover_blocks_with_regex(text)
    if regex_payload:
        report = _validation_report(regex_payload, expected_count, "regex")
        return regex_payload, report

    return {}, _build_report(
        False,
        expected_count,
        "Impossibile ricostruire un payload di traduzione valido.",
        "unrecoverable",
    )


def normalize_translation_payload(data: Any) -> Dict[str, str]:
    if isinstance(data, dict):
        nested = _extract_nested_payload(data)
        if nested is not None:
            return normalize_translation_payload(nested)
        return _normalize_keyed_dict(data)

    if isinstance(data, list):
        normalized: Dict[str, str] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            block_key = _normalize_block_key(
                item.get("id") or item.get("block_id") or item.get("block")
            )
            if not block_key:
                continue
            normalized[block_key] = _pick_translation_value(item)
        return normalized

    return {}


def _extract_nested_payload(data: Dict[str, Any]) -> Any:
    for key in ("translation", "translations", "result", "results", "data"):
        value = data.get(key)
        if isinstance(value, (dict, list)):
            return value
    return None


def _normalize_keyed_dict(data: Dict[str, Any]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in data.items():
        block_key = _normalize_block_key(key)
        if not block_key:
            continue
        normalized[block_key] = _normalize_value(value)
    return normalized


def _normalize_block_key(raw_key: Any) -> str:
    if raw_key is None:
        return ""
    if isinstance(raw_key, int):
        return f"block_{raw_key}"
    key = str(raw_key).strip().strip('"').strip("'")
    if key.isdigit():
        return f"block_{key}"
    match = re.search(r"block_(\d+)", key, re.IGNORECASE)
    if not match:
        return ""
    return f"block_{match.group(1)}"


def _pick_translation_value(item: Dict[str, Any]) -> str:
    for key in ("it", "translation", "target", "text", "fr", "source"):
        if key in item:
            return _normalize_value(item.get(key))
    return ""


def _normalize_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("it", "translation", "target", "text", "fr", "source"):
            if key in value:
                return _normalize_value(value.get(key))
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value).strip()


def _try_json_load(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _recover_blocks_with_regex(text: str) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for match in BLOCK_LINE_PATTERN.finditer(text):
        block_key = f"block_{match.group(1)}"
        raw_value = match.group(2).strip().rstrip(",").strip()
        normalized[block_key] = _clean_regex_value(raw_value)
    return normalized


def _clean_regex_value(raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        try:
            return json.loads(value)
        except Exception:
            value = value[1:-1]
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        value = value[1:-1]
    return (
        value.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
        .strip()
    )


def _validation_report(
    payload: Dict[str, str],
    expected_count: int,
    source: str,
) -> Dict[str, Any]:
    base_report = validate_translation_integrity(payload, expected_count)
    base_report["source"] = source
    return base_report


def _build_report(
    is_valid: bool,
    expected_count: int,
    error: str,
    source: str,
) -> Dict[str, Any]:
    return {
        "is_valid": is_valid,
        "missing_blocks": [],
        "empty_blocks": [],
        "total_found": 0,
        "expected": expected_count,
        "error": error,
        "source": source,
    }
