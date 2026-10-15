"""Definizione di un sito "browser": una chat web automatizzata via pywebview.

Ogni sito e' un descrittore di dati: URL, selettori per il composer (dove
scrivere), per l'invio, per estrarre la risposta, e le opzioni del sito.
Non contiene logica: la logica sta in modules/gemini_automator.py, che ora
e' generico rispetto al sito.

I selettori sono volutamente multipli e in italiano + inglese: i siti
cambiano il DOM spesso, e quando lo fanno basta aggiungere una riga qui
invece di modificare il motore.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class BrowserSite:
    """Un sito di chat web automatizzabile."""

    key: str
    label: str
    url: str

    # --- selettori del composer (campo in cui incollare il prompt) ---
    composer: List[str] = field(default_factory=list)

    # --- selettori del pulsante di invio ---
    send: List[str] = field(default_factory=list)

    # --- selettori per leggere la risposta (dal piu' specifico al piu' generico) ---
    response: List[str] = field(default_factory=list)

    # --- selettori per il pulsante di copia della risposta (usato come fallback) ---
    copy_response: List[str] = field(default_factory=list)

    # --- selettori del pulsante "interrompi": presenti = generazione in corso ---
    stop: List[str] = field(default_factory=list)

    # --- pulsanti di consenso/cookie da chiudere all'avvio ---
    consent: List[str] = field(default_factory=list)

    # il sito accetta immagini oltre al testo?
    supports_image: bool = False

    # secondi di attesa minima fra una richiesta e la successiva (rate limiting)
    delay_between_pages: float = 8.0

    # True = il sito esiste nel registro ma non si mostra nel dropdown.
    # Serve per siti a meta' strada (es. Dola: adapter scritto, selettori di
    # invio/risposta non ancora verificati): resta tutto funzionante per chi
    # ce l'ha nel config, ma i nuovi utenti non possono selezionarlo.
    hidden: bool = False

    def __post_init__(self):
        if not self.composer:
            raise ValueError(f"{self.key}: serve almeno un selettore per il composer")
        if not self.response:
            raise ValueError(f"{self.key}: serve almeno un selettore per la risposta")