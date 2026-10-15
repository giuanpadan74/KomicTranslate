"""Adapter per gemini.google.com.

I selettori sono presi dal codice Gemini preesistente (modules/gemini_scripts.py
edgemini_extract_scripts.py), non scritti a caso: questo sito funziona gia' e
non si deve regressare.
"""
from .base import BrowserSite

GEMINI = BrowserSite(
    key="Gemini",
    label="Gemini",
    url="https://gemini.google.com/app?hl=it",

    # Il codice esistente prova in quest'ordine (gemini_scripts.py riga 7)
    composer=[
        "textarea",
        '[role="textbox"]',
        ".ql-editor",
        'div[contenteditable="true"]',
    ],

    # gemini_scripts.py righe 99-109
    send=[
        'button:has(mat-icon[svgicon="send"])',
        'button[aria-label*="Invia" i]',
        'button[aria-label*="Send" i]',
        'button[aria-label*="Run" i]',
    ],

    # gemini_extract_scripts.py riga 109, in ordine di specificita'
    response=[
        ".message-content",
        '[data-testid="response-container"]',
        ".markdown",
        "model-response message",
        "model-response",
    ],

    # usati per capire se la generazione e' finita (gemini_extract_scripts.py)
    stop=[
        'button[aria-label*="Interrompi" i]',
        'button[aria-label*="Stop" i]',
    ],

    # pulsante di copia sulla risposta: fallback piu' stabile della lettura DOM
    copy_response=[
        "copy-response-button",
        'button[aria-label*="Copia" i]',
        'button[aria-label*="Copy" i]',
    ],

    # banner di consenso (gemini_automator.py _on_loaded -> get_js_consent)
    consent=[
        'button:has-text("Accetta tutto")',
        'button:has-text("Accept all")',
    ],

    supports_image=True,
    delay_between_pages=8.0,
)