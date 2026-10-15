"""
browser_injector.py
------------------
Inietta cookie di autenticazione nei browser embedded.
"""

import os
import time
import webview
from typing import Optional, Callable


class PyWebviewCookieInjector:
    """
    Iniettore cookie per pywebview.
    Usa JavaScript injection per impostare cookie prima del login.
    """

    def __init__(self):
        self.window: Optional[webview.Window] = None
        self._inject_ready = False

    def create_cookie_injection_js(self, cookies: dict) -> str:
        """
        Genera codice JavaScript per impostare cookie.

        Args:
            cookies: Dict con {cookie_name: cookie_value}

        Returns:
            Stringa JavaScript per l'injection
        """
        cookie_js_parts = []
        for name, value in cookies.items():
            if value:
                secure = "true" if "Secure" in name else "false"
                cookie_js_parts.append(
                    f"document.cookie = '{name}={value}; path=/; domain=.google.com; secure={secure}; samesite=none';"
                )

        return "\n".join(cookie_js_parts)

    def create_html_bridge(self, cookies: dict, target_url: str) -> str:
        """
        Crea una pagina HTML locale che imposta i cookie e reindirizza.

        Args:
            cookies: Dict con cookie da impostare
            target_url: URL target Gemini

        Returns:
            HTML string
        """
        cookie_lines = []
        for name, value in cookies.items():
            if value:
                cookie_lines.append(
                    f"document.cookie = '{name}={value}; path=/; domain=.google.com; secure; samesite=none';"
                )

        cookie_script = "\n".join(cookie_lines)

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Gemini Auth</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: #1a1a2e;
            color: white;
        }}
        .status {{
            text-align: center;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            border: 4px solid #333;
            border-top: 4px solid #4fc3f7;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="status">
        <p>Preparazione sessione Gemini...</p>
        <div class="spinner"></div>
        <p id="msg">Injecting cookies</p>
    </div>
    <script>
        {cookie_script}
        console.log("Cookies injected, redirecting to Gemini...");
        document.getElementById("msg").textContent = "Reindirizzamento...";
        window.location.href = "{target_url}";
    </script>
</body>
</html>
"""
        return html

    def inject_cookies_to_webview(self, cookies: dict) -> bool:
        """
        Iniett i cookie in una finestra pywebview esistente.

        Args:
            cookies: Dict con cookie da iniettare

        Returns:
            True se injection riuscita
        """
        if not self.window:
            return False

        js = self.create_cookie_injection_js(cookies)
        try:
            self.window.evaluate_js(js)
            return True
        except Exception as e:
            print(f"[CookieInjector] Injection failed: {e}")
            return False

    def prepare_window_with_cookies(self, cookies: dict, url: str, width: int = 1100, height: int = 850) -> webview.Window:
        """
        Prepara una finestra pywebview con cookie già injectati.

        Args:
            cookies: Cookie da impostare
            url: URL finale
            width: Larghezza finestra
            height: Altezza finestra

        Returns:
            Window configurata
        """
        html_bridge = self.create_html_bridge(cookies, url)

        self.window = webview.create_window(
            "Gemini Auto-Translator",
            html=html_bridge,
            width=width,
            height=height,
            resizable=True
        )

        return self.window

    def inject_via_js_before_load(self, window: webview.Window, cookies: dict) -> None:
        """
        Inietta cookie via JavaScript PRIMA del caricamento della pagina.
        Da chiamare nell'evento loaded.

        Args:
            window: Finestra pywebview
            cookies: Cookie da iniettare
        """
        js = self.create_cookie_injection_js(cookies)
        try:
            window.evaluate_js(f"""
                (function() {{
                    {js}
                    window.location.reload();
                }})();
            """)
        except Exception as e:
            print(f"[CookieInjector] Pre-load injection failed: {e}")


class QtWebEngineCookieInjector:
    """
    Iniettore cookie per QtWebEngine (MiniBrowser).
    """

    @staticmethod
    def create_profile_with_cookies(profile, cookies: dict) -> None:
        """
        Configura un QWebEngineProfile con cookie persistenti.

        Args:
            profile: QWebEngineProfile
            cookies: Dict con cookie
        """
        from PySide6.QtWebEngineCore import QWebEngineCookieStore
        from PySide6.QtNetwork import QNetworkCookie

        cookie_store = profile.cookieStore()

        for name, value in cookies.items():
            if value:
                cookie = QNetworkCookie(name.encode(), value.encode())
                cookie.setDomain(".google.com")
                cookie.setPath("/")
                cookie.setSecure(True)
                cookie_store.setCookie(cookie)

    @staticmethod
    def inject_cookies_to_view(web_view, cookies: dict) -> bool:
        """
        Inietta cookie in una QWebEngineView esistente.

        Args:
            web_view: QWebEngineView
            cookies: Dict con cookie

        Returns:
            True se riuscito
        """
        try:
            profile = web_view.page().profile()
            QtWebEngineCookieInjector.create_profile_with_cookies(profile, cookies)
            return True
        except Exception as e:
            print(f"[QtCookieInjector] Injection failed: {e}")
            return False


class AuthStateManager:
    """
    Gestisce lo stato di autenticazione tra sessioni.
    """

    def __init__(self, storage, cookie_manager):
        self.storage = storage
        self.cookie_manager = cookie_manager
        self._last_check = 0
        self._check_interval = 60

    def is_authenticated(self, force_check: bool = False) -> bool:
        """
        Verifica se l'utente è autenticato.

        Args:
            force_check: Forza rilettura da Firefox

        Returns:
            True se cookie validi disponibili
        """
        now = time.time()
        if now - self._last_check < self._check_interval and not force_check:
            return self.storage.is_valid()

        self._last_check = now

        session = self.storage.load_session()
        if session:
            return True

        cookies_data = self.cookie_manager.get_cookies()
        if not cookies_data:
            return False

        cookies = cookies_data.get("cookies", {})
        if not cookies or not cookies.get("__Secure-1PSID"):
            return False

        return self.storage.store_session(cookies, {
            "source": cookies_data.get("source", "unknown"),
            "timestamp": time.time()
        })

    def get_auth_status(self) -> dict:
        """
        Ritorna stato dettagliato autenticazione.

        Returns:
            Dict con info complete
        """
        session = self.storage.load_session()
        ff_status = self.cookie_manager.get_firefox_status()

        return {
            "is_authenticated": session is not None,
            "session_age": self.storage.get_session_age() if session else 0,
            "firefox_installed": ff_status.get("installed", False),
            "firefox_has_cookies": ff_status.get("has_cookies", False),
            "source": session[1].get("source") if session else None
        }

    def refresh_auth(self) -> bool:
        """
        Forza refresh dell'autenticazione da Firefox.

        Returns:
            True se refresh riuscito
        """
        cookies_data = self.cookie_manager.get_cookies()
        if not cookies_data:
            return False

        cookies = cookies_data.get("cookies", {})
        if not cookies or not cookies.get("__Secure-1PSID"):
            return False

        return self.storage.store_session(cookies, {
            "source": cookies_data.get("source", "unknown"),
            "timestamp": time.time(),
            "refreshed": True
        })

    def clear_auth(self) -> bool:
        """
        Pulisce sessione autenticazione.

        Returns:
            True se pulizia riuscita
        """
        return self.storage.clear_session()
