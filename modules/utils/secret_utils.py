"""
Helper per gestire in modo sicuro le credenziali (API key) nei log.

Problema risolto: il codice loggava prefissi/tratti di API key
(es. f"API key {api_key[:10]}..."). Nei casi peggiori, quando la chiave era
piu' corta di 12 caratteri, l'hint coincideva con la chiave INTERA.

Soluzione: usare un'impronta SHA-256 non reversibile. Non rivela il valore ma
permette comunque di distinguere e correlare le chiavi nei log e nelle metriche
(es. per capire se due errori riguardano la stessa chiave).
"""
import hashlib
from typing import Optional

__all__ = ["key_fingerprint", "mask_key", "safe_hint"]


def key_fingerprint(key: Optional[str], length: int = 8) -> str:
    """
    Impronta non reversibile di una API key, sicura da mettere nei log.

    Non contiene alcun materiale della chiave: e' l'hash SHA-256 (primi
    `length` hex char). Chiavi diverse producono impronte diverse; la chiave
    originale non e' ricostruibile.

    Args:
        key: la API key (o None)
        length: quante cifre dell'hash usare (default 8)

    Returns:
        Stringa tipo "sha256:1a2b3c4d", oppure "none" se la chiave e' vuota.
    """
    if not key:
        return "none"
    try:
        digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
        return f"sha256:{digest[:length]}"
    except Exception:
        # Non deve mai propagare: questo helper gira dentro logging.
        return "sha256:<error>"


def mask_key(key: Optional[str], visible: int = 4) -> str:
    """
    Maschera per la UI/log: mostra solo gli ultimi `visible` caratteri.

    Pensata per mostrare all'utente quale chiave sta usando senza esporla.
    Meglio di key_fingerprint quando serve riconoscere visivamente la chiave.
    """
    if not key:
        return "(nessuna)"
    key = str(key)
    if len(key) <= visible:
        return "*" * len(key)
    return "*" * (len(key) - visible) + key[-visible:]


def safe_hint(key: Optional[str]) -> str:
    """
    Hint usabile come chiave di dizionario (quota manager, metriche).

    Storicamente era api_key[:8] + "..." + api_key[-4:], che esponeva 12
    caratteri della chiave e, se piu' corta di 12, la chiave INTERA.
    Ora e' un hash: stabile tra le esecuzioni, non reversibile.
    """
    return key_fingerprint(key)