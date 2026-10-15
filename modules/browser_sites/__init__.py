"""Registro dei siti "browser" automatizzabili.

Un registro, non una lista sparsa: aggiungere un sito significa creare un
file in questo package e registrarlo qui sotto.
"""
from typing import Dict, List

from .base import BrowserSite
from .gemini import GEMINI
from .dola import DOLA

# Chiave -> sito. La chiave e' anche il translator_key usato nel config.
SITES: Dict[str, BrowserSite] = {
    GEMINI.key: GEMINI,
    DOLA.key: DOLA,
}

# Chiavi usate nelle versioni precedenti del programma, mappate su quelle
# attuali. Serve perche' il translator scelto viene salvato nel registry di
# Windows: un utente che aveva "TXT" deve continuare a funzionare.
LEGACY_KEYS: Dict[str, str] = {
    "TXT": "Gemini",
}

GROUP_LABEL = "── Chat via browser ──"


def get_site(key: str):
    """Ritorna l'adapter del sito, risolvendo anche le chiavi legacy."""
    if key is None:
        return None
    resolved = LEGACY_KEYS.get(key, key)
    return SITES.get(resolved)


def resolve_key(key: str):
    """'TXT' -> 'Gemini'. Per chiavi gia' valide restituisce la stessa chiave."""
    if key is None:
        return None
    return LEGACY_KEYS.get(key, key)


def is_browser_site(key: str) -> bool:
    """True se la chiave identifica un sito browser (quindi va automatizzato)."""
    return get_site(key) is not None


def _visible():
    """Solo i siti non nascosti: quelli che finiscono nel dropdown."""
    return {k: s for k, s in SITES.items() if not s.hidden}


def site_keys(include_hidden: bool = False) -> List[str]:
    src = SITES if include_hidden else _visible()
    return list(src)


def site_labels(include_hidden: bool = False) -> List[str]:
    src = SITES if include_hidden else _visible()
    return [s.label for s in src.values()]


__all__ = [
    "BrowserSite",
    "SITES",
    "LEGACY_KEYS",
    "GROUP_LABEL",
    "GEMINI",
    "DOLA",
    "get_site",
    "resolve_key",
    "is_browser_site",
    "site_keys",
    "site_labels",
]