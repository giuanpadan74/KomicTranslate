import json
import re
from typing import Optional, List, Dict, Any
from .types import VisionFailureReason


def parse_json_response(raw_text: str) -> Optional[List[Dict[str, Any]]]:
    cleaned = raw_text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
        return None
    except json.JSONDecodeError:
        return _try_fallback_parse(cleaned)


def _try_fallback_parse(text: str) -> Optional[List[Dict[str, Any]]]:
    block_pattern = re.compile(
        r'["\']?id["\']?\s*:\s*["\']?(block_\d+)["\']?', re.IGNORECASE
    )
    fr_pattern = re.compile(r'["\']?fr["\']?\s*:\s*["\']([^"\']+)["\']', re.IGNORECASE)
    it_pattern = re.compile(r'["\']?it["\']?\s*:\s*["\']([^"\']+)["\']', re.IGNORECASE)
    matches = block_pattern.finditer(text)
    results = []
    for m in matches:
        block_id = m.group(1)
        fr = ""
        it = ""
        fr_m = re.search(fr_pattern, text[m.end() : m.end() + 500])
        if fr_m:
            fr = fr_m.group(1)
        it_m = re.search(it_pattern, text[m.end() : m.end() + 500])
        if it_m:
            it = it_m.group(1)
        results.append({"id": block_id, "fr": fr, "it": it})
    return results if results else None


def validate_completeness(
    data: List[Dict[str, Any]], expected_count: int
) -> tuple[bool, VisionFailureReason]:
    if not data:
        return False, VisionFailureReason.JSON_NOT_FOUND
    found = sum(1 for item in data if item.get("id"))
    if found < expected_count:
        return False, VisionFailureReason.JSON_INCOMPLETE
    return True, VisionFailureReason.JSON_NOT_FOUND


def normalize_keys(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for item in data:
        entry = {}
        raw_id = item.get("id") or item.get("block_id") or item.get("block") or ""
        entry["id"] = _normalize_id(raw_id)
        entry["fr"] = item.get("fr") or item.get("text") or item.get("source") or ""
        entry["it"] = item.get("it") or item.get("translation") or item.get("target") or ""
        entry["note"] = item.get("note") or item.get("notes") or None
        normalized.append(entry)
    return normalized


def _normalize_id(raw_id: str) -> str:
    if isinstance(raw_id, int):
        return f"block_{raw_id}"
    raw_id = str(raw_id).strip()
    if raw_id.startswith("block_"):
        return raw_id
    return f"block_{raw_id}"


def parse_and_validate(
    raw_text: str, expected_count: int
) -> tuple[Optional[List[Dict[str, Any]]], VisionFailureReason]:
    data = parse_json_response(raw_text)
    if data is None:
        return None, VisionFailureReason.JSON_PARSE_ERROR
    data = normalize_keys(data)
    is_complete, reason = validate_completeness(data, expected_count)
    if not is_complete:
        return data, reason
    return data, VisionFailureReason.JSON_NOT_FOUND