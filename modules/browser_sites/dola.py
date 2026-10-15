"""Adapter per dola.com.

ATTENZIONE - i selettori qui NON sono verificati contro il DOM reale di Dola.
Non ho una sessione autenticata con cui ispezionarlo. Sono selettori
generici per interfacce di chat, scelti nell'ordine piu' probabile, con
fallback espliciti.

Se la traduzione non funziona, il modo piu' rapido e' usare la modalita'
sonda, che stampa cosa trova realmente nella pagina:

    python -m modules.browser_sites.probe Gemini
    python -m modules.browser_sites.probe Dola

Poi correggi i selettori qui dentro. Ogni sito si risolve senza toccare
il motore.
"""
from .base import BrowserSite

DOLA = BrowserSite(
    key="Dola",
    label="Dola",
    url="https://www.dola.com/",

    # textarea e contenteditable sono i due casi piu' diffusi; gli altri
    # sono editor "rich text" usati da diverse chat web.
    composer=[
        "textarea",
        'textarea[placeholder]',
        'div[contenteditable="true"]',
        'div[contenteditable="true"][role="textbox"]',
        '[role="textbox"]',
        ".ql-editor",
        "p.ProseMirror",
        "div.ProseMirror",
    ],

    send=[
        'button[type="submit"]',
        'button[aria-label*="Send" i]',
        'button[aria-label*="Invia" i]',
        'button[aria-label*="Submit" i]',
        'form button:last-of-type',
    ],

    # Dal piu' specifico al meno specifico. Niente fallback generico tipo
    # "main": scatterebbe su qualunque pagina (falso "trovato") e nasconderebbe
    # il fatto che il selettore vero e' ancora sconosciuto. Senza una
    # conversazione con risposta il DOM giusto non esiste: si verifica dopo
    # aver chattato una volta, non prima.
    response=[
        '[data-testid*="message" i]',
        '[class*="message" i][class*="assistant" i]',
        '[class*="assistant" i]',
        '[class*="response" i]',
        '[class*="bubble" i][class*="ai" i]',
        "article",
        '[role="log"] > *:last-child',
    ],

    copy_response=[
        'button[aria-label*="Copy" i]',
        'button[aria-label*="Copia" i]',
        '[data-testid*="copy" i]',
    ],

    stop=[
        'button[aria-label*="Stop" i]',
        'button[aria-label*="Interrompi" i]',
        'button[aria-label*="Fermati" i]',
    ],

    consent=[
        'button:has-text("Accept")',
        'button:has-text("Accetta")',
        'button:has-text("Allow")',
        'button:has-text("Consenti")',
    ],

    # Da verificare: non so se Dola accetta immagini oltre al testo.
    supports_image=False,
    delay_between_pages=10.0,

    # Nascosto dal dropdown finche' invio/risposta non sono verificati
    # (soda: composer ok, send da trovare, response senza conversazione).
    # get_site/is_browser_site continuano a riconoscerlo: i config esistenti
    # e la sonda funzionano, i nuovi utenti non lo vedono.
    hidden=True,
)