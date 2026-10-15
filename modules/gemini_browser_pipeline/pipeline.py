import time
import logging
from typing import Optional, Callable
from .types import VisionJob, VisionResult, VisionFailureReason, GeminiBrowserMode
from .browser_session import BrowserSession
from .prompt_builder import build_prompt
from .result_parser import parse_and_validate
from .block_payload import textblock_to_payload, payload_to_textblock
from .fallbacks import FallbackChain, build_fallback_chain
from .retry_policy import RetryPolicy, get_dynamic_timeout


logger = logging.getLogger(__name__)


class GeminiVisionToTextPipeline:
    def __init__(
        self,
        session: BrowserSession,
        fallback_chain: Optional[FallbackChain] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        self._session = session
        self._fallback_chain = fallback_chain or build_fallback_chain()
        self._retry_policy = retry_policy or RetryPolicy.default()

    def run(self, job: VisionJob) -> VisionResult:
        start = time.time()
        blocks = textblock_to_payload(job.blk_list, mode="translate")
        prompt = build_prompt(
            blocks,
            job.mode,
            job.source_lang,
            job.target_lang,
            job.extra_context,
        )
        raw_result = self._execute_with_retry(job, prompt)
        if not raw_result:
            fallback = self._fallback_chain.execute(job, Exception("No response"))
            if fallback:
                return fallback
            return VisionResult(
                success=False,
                failure_reason=VisionFailureReason.RESPONSE_TIMEOUT,
                error_message="Timeout and fallback failed",
                elapsed_seconds=time.time() - start,
            )
        data, reason = parse_and_validate(raw_result, len(job.blk_list))
        if data is None:
            fallback = self._fallback_chain.execute(job, Exception(str(reason)))
            if fallback:
                return fallback
            return VisionResult(
                success=False,
                failure_reason=reason,
                error_message=f"Parse failed: {reason.value}",
                elapsed_seconds=time.time() - start,
            )
        updated = payload_to_textblock(list(data), list(job.blk_list))
        translations = {item["id"]: item.get("it", "") for item in data if item.get("it")}
        recognized = {item["id"]: item.get("fr", "") for item in data if item.get("fr")}
        return VisionResult(
            success=True,
            translations_json=translations,
            recognized_text_json=recognized,
            updated_blk_list=updated,
            blocks_found=len(data),
            blocks_expected=len(job.blk_list),
            elapsed_seconds=time.time() - start,
        )

    def _execute_with_retry(self, job: VisionJob, prompt: str) -> Optional[str]:
        timeout = get_dynamic_timeout(len(job.blk_list))
        for attempt in range(self._retry_policy.config.max_retries + 1):
            try:
                self._session.reload()
                if not self._session.is_ready():
                    time.sleep(3)
                    if not self._session.is_ready() and attempt > 0:
                        continue
                if not self._session.inject_prompt(prompt):
                    continue
                if not self._session.click_send():
                    continue
                result = self._session.wait_response(timeout)
                if result and ("block_" in result or '"id"' in result):
                    return result
                self._session.copy_response()
                clipboard = self._session.get_clipboard_text()
                if clipboard and ("block_" in clipboard or '"id"' in clipboard):
                    return clipboard
            except Exception as e:
                logger.warning(f"[VisionPipeline] Attempt {attempt + 1} failed: {e}")
                if attempt < self._retry_policy.config.max_retries:
                    self._session.reload()
                    time.sleep(2)
        return None