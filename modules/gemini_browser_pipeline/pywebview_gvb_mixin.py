import json

from modules.gemini_scripts_image import get_js_get_image_upload_state, get_js_paste_image
from modules.gvb_scripts import get_js_attach_and_upload_image, get_js_focus_composer


class PyWebviewGvbMixin:
    def run_js(self, script: str):
        if not self._window:
            return None
        try:
            return self._window.evaluate_js(script)
        except Exception:
            return None

    def focus_composer(self):
        return self.run_js(get_js_focus_composer())

    def attach_image_file(self, image_path: str):
        return self.run_js(get_js_attach_and_upload_image(image_path))

    def paste_image_js(self):
        return self.run_js(get_js_paste_image())

    def get_image_upload_state(self):
        raw = self.run_js(get_js_get_image_upload_state())
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {'status': raw}
        return {'status': 'error'}
