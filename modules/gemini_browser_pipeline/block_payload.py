import json
import numpy as np
from typing import List, Dict, Any


def textblock_to_payload(blk_list: List, mode: str = "translate") -> List[Dict[str, Any]]:
    blocks = []
    for i, blk in enumerate(blk_list):
        block_id = f"block_{i+1}"
        entry = {"id": block_id}
        if mode == "ocr_translate":
            entry["bbox"] = _safe_bbox(blk)
            entry["text_class"] = getattr(blk, "text_class", "")
        if hasattr(blk, "text") and blk.text:
            entry["fr"] = blk.text
        blocks.append(entry)
    return blocks


def _safe_bbox(blk) -> List[float]:
    xyxy = getattr(blk, "xyxy", None)
    if xyxy is not None:
        return [float(x) for x in xyxy]
    return [0.0, 0.0, 0.0, 0.0]


def payload_to_textblock(
    payload: List[Dict[str, Any]], blk_list: List
) -> List:
    id_map: Dict[str, int] = {}
    for i, blk in enumerate(blk_list):
        block_id = f"block_{i+1}"
        id_map[block_id] = i

    for item in payload:
        raw_id = item.get("id", "")
        block_id = _normalize_id(raw_id)
        if block_id not in id_map:
            block_id = _normalize_id(f"block_{raw_id}")
        if block_id not in id_map:
            continue
        idx = id_map[block_id]
        fr = item.get("fr") or item.get("text") or ""
        it = item.get("it") or item.get("translation") or ""
        if fr and not getattr(blk_list[idx], "text", ""):
            blk_list[idx].text = fr
        if it:
            blk_list[idx].translation = it
    return blk_list


def _normalize_id(raw_id: str) -> str:
    if isinstance(raw_id, int):
        return f"block_{raw_id}"
    raw_id = str(raw_id).strip()
    if raw_id.startswith("block_"):
        return raw_id
    return f"block_{raw_id}"


def blocks_to_json(blk_list: List) -> str:
    blocks = textblock_to_payload(blk_list, mode="translate")
    return json.dumps(blocks, ensure_ascii=False, indent=2)


def json_to_blocks(json_str: str, blk_list: List) -> List:
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return blk_list
        return payload_to_textblock(data, blk_list)
    except (json.JSONDecodeError, TypeError):
        return blk_list