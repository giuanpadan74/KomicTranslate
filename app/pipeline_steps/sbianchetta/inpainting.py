"""
Gestione inpainter e step di inpainting per la sbianchetta.
"""
import logging

import cv2

from modules.utils.pipeline_utils import generate_mask, get_config

logger = logging.getLogger(__name__)


def ensure_inpainter(pipeline, settings_page) -> None:
    """Inizializza l'inpainter_cache condiviso con la pipeline principale."""
    if pipeline.inpainter_cache is not None:
        return
    from modules.inpainting.factory import InpainterFactory
    from modules.inpainting.lama import LaMa

    inpainter_key = settings_page.get_tool_selection("inpainter")
    device = "cuda" if settings_page.is_gpu_enabled() else "cpu"
    try:
        pipeline.inpainter_cache = InpainterFactory.get_inpainter(
            inpainter_key, device
        )
        logger.info("[SBIANCHETTA] Using inpainter %s", inpainter_key)
    except Exception as exc:
        logger.warning(
            "[SBIANCHETTA] Fallback a LaMa dopo errore su %s: %s",
            inpainter_key, exc,
        )
        pipeline.inpainter_cache = LaMa(device)
        inpainter_key = "lama"
    pipeline.cached_inpainter_key = inpainter_key


def inpaint(pipeline, image, blk_list, settings_page):
    """Genera mask e invoca l'inpainter_cache."""
    config = get_config(
        settings_page,
        blk_list=blk_list,
        original_size=image.shape[:2],
    )
    mask = generate_mask(image, blk_list)
    inpaint_input_img = pipeline.inpainter_cache(image, mask, config)
    return cv2.convertScaleAbs(inpaint_input_img)