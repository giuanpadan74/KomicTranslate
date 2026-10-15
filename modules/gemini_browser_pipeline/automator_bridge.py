import json
import logging
from typing import Optional, Dict, Any, List
from .types import VisionJob, VisionResult, VisionFailureReason, GeminiBrowserMode
from .pipeline import GeminiVisionToTextPipeline
from .browser_session import BrowserSession


logger = logging.getLogger(__name__)


def translate_blocks_automator(
    blk_list: List[Any],
    image_path: str,
    source_lang: str,
    target_lang: str,
    main_page,
    max_retries: int = 3,
) -> Optional[str]:
    import time
    from modules.utils.textblock import sort_blk_list

    logger.info(f"[VisionBridge] Starting automator translation for {image_path}")

    if not blk_list:
        return None

    blk_list = sort_blk_list(blk_list, right_to_left=False)
    blocks = []
    for i, blk in enumerate(blk_list):
        text = (getattr(blk, 'text', '') or "").replace('"', '')
        blocks.append({'id': f'block_{i+1}', 'text': text})

    full_text = ""
    for i, blk in enumerate(blk_list):
        text = (getattr(blk, 'text', '') or "").replace('"', '')
        full_text += f"block_{i+1}: {text}\n\n"

    full_text += "\n" + "=" * 50 + "\n"
    full_text += "TRANSLATION PROMPT (System Instruction):\n"
    full_text += "=" * 50 + "\n\n"
    full_text += _build_prompt(target_lang)

    result_container = {'json_result': None, 'error': None}
    blocks_json = json.dumps(blocks)

    for attempt in range(max_retries):
        if attempt > 0:
            delay = 2 * (2 ** (attempt - 1))
            logger.info(f"[VisionBridge] Retry {attempt}/{max_retries} after {delay}s")
            time.sleep(delay)

        try:
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            main_page._gemini_result_container = result_container

            QMetaObject.invokeMethod(
                main_page,
                "_run_gemini_automation_sync",
                Qt.BlockingQueuedConnection,
                Q_ARG(str, blocks_json),
                Q_ARG(str, full_text),
                Q_ARG(int, len(blocks)),
                Q_ARG(str, source_lang),
                Q_ARG(str, target_lang),
            )

            if result_container.get('json_result'):
                return result_container['json_result']
            if result_container.get('error'):
                logger.warning(f"[VisionBridge] Attempt {attempt + 1} error: {result_container['error']}")
        except Exception as e:
            logger.warning(f"[VisionBridge] Attempt {attempt + 1} exception: {e}")
            if attempt < max_retries - 1:
                continue
            return None

    logger.error(f"[VisionBridge] All {max_retries} attempts failed")
    return None


def _build_prompt(target_lang: str) -> str:
    return (
        "Sei un traduttore esperto di fumetti. Traduci mantenendo il tono, i giochi di parole e le espressioni idiomatiche. "
        f"Restituisci SOLO un blocco JSON con la traduzione in {target_lang} per ogni block_N presente. "
        'Formato: [{"id": "block_1", "it": "traduzione..."}]'
    )