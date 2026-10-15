import json
import time
import logging
from typing import Optional, Dict, Any, List
from .types import VisionJob, VisionResult, VisionFailureReason, GeminiBrowserMode
from .pipeline import GeminiVisionToTextPipeline
from .browser_session import BrowserSession


logger = logging.getLogger(__name__)


def create_vision_service(
    session: BrowserSession,
) -> GeminiVisionToTextPipeline:
    from .fallbacks import build_fallback_chain
    return GeminiVisionToTextPipeline(session=session, fallback_chain=build_fallback_chain())


def run_vision_translate_sync(
    blk_list: List[Any],
    image_path: str,
    source_lang: str,
    target_lang: str,
    webview=None,
    session: Optional[BrowserSession] = None,
    mode: GeminiBrowserMode = GeminiBrowserMode.VISION_TRANSLATE,
    result_container: Optional[Dict] = None,
) -> Optional[VisionResult]:
    if session is None and webview is None:
        logger.error("[VisionService] No webview or session provided")
        return None

    if session is None:
        from .qtwebengine_session import QtWebEngineSession
        session = QtWebEngineSession(webview)

    pipeline = create_vision_service(session)
    job = VisionJob(
        image_path=image_path,
        blk_list=blk_list,
        source_lang=source_lang,
        target_lang=target_lang,
        mode=mode,
    )
    result = pipeline.run(job)

    if result_container is not None:
        if result.success:
            result_container["json_result"] = json.dumps(
                result.translations_json, ensure_ascii=False, indent=2
            )
        elif result.failure_reason:
            result_container["error"] = Exception(result.failure_reason.value)

    return result


def translate_blocks_legacy(
    blocks: List[Dict[str, Any]],
    full_text: str,
    expected_count: int,
    source_lang: str,
    target_lang: str,
    webview=None,
    session: Optional[BrowserSession] = None,
) -> Dict[str, str]:
    blk_list = []
    for i, b in enumerate(blocks):
        class FakeBlock:
            def __init__(self, idx, text):
                self.text = text
                self.translation = ""
                self._idx = idx
        blk_list.append(FakeBlock(i, b.get("text", "")))

    result = run_vision_translate_sync(
        blk_list=blk_list,
        image_path="legacy",
        source_lang=source_lang,
        target_lang=target_lang,
        webview=webview,
        session=session,
        result_container={},
    )

    if result and result.success:
        return result.translations_json

    logger.warning("[VisionService] Legacy translation failed, returning empty dict")
    return {}