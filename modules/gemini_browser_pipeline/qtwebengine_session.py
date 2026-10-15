import time
from typing import Optional, Callable
from .browser_session import BrowserSession
from .types import VisionFailureReason


GEMINI_URL = "https://gemini.google.com/app?hl=it"

JS_CHECK_READY = '''
(function() {
    const input = document.querySelector('textarea') ||
                  document.querySelector('[role="textbox"]') ||
                  document.querySelector('.ql-editor') ||
                  document.querySelector('div[contenteditable="true"]');
    return input !== null && input.getBoundingClientRect().width > 0;
})();
'''

JS_INJECT = '''
(function() {
    const input = document.querySelector('textarea') ||
                  document.querySelector('[role="textbox"]') ||
                  document.querySelector('.ql-editor') ||
                  document.querySelector('div[contenteditable="true"]');
    if (input) {
        input.focus();
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(input, %s);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }
    return false;
})();
'''

JS_WAIT_SEND = '''
(function() {
    const btn = document.querySelector('button[aria-label*="Invia"]') ||
                document.querySelector('button[aria-label*="Send"]') ||
                document.querySelector('button[aria-label*="Run"]') ||
                document.querySelector('[data-testid="send-button"]');
    if (btn && !btn.disabled && btn.offsetParent !== null) {
        btn.click();
        return true;
    }
    return false;
})();
'''

JS_EXTRACT = '''
(function() {
    const codeBlocks = document.querySelectorAll('pre code, pre');
    for (const block of codeBlocks) {
        const text = block.textContent || '';
        if (text.includes('"id"') || text.includes("'id'") || text.includes('block_')) {
            return text;
        }
    }
    const containers = document.querySelectorAll(
        '[data-testid="response-container"], .response-block, model-response'
    );
    if (containers.length > 0) {
        const last = containers[containers.length - 1];
        return last.textContent || '';
    }
    return '';
})();
'''

JS_COPY_RESPONSE = '''
(function() {
    const selectors = [
        'button[aria-label*="Copia risposta"]',
        'button[aria-label*="Copy response"]',
        'button[aria-label*="Copia"]',
        'button[aria-label*="Copy"]',
    ];
    for (const sel of selectors) {
        const btn = document.querySelector(sel);
        if (btn && !btn.disabled && btn.offsetParent !== null) {
            btn.scrollIntoView({ block: 'center' });
            btn.click();
            return true;
        }
    }
    return false;
})();
'''


class QtWebEngineSession(BrowserSession):
    def __init__(self, webview, url: str = GEMINI_URL):
        self._webview = webview
        self._url = url
        self._ready = False
        self._pending_result = ""
        self._error: Optional[str] = None

    def is_ready(self) -> bool:
        try:
            result = self._webview.page().runJavaScript(JS_CHECK_READY)
            self._ready = bool(result)
            return self._ready
        except Exception:
            return False

    def inject_prompt(self, prompt: str) -> bool:
        try:
            js = JS_INJECT % repr(prompt)
            result = self._webview.page().runJavaScript(js)
            return bool(result)
        except Exception:
            return False

    def click_send(self) -> bool:
        try:
            result = self._webview.page().runJavaScript(JS_WAIT_SEND)
            return bool(result)
        except Exception:
            return False

    def wait_response(self, timeout_seconds: int) -> str:
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                text = self._webview.page().runJavaScript(JS_EXTRACT)
                if text and len(text) > 10 and ("block_" in text or '"id"' in text):
                    self._pending_result = text
                    return text
            except Exception:
                pass
            time.sleep(1)
        self._error = "Timeout waiting for response"
        return self._pending_result

    def copy_response(self) -> bool:
        try:
            return bool(self._webview.page().runJavaScript(JS_COPY_RESPONSE))
        except Exception:
            return False

    def get_clipboard_text(self) -> Optional[str]:
        try:
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            return clipboard.text()
        except Exception:
            return None

    def reload(self) -> None:
        self._webview.setUrl(self._url)
        time.sleep(2)

    def close(self) -> None:
        pass