"""
geminiamo_auth package
----------------------
Gestione autenticazione Gemini per TXT mode.
Supporta estrazione cookie da Firefox e iniezione nei browser embedded.
"""

from .cookie_manager import (
    BrowserCookieManager,
    FirefoxCookieExtractor,
    ChromeCookieExtractor,
    get_browser_manager
)

from .secure_storage import SecureCookieStorage

from .browser_injector import (
    PyWebviewCookieInjector,
    QtWebEngineCookieInjector,
    AuthStateManager
)

__all__ = [
    "BrowserCookieManager",
    "FirefoxCookieExtractor",
    "ChromeCookieExtractor",
    "get_browser_manager",
    "SecureCookieStorage",
    "PyWebviewCookieInjector",
    "QtWebEngineCookieInjector",
    "AuthStateManager",
]
