"""
Filtro pre-OCR: verifica il contenuto testuale dei blocchi rilevati.

Dopo l'esecuzione dell'OCR, rimuove:
- Blocchi con testo vuoto o solo whitespace (falsi positivi)
- Blocchi contenenti solo numeri < 999 (numeri di pagina)
"""

import re

MAX_PAGE_NUMBER = 999
PURE_NUMBER_RE = re.compile(r"^\s*(\d{1,4})\s*$")


def filter_blocks_by_text(blocks):
    """
    Filtra blocchi in base al testo OCR rilevato.

    Args:
        blocks: lista di TextBlock con text già popolato dall'OCR

    Returns:
        lista filtrata di blocchi mantenuti
    """
    if not blocks:
        return blocks

    kept = []
    removed_empty = 0
    removed_number = 0

    for blk in blocks:
        text = getattr(blk, "text", "") or ""
        cleaned = text.strip()

        # Rimuovi blocchi vuoti o solo whitespace
        if not cleaned:
            removed_empty += 1
            continue

        # Rimuovi blocchi con solo numeri < 999 (numeri di pagina)
        match = PURE_NUMBER_RE.match(cleaned)
        if match:
            num = int(match.group(1))
            if num < MAX_PAGE_NUMBER:
                removed_number += 1
                continue

        kept.append(blk)

    total_removed = removed_empty + removed_number
    if total_removed > 0:
        print(
            f"[PRE_OCR_FILTER] Rimossi {total_removed} blocchi "
            f"({removed_empty} vuoti, {removed_number} numeri pagina)"
        )

    return kept
