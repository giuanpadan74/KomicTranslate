import json
import time
from typing import Optional, Callable

from .browser_session import BrowserSession
from .pywebview_gvb_mixin import PyWebviewGvbMixin
from .types import VisionFailureReason


GEMINI_URL = "https://gemini.google.com/app?hl=it"


class PyWebviewSession(PyWebviewGvbMixin, BrowserSession):
    def __init__(self, window=None, storage_path: str = ""):
        self._window = window
        self._storage_path = storage_path
        self._ready = False
        self._last_result = ""
        self._expected_count = 0
        self._full_text = ""
        self._start_time = 0.0
        self._timeout = 300

    def is_ready(self) -> bool:
        if not self._window:
            return False
        try:
            ready = self._window.evaluate_js(self._js_check_ready())
            self._ready = bool(ready)
            return self._ready
        except Exception:
            return False

    def _js_check_ready(self) -> str:
        return '''
(function() {
    const input = document.querySelector('textarea') ||
                  document.querySelector('[role="textbox"]') ||
                  document.querySelector('.ql-editor') ||
                  document.querySelector('div[contenteditable="true"]');
    return input !== null && input.getBoundingClientRect().width > 0;
})();
'''

    def inject_prompt(self, prompt: str) -> bool:
        if not self._window:
            print("[PYWEBVIEW DEBUG] Window non disponibile")
            return False
        try:
            self._full_text = prompt
            js = self._js_inject()
            print(f"[PYWEBVIEW DEBUG] Eseguo JS per iniettare prompt...")
            result = self._window.evaluate_js(js)
            print(f"[PYWEBVIEW DEBUG] Risultato evaluate_js: {result}")
            if isinstance(result, bool):
                return result
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    print(f"[PYWEBVIEW DEBUG] Risultato parsato: {parsed}")
                    return parsed.get('success', False)
                except:
                    return bool(result)
            return bool(result)
        except Exception as e:
            print(f"[PYWEBVIEW DEBUG] Errore durante inject_prompt: {e}")
            return False

    def evaluate_js(self, js: str):
        """Proxy per compatibilità con PyWebview API esterna."""
        if not self._window:
            return None
        try:
            return self._window.evaluate_js(js)
        except Exception as e:
            print(f"[PYWEBVIEW DEBUG] evaluate_js error: {e}")
            return None

    def run_js(self, js: str):
        """Alias di evaluate_js per compatibilità con chiamanti che usano run_js()."""
        return self.evaluate_js(js)

    def _js_inject(self) -> str:
        return f'''
(function() {{
    const selectors = [
        'textarea[name="prompt"]',
        'textarea[placeholder*="message" i]',
        'textarea[placeholder*="prompt" i]',
        'textarea',
        'g-ai-input',
        '[contenteditable="true"]',
        '[role="textbox"]',
        '.g-ai-input'
    ];
    let input = null;
    let foundSelector = null;
    for (const sel of selectors) {{
        const el = document.querySelector(sel);
        if (el && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0) {{
            input = el;
            foundSelector = sel;
            break;
        }}
    }}
    if (!input) {{
        return JSON.stringify({{ success: false, reason: 'no_input_found' }});
    }}
    input.focus();
    const targetText = {json.dumps(self._full_text)};
    const tag = (input.tagName || '').toUpperCase();
    const isTextArea = tag === 'TEXTAREA';
    const isContentEditable = input.isContentEditable
                            || (input.getAttribute && input.getAttribute('contenteditable') === 'true');

    if (isTextArea) {{
        // textarea: usa il setter nativo del prototipo (compatibile con framework)
        try {{
            const descriptor = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
            if (descriptor && descriptor.set) {{
                descriptor.set.call(input, targetText);
            }} else {{
                input.value = targetText;
            }}
        }} catch (e) {{
            input.value = targetText;
        }}
    }} else if (isContentEditable) {{
        // contenteditable: execCommand insertText
        try {{
            document.execCommand('selectAll', false, null);
        }} catch(e) {{}}
        try {{
            document.execCommand('delete', false, null);
        }} catch(e) {{}}
        try {{
            document.execCommand('insertText', false, targetText);
        }} catch(e) {{
            input.innerText = targetText;
        }}
    }} else {{
        try {{ input.value = targetText; }} catch(e) {{ input.textContent = targetText; }}
    }}

    // Dispatch eventi
    try {{ input.dispatchEvent(new Event('input', {{ bubbles: true }})); }} catch(e) {{}}
    try {{ input.dispatchEvent(new Event('change', {{ bubbles: true }})); }} catch(e) {{}}

    return JSON.stringify({{ success: true, selector: foundSelector, tag: tag }});
}})();
'''

    def click_send(self) -> bool:
        if not self._window:
            return False
        try:
            js = self._js_wait_send()
            return bool(self._window.evaluate_js(js))
        except Exception:
            return False

    def _js_wait_send(self) -> str:
        return '''
(function() {
    const btn = document.querySelector('button[aria-label*="Invia"]') ||
                document.querySelector('button[aria-label*="Send"]') ||
                document.querySelector('button[aria-label*="Run"]') ||
                document.querySelector('[data-testid="send-button"]');
    if (btn && !btn.disabled && btn.getBoundingClientRect().width > 0 && btn.getBoundingClientRect().height > 0) {
        btn.click();
        return true;
    }
    return false;
})();
'''

    def _js_extract(self) -> str:
        return '''
(function() {
    const codeBlocks = document.querySelectorAll('pre code, pre');
    for (const block of codeBlocks) {
        const text = block.textContent || '';
        if (text.includes('"id"') || text.includes("'id'") || text.includes('block_')) {
            return text;
        }
    }
    const containers = document.querySelectorAll(
        '[data-testid="response-container"]', '.response-block', 'model-response'
    );
    if (containers.length > 0) {
        return containers[containers.length - 1].textContent || '';
    }
    return '';
})();
'''

    def wait_response(self, timeout_seconds: int) -> str:
        self._start_time = time.time()
        self._timeout = timeout_seconds
        while time.time() - self._start_time < timeout_seconds:
            if not self._window:
                break
            try:
                text = self._window.evaluate_js(self._js_extract())
                if text and len(text) > 10 and ("block_" in text or '"id"' in text):
                    self._last_result = text
                    return text
            except Exception:
                pass
            time.sleep(1)
        return self._last_result

    def copy_response(self) -> bool:
        if not self._window:
            return False
        try:
            js = '''
(function() {
    const selectors = [
        'button[aria-label*="Copia risposta"]',
        'button[aria-label*="Copy response"]',
        'button[aria-label*="Copia"]',
        'button[aria-label*="Copy"]',
    ];
    for (const sel of selectors) {
        const btn = document.querySelector(sel);
        if (btn && !btn.disabled && btn.getBoundingClientRect().width > 0 && btn.getBoundingClientRect().height > 0) {
            btn.scrollIntoView({ block: 'center' });
            btn.click();
            return true;
        }
    }
    return false;
})();
'''
            return bool(self._window.evaluate_js(js))
        except Exception:
            return False

    def get_clipboard_text(self) -> Optional[str]:
        try:
            import webview
            return webview.windows[0].clipboard.get() if webview.windows else None
        except Exception:
            return None

    def reload(self) -> None:
        if self._window:
            self._window.load_url(GEMINI_URL)
            time.sleep(2)

    def close(self) -> None:
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
