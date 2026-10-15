"""
Filtro post-OCR per caratteri CJK in lingue non-asiatiche.

Quando la lingua origine è europea, i caratteri CJK rilevati dall'OCR
sono quasi certamente falsi positivi (PP-OCR addestrato su CJK).
"""

import re

# CJK: ideogrammi, hiragana, katakana, hangul
_CJK_RE = re.compile(
    "["
    "\u2e80-\u2eff\u2f00-\u2fdf"  # CJK Radicals, Kangxi Radicals
    "\u3040-\u309f"                # Hiragana
    "\u30a0-\u30ff"                # Katakana
    "\u3100-\u312f"                # Bopomofo
    "\u3130-\u318f"                # Hangul Compatibility Jamo
    "\u3200-\u32ff"                # Enclosed CJK Letters
    "\u3400-\u4dbf"                # CJK Extension A
    "\u4e00-\u9fff"                # CJK Unified Ideographs
    "\ua960-\ua97c"                # Hangul Jamo Extended-A
    "\uac00-\ud7af"                # Hangul Syllables
    "\ud7b0-\ud7ff"                # Hangul Jamo Extended-B
    "\uf900-\ufaff"                # CJK Compatibility Ideographs
    "\U00020000-\U0002a6df"        # CJK Extension B
    "\U0002a700-\U0002b73f"        # CJK Extension C
    "\U0002b740-\U0002b81f"        # CJK Extension D
    "]"
)

# Lingue CJK dove il testo CJK è valido
_CJK_LANGUAGES = frozenset({
    "Japanese", "Korean", "Chinese",
    "Simplified Chinese", "Traditional Chinese",
})

CJK_MIN_RATIO = 0.8


def is_cjk_dominant(text):
    """True se >= 80% dei caratteri non-whitespace sono CJK."""
    if not text:
        return False
    cleaned = re.sub(r"\s+", "", text)
    if not cleaned:
        return False
    cjk_count = len(_CJK_RE.findall(cleaned))
    return cjk_count / len(cleaned) >= CJK_MIN_RATIO


def filter_cjk_for_non_asian(blocks, source_lang_english):
    """
    Rimuove blocchi con testo prevalentemente CJK quando la lingua
    origine non è asiatica.
    """
    if source_lang_english in _CJK_LANGUAGES:
        return blocks

    kept = []
    removed = 0
    for blk in blocks:
        text = getattr(blk, "text", "") or ""
        if is_cjk_dominant(text):
            removed += 1
            continue
        kept.append(blk)

    if removed > 0:
        print(
            f"[CJK_FILTER] Rimossi {removed} blocchi con testo CJK "
            f"(lingua: {source_lang_english})"
        )

    return kept
