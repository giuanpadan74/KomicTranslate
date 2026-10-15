import json

from modules.gemini_scripts_image import get_js_get_image_upload_state


def read_image_upload_state(window) -> dict:
    if window is None:
        return {'status': 'error', 'detail': 'missing_window'}
    try:
        raw = window.evaluate_js(get_js_get_image_upload_state())
    except Exception as exc:
        return {'status': 'error', 'detail': str(exc)}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {'status': raw}
    return {'status': 'error', 'detail': repr(raw)}
