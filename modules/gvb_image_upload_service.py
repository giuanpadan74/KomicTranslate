import time

from modules.gemini_scripts_image import get_js_paste_image
from modules.gvb_image_clipboard import copy_image_file_to_windows_clipboard
from modules.gvb_image_upload_state import read_image_upload_state
from modules.gvb_keyboard import focus_and_paste_with_retry
from modules.gvb_scripts import get_js_attach_and_upload_image, get_js_focus_composer, get_js_click_send_button


class GvbImageUploadService:
    def __init__(self, poll_interval: float = 0.3, timeout_seconds: float = 4.0):
        self.poll_interval = poll_interval
        self.timeout_seconds = timeout_seconds

    def attach_image(self, window, image_path: str) -> dict:
        if not window or not image_path:
            return {'success': False, 'method': 'none', 'status': 'error'}
        # 1) Clipboard paste (Ctrl+V Windows) — la più veloce e affidabile (come prima)
        outcome = self._try_clipboard_paste(window, image_path)
        if outcome['success']:
            return outcome
        # 2) DOM upload (click + → upload file)
        outcome = self._try_dom_upload(window, image_path)
        if outcome['success']:
            return outcome
        # 3) JS paste (clipboard API)
        outcome = self._try_js_paste(window)
        return outcome

    def _try_dom_upload(self, window, image_path: str) -> dict:
        info = self._evaluate(window, get_js_attach_and_upload_image(image_path))
        if self._wait_until_ready(window):
            return {'success': True, 'method': 'dom_file_input', 'status': 'loaded', 'details': info}
        return {'success': False, 'method': 'dom_file_input', 'status': 'error', 'details': info}

    def _try_clipboard_paste(self, window, image_path: str) -> dict:
        if not copy_image_file_to_windows_clipboard(image_path):
            return {'success': False, 'method': 'clipboard', 'status': 'error'}
        self._evaluate(window, get_js_focus_composer())
        time.sleep(0.2)
        focus_and_paste_with_retry(window, attempts=3, delay=0.4)
        if self._wait_until_ready(window):
            return {'success': True, 'method': 'clipboard', 'status': 'loaded'}
        return {'success': False, 'method': 'clipboard', 'status': 'error'}

    def _try_js_paste(self, window) -> dict:
        self._evaluate(window, get_js_focus_composer())
        pasted = self._evaluate(window, get_js_paste_image())
        if pasted and self._wait_until_ready(window):
            return {'success': True, 'method': 'js_paste', 'status': 'loaded'}
        return {'success': False, 'method': 'js_paste', 'status': 'error'}

    def _wait_until_ready(self, window) -> bool:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            state = read_image_upload_state(window)
            if state.get('status') == 'loaded':
                return True
            if state.get('status') == 'error':
                return False
            time.sleep(self.poll_interval)
        return False

    def _evaluate(self, window, script: str):
        if hasattr(window, 'evaluate_js'):
            try:
                return window.evaluate_js(script)
            except Exception:
                return None
        try:
            return window.run_js(script)
        except Exception:
            return None

    def click_send_button(self, window) -> bool:
        """Clicca il pulsante Invia/Send dopo che l'immagine è stata caricata."""
        result = self._evaluate(window, get_js_click_send_button())
        return result is True
