from typing import List, Callable, Optional
from .types import VisionFailureReason, VisionResult, VisionJob
from .retry_policy import RetryPolicy


FallbackLevel = int


class FallbackChain:
    def __init__(self):
        self._handlers: List[Callable[[VisionJob, Exception], Optional[VisionResult]]] = []
        self._policy = RetryPolicy.default()

    def add_handler(
        self,
        handler: Callable[[VisionJob, Exception], Optional[VisionResult]],
    ) -> "FallbackChain":
        self._handlers.append(handler)
        return self

    def execute(self, job: VisionJob, primary_error: Exception) -> Optional[VisionResult]:
        for handler in self._handlers:
            try:
                result = handler(job, primary_error)
                if result and result.success:
                    return result
            except Exception:
                continue
        return None


def make_clipboard_fallback(job: VisionJob, error: Exception) -> Optional[VisionResult]:
    try:
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text and "block_" in text:
            return _text_to_result(text, job)
    except Exception:
        pass
    return None


def make_reload_fallback(job: VisionJob, error: Exception) -> Optional[VisionResult]:
    return None


def _text_to_result(text: str, job: VisionJob):
    from .result_parser import parse_and_validate

    data, reason = parse_and_validate(text, len(job.blk_list))
    if data:
        from .block_payload import payload_to_textblock
        blk_list = payload_to_textblock(data, list(job.blk_list))
        return VisionResult(
            success=True,
            translations_json={item["id"]: item.get("it", "") for item in data if item.get("it")},
            recognized_text_json={item["id"]: item.get("fr", "") for item in data if item.get("fr")},
            updated_blk_list=blk_list,
            blocks_found=len(data),
            blocks_expected=len(job.blk_list),
        )
    return None


def build_fallback_chain() -> FallbackChain:
    chain = FallbackChain()
    chain.add_handler(make_clipboard_fallback)
    chain.add_handler(make_reload_fallback)
    return chain