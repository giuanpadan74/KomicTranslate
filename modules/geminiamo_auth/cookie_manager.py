"""
cookie_manager.py
----------------
Gestisce l'estrazione e memorizzazione dei cookie di Gemini da Firefox.
"""

import os
import platform
import glob
import shutil
import sqlite3
import tempfile
import time
from typing import Optional

COOKIE_NAME_1 = "__Secure-1PSID"
COOKIE_NAME_2 = "__Secure-1PSIDTS"
COOKIE_CACHE_TTL = 14400


class FirefoxCookieExtractor:
    """
    Estrae i cookie di Gemini dal browser Firefox.
    """

    def __init__(self):
        self.platform = platform.system()
        self._profile_path: Optional[str] = None

    def find_firefox_profile(self) -> Optional[str]:
        """
        Trova il percorso del profilo Firefox predefinito.

        Returns:
            Percorso del profilo o None se non trovato
        """
        if self.platform == "Windows":
            profile_base = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles")
        elif self.platform == "Darwin":
            profile_base = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        else:
            profile_base = os.path.expanduser("~/.mozilla/firefox")

        if not os.path.exists(profile_base):
            return None

        profiles = glob.glob(os.path.join(profile_base, "*.default*"))
        if not profiles:
            profiles = glob.glob(os.path.join(profile_base, "*.default"))
        if not profiles:
            return None

        return profiles[0]

    def is_firefox_installed(self) -> bool:
        """Verifica se Firefox è installato."""
        return self.find_firefox_profile() is not None

    def _copy_cookies_db(self) -> Optional[str]:
        """
        Copia il database cookies in una cartella temporanea.
        Funziona anche se Firefox è aperto.
        """
        profile_path = self.find_firefox_profile()
        if not profile_path:
            return None

        cookies_file = os.path.join(profile_path, "cookies.sqlite")
        if not os.path.exists(cookies_file):
            return None

        temp_dir = tempfile.gettempdir()
        temp_cookies = os.path.join(temp_dir, f"ff_cookies_{os.getpid()}.sqlite")

        try:
            shutil.copy2(cookies_file, temp_cookies)
            return temp_cookies
        except PermissionError:
            return None
        except Exception:
            return None

    def _read_cookies(self, db_path: str) -> Optional[dict]:
        """
        Legge i cookie Gemini dal database SQLite.
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT name, value, path, domain, secure, expires
                FROM moz_cookies
                WHERE host LIKE '%google.com%'
                AND (name = ? OR name = ?)
            """, (COOKIE_NAME_1, COOKIE_NAME_2))

            result = {}
            for name, value, path, domain, secure, expires in cursor.fetchall():
                result[name] = {
                    "value": value,
                    "path": path,
                    "domain": domain,
                    "secure": bool(secure),
                    "expires": expires
                }

            conn.close()
            return result if result else None

        except Exception:
            return None

    def get_cookies(self) -> Optional[dict]:
        """
        Estrae i cookie Gemini da Firefox.

        Returns:
            Dict con cookie Google o None se non disponibili
        """
        temp_db = self._copy_cookies_db()
        if not temp_db:
            return None

        try:
            cookies = self._read_cookies(temp_db)
            return cookies
        finally:
            try:
                os.remove(temp_db)
            except Exception:
                pass

    def get_minimal_cookies(self) -> Optional[dict]:
        """
        Estrae solo i valori essenziali per l'autenticazione.
        Formato compatto per iniezione.
        """
        cookies = self.get_cookies()
        if not cookies:
            return None

        return {
            "__Secure-1PSID": cookies.get("__Secure-1PSID", {}).get("value"),
            "__Secure-1PSIDTS": cookies.get("__Secure-1PSIDTS", {}).get("value")
        }


class ChromeCookieExtractor:
    """
    Estrae i cookie di Gemini da Chrome (supporto futuro).
    """

    def is_chrome_installed(self) -> bool:
        """Verifica se Chrome è installato."""
        if platform.system() == "Windows":
            base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
        elif platform.system() == "Darwin":
            base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        else:
            base = os.path.expanduser("~/.config/google-chrome")

        return os.path.exists(base)

    def get_cookies(self) -> Optional[dict]:
        """Estrae cookie da Chrome (da implementare)."""
        return None


class BrowserCookieManager:
    """
    Gestisce l'estrazione cookie da browser disponibili.
    Supporta Firefox (implementato) e Chrome (future).
    """

    def __init__(self):
        self.firefox = FirefoxCookieExtractor()
        self.chrome = ChromeCookieExtractor()

    def is_any_browser_available(self) -> bool:
        """Verifica se almeno un browser con cookie è disponibile."""
        return self.firefox.is_firefox_installed()

    def get_available_browsers(self) -> list:
        """Lista browser disponibili."""
        browsers = []
        if self.firefox.is_firefox_installed():
            browsers.append("Firefox")
        if self.chrome.is_chrome_installed():
            browsers.append("Chrome")
        return browsers

    def get_cookies(self) -> Optional[dict]:
        """
        Estrae cookie dal primo browser disponibile.

        Priority: Firefox > Chrome
        """
        if self.firefox.is_firefox_installed():
            cookies = self.firefox.get_minimal_cookies()
            if cookies and cookies.get("__Secure-1PSID"):
                return {
                    "source": "firefox",
                    "cookies": cookies,
                    "timestamp": time.time()
                }

        if self.chrome.is_chrome_installed():
            cookies = self.chrome.get_cookies()
            if cookies:
                return {
                    "source": "chrome",
                    "cookies": cookies,
                    "timestamp": time.time()
                }

        return None

    def get_firefox_status(self) -> dict:
        """
        Ritorna stato dettagliato di Firefox.

        Returns:
            Dict con info su Firefox e suoi cookie
        """
        profile = self.firefox.find_firefox_profile()
        cookies = self.firefox.get_minimal_cookies() if profile else None

        return {
            "installed": profile is not None,
            "profile_path": profile,
            "has_cookies": cookies is not None and bool(cookies.get("__Secure-1PSID")),
            "cookies": cookies
        }


def get_browser_manager() -> BrowserCookieManager:
    """Factory function per ottenere il gestore browser."""
    return BrowserCookieManager()
