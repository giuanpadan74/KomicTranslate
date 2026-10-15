import ctypes
from ctypes import wintypes
import time


def _enum_visible_windows():
    user32 = ctypes.windll.user32
    results = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, lParam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if title:
            results.append((int(hwnd), title))
        return True

    user32.EnumWindows(enum_proc, 0)
    return results


def send_ctrl_v_to_window(hwnd):
    """Simula Ctrl+V per incollare dalla clipboard a livello di sistema."""
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 5)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        
        user32.keybd_event(0x11, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(ord('V'), 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(ord('V'), 0, 2, 0)
        time.sleep(0.05)
        user32.keybd_event(0x11, 0, 2, 0)
        
        return True
    except Exception as e:
        print(f"[GVB] Errore send_ctrl_v: {e}")
        return False


def get_window_handle(webview):
    """Ottiene l'handle HWND di una finestra pywebview/Edge o fallback per titolo."""
    try:
        if hasattr(webview, 'title') and callable(getattr(webview, 'title', None)):
            title = webview.title()
        else:
            title = getattr(webview, 'title', None)

        if hasattr(webview, 'winId'):
            return int(webview.winId())

        if title:
            lowered = str(title).strip().lower()
            for hwnd, window_title in _enum_visible_windows():
                if lowered and lowered in window_title.lower():
                    return hwnd

        for hwnd, window_title in _enum_visible_windows():
            if 'gemini auto-translator' in window_title.lower() or 'gemini' in window_title.lower():
                return hwnd

        return 0
    except Exception as e:
        print(f"[GVB] Errore get HWND: {e}")
        return 0


def focus_and_paste(webview) -> bool:
    """Mette a fuoco la webview e simula Ctrl+V."""
    hwnd = get_window_handle(webview)
    if hwnd == 0:
        print("[GVB] Impossibile ottenere HWND")
        return False
    
    return send_ctrl_v_to_window(hwnd)


def focus_and_paste_with_retry(webview, attempts: int = 8, delay: float = 0.6) -> bool:
    """Prova più volte a mettere a fuoco la webview e incollare dalla clipboard."""
    for _ in range(max(1, attempts)):
        if focus_and_paste(webview):
            return True
        time.sleep(max(0.1, delay))
    return False
