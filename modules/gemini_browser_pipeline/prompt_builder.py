from typing import List, Dict, Any
from .types import GeminiBrowserMode


SYSTEM_INSTRUCTION = (
    "Sei un traduttore esperto di fumetti franco-belgi. "
    "Mantieni il tono, i giochi di parole e le espressioni idiomatiche. "
    "Restituisci SOLO il JSON richiesto, senza testo aggiuntivo."
)

JSON_FORMAT = (
    'Restituisci i dati esclusivamente in questo formato JSON: '
    '[{"id": "block_1", "fr": "...", "it": "..."}]'
)


def build_vision_translate_prompt(
    blocks: List[Dict[str, Any]],
    source_lang: str = "fr",
    target_lang: str = "it",
    extra_context: str = "",
) -> str:
    lines = [
        SYSTEM_INSTRUCTION,
        "",
        f"Traduci dal {source_lang} al {target_lang}.",
        "",
        "Blocchi di testo da tradurre:",
    ]
    for blk in blocks:
        block_id = blk.get("id", "?")
        text = blk.get("fr") or blk.get("text") or ""
        lines.append(f"  {block_id}: {text}")
    if extra_context:
        lines.append("")
        lines.append(f"Contesto aggiuntivo: {extra_context}")
    lines.append("")
    lines.append(JSON_FORMAT)
    return "\n".join(lines)


def build_vision_ocr_translate_prompt(
    blocks: List[Dict[str, Any]],
    source_lang: str = "fr",
    target_lang: str = "it",
    extra_context: str = "",
) -> str:
    lines = [
        SYSTEM_INSTRUCTION,
        "",
        f"Analizza questa tavola di fumetto. Identifica tutti i balloon e i box di testo. "
        f"Per ciascuno restituisci il testo originale ({source_lang}) e la migliore "
        f"traduzione in {target_lang}, mantenendo il tono e i giochi di parole.",
        "",
        "Riferimento blocchi attesi (usa questi ID come riferimento):",
    ]
    for blk in blocks:
        block_id = blk.get("id", "?")
        bbox = blk.get("bbox", [])
        text_class = blk.get("text_class", "")
        text = blk.get("fr") or blk.get("text") or ""
        if bbox:
            lines.append(f"  {block_id} [area: {bbox[0]:.0f},{bbox[1]:.0f}-{bbox[2]:.0f},{bbox[3]:.0f}] {text_class}: {text}")
        else:
            lines.append(f"  {block_id} {text_class}: {text}")
    if extra_context:
        lines.append("")
        lines.append(f"Contesto aggiuntivo: {extra_context}")
    lines.append("")
    lines.append(JSON_FORMAT)
    return "\n".join(lines)


def build_prompt(
    blocks: List[Dict[str, Any]],
    mode: GeminiBrowserMode,
    source_lang: str = "fr",
    target_lang: str = "it",
    extra_context: str = "",
) -> str:
    if mode == GeminiBrowserMode.VISION_OCR_TRANSLATE:
        return build_vision_ocr_translate_prompt(blocks, source_lang, target_lang, extra_context)
    return build_vision_translate_prompt(blocks, source_lang, target_lang, extra_context)