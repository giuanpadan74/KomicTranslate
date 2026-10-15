"""
Helper per la rilevazione / recupero dei blocchi di testo per la sbianchetta.
"""
import logging
import os

from modules.utils.textblock import sort_blk_list

logger = logging.getLogger(__name__)


def _ensure_image_state(main_page, image_path: str) -> None:
    if image_path not in main_page.image_states:
        main_page.image_states[image_path] = {
            "viewer_state": {},
            "source_lang": main_page.s_combo.currentText(),
            "target_lang": main_page.t_combo.currentText(),
        }


def get_blk_list(pipeline, image, image_path, source_lang,
                 skip_detection, existing_blk_list):
    """Recupera (o rileva) i blocchi di testo per l'immagine corrente."""
    source_lang_english = pipeline.main_page.lang_mapping.get(
        source_lang, source_lang
    )
    if pipeline._should_skip_text_detection(
        image_path, skip_detection, existing_blk_list
    ):
        blk_list = pipeline._get_existing_blocks(
            image_path, existing_blk_list, apply_filter=False
        )
        logger.info(
            "[SBIANCHETTA] Utilizzando %s caselle esistenti per %s",
            len(blk_list), os.path.basename(image_path),
        )
        return blk_list, source_lang_english

    blk_list = pipeline._perform_text_detection(image)
    if not blk_list:
        logger.info(
            "[SBIANCHETTA] Nessun blocco rilevato in: %s", image_path
        )
        return [], source_lang_english

    rtl = source_lang_english == "Japanese"
    blk_list = sort_blk_list(blk_list, rtl)
    logger.info(
        "[SBIANCHETTA] Rilevamento completato per %s - trovati %s blocchi",
        os.path.basename(image_path), len(blk_list),
    )
    return blk_list, source_lang_english