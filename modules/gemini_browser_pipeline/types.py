from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GeminiBrowserMode(Enum):
    VISION_TRANSLATE = "vision_translate"
    VISION_OCR_TRANSLATE = "vision_ocr_translate"


class VisionFailureReason(Enum):
    BROWSER_NOT_READY = "browser_not_ready"
    UPLOAD_FAILED = "upload_failed"
    PROMPT_INJECT_FAILED = "prompt_inject_failed"
    SEND_FAILED = "send_failed"
    RESPONSE_TIMEOUT = "response_timeout"
    DOM_CHANGED = "dom_changed"
    JSON_NOT_FOUND = "json_not_found"
    JSON_INCOMPLETE = "json_incomplete"
    JSON_PARSE_ERROR = "json_parse_error"
    COPY_BUTTON_NOT_FOUND = "copy_button_not_found"
    CLIPBOARD_EMPTY = "clipboard_empty"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class VisionJob:
    image_path: str
    blk_list: list
    source_lang: str = "fr"
    target_lang: str = "it"
    mode: GeminiBrowserMode = GeminiBrowserMode.VISION_TRANSLATE
    extra_context: str = ""
    use_collage: bool = True
    timeout_seconds: int = 240


@dataclass
class VisionBlockResult:
    block_id: str
    fr: str = ""
    it: str = ""
    note: Optional[str] = None


@dataclass
class VisionResult:
    success: bool
    translations_json: dict = field(default_factory=dict)
    recognized_text_json: dict = field(default_factory=dict)
    updated_blk_list: list = field(default_factory=list)
    failure_reason: Optional[VisionFailureReason] = None
    error_message: str = ""
    elapsed_seconds: float = 0.0
    blocks_found: int = 0
    blocks_expected: int = 0