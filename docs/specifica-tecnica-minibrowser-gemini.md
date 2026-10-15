# Specifica Tecnica: Integrazione Minibrowser per Gemini Web

**Progetto:** KomicTranslate  
**Versione:** 1.0  
**Data:** 15 Aprile 2026  
**Stato:** Proposta Architetturale

---

## 1. Panoramica e Obiettivi

Il componente Minibrowser integra un browser embedded basato su Qt WebEngine per interagire programmaticamente con l'interfaccia web di Gemini. Questo documento definisce l'architettura, i metodi di automazione, le strategie di gestione stati, i requisiti di sicurezza e le procedure di error handling.

**Obiettivi Principali:**
- Automazione TXT IN: invio programmatico di testo/input alla pagina Gemini
- Automazione TXT OUT: estrazione di risposte testuali dal DOM della pagina
- Interazione con elementi DOM della pagina Gemini per operazioni automatizzate

---

## 2. Architettura del Minibrowser

### 2.1 Scelta Tecnologica: QtWebEngineWidgets

| Componente | Valutazione | Vantaggi | Svantaggi |
|------------|-------------|----------|-----------|
| **QtWebEngineWidgets (QWebEngineView)** | ✅ Raccomandato | Integrazione nativa Qt, accesso DOM completo via JS injection, supporto Chrome DevTools Protocol, multipiattaforma | Overhead memoria (~100-200MB), dipendenza da sistema |
| iframe | ❌ Sconsigliato | Semplicità iniziale | Sandbox same-origin, accesso DOM limitato, Google blocca embedding |
| Componente Custom (CEF/Electron) | ❌ Non raccomandato | Controllo totale | Complessità elevata, stack tecnologico separato, manutenzione onerosa |
| Selenium/Playwright standalone | ⚠️ Ibrido | Automazione robusta | Processo separato, IPC complesso, duplicazione stack browser |

**Motivazione:** QtWebEngineWidgets è il componente già presente in `app/ui/widgets/mini_browser.py`. Offre accesso completo al DOM via JavaScript injection, è nativamente integrato con Qt (thread safety), e supporta il Chrome DevTools Protocol per debugging avanzato.

### 2.2 Architettura Componenti

```
┌─────────────────────────────────────────────────────────────────┐
│                     MiniBrowserWidget (Qt Widget)                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Toolbar: back, forward, refresh, expand, external          │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ QWebEngineView                                              │  │
│  │  ├── QWebEnginePage (Chrome/Chromium embed)                │  │
│  │  │    ├── JavaScript Context (TXT IN/OUT engine)           │  │
│  │  │    ├── DOM Access (querySelector, XPath)                 │  │
│  │  │    └── Signal/Slot per eventi asincroni                 │  │
│  │  └── QWebEngineProfile                                      │  │
│  │       └── User Agent: Linux Chrome per evitare Passkey      │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ GeminiAutomationController (Controller separato)           │  │
│  │  ├── TextInputService: Inietta testo in textarea           │  │
│  │  ├── ResponseExtractionService: Parsing risposte DOM       │  │
│  │  ├── StateManager: Gestione stati operazione               │  │
│  │  └── ErrorHandler: Gestione timeout/UI changes             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Configurazione WebEngine

```python
# Configurazione esistente in mini_browser.py (linee 89-99)
settings = self.webview.settings()
settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
settings.setAttribute(settings.WebAttribute.JavascriptCanAccessClipboard, True)
settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
settings.setAttribute(settings.WebAttribute.ScrollAnimatorEnabled, True)

# User Agent Linux per evitare prompt Windows Hello/Passkey
profile = self.webview.page().profile()
profile.setHttpUserAgent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...")
```

**Configurazioni aggiuntive necessarie per automazione:**

| Impostazione | Valore | Ragione |
|--------------|--------|---------|
| `JavascriptCanCloseWindows` | `True` | Permetti chiusura popup Gemini |
| `ErrorPageEnabled` | `True` | Mostra errori pagina anziché blank |
| `PluginsEnabled` | `False` | Sicurezza, nessun plugin necessario |
| `AllowRunningInsecureContent` | `False` | Blocca contenuti misti HTTP/HTTPS |

---

## 3. Sistema di Automazione

### 3.1 Matrice Decisionale Metodi di Automazione

| Metodo | Complessità | Affidabilità DOM Changes | Performance | Manutenzione | Raccomandazione |
|--------|-------------|--------------------------|-------------|--------------|-----------------|
| **JavaScript Injection** | ⭐ Bassa | ⭐⭐ Media | ⭐⭐⭐⭐ Alta | ⭐⭐⭐ Media | ✅ Default per TXT IN/OUT |
| **Chrome DevTools Protocol (CDP)** | ⭐⭐ Media | ⭐⭐⭐⭐ Alta | ⭐⭐⭐⭐ Alta | ⭐⭐ Media | ✅ Per debugging avanzato |
| **API Native WebDriver** | ⭐⭐⭐ Alta | ⭐⭐⭐⭐ Alta | ⭐⭐ Media | ⭐⭐ Bassa | ⚠️ Solo per fallback |
| **Framework Testing (Playwright)** | ⭐⭐⭐⭐ Alta | ⭐⭐⭐⭐⭐ Molto Alta | ⭐⭐ Media | ⭐⭐⭐ Media | ⚠️ Integrare esternamente |

### 3.2 JavaScript Injection (Metodo Principale)

JavaScript injection è il metodo raccomandato per l'automazione TXT IN/OUT. Il `QWebEngineView` espone il metodo `runJavaScript()` per eseguire codice nel contesto della pagina.

**Flusso TXT IN (Input Testuale):**

```
Applicazione KomicTranslate
    │
    ├──> GeminiAutomationController
    │     ├── 1. Attende DOMReady: wait_for_selector("textarea")
    │     ├── 2. runJavaScript(): inpagine.setText("prompt...")
    │     ├── 3. Click pulsante submit
    │     └── 4. Attesa response
    │
    └──> QWebEngineView.runJavaScript()
              │
              ▼
         Pagina Gemini (DOM)
         textarea#... →.value = "testo"
         button[aria-label="Run"] → .click()
```

**Flusso TXT OUT (Output Testuale):**

```
Pagina Gemini (DOM)
    │
    ├──> Response div rilevato
    │     └── MutationObserver triggerato
    │
    └──> runJavaScript(): extract_response_text()
              │
              ▼
         Applicazione KomicTranslate
              │
              └──> StateManager.on_response_received()
```

### 3.3 Selettori DOM per Gemini (da monitorare)

Google Gemini modifica frequentemente la struttura DOM. I selettori devono essere parametrizzati e verificabili.

**Selettori attuali (2026-04):**

```javascript
const SELECTORS = {
  // Input
  textarea: "textarea[aria-label*='message'], textarea[name='message']",
  submit_button: "button[aria-label*='Run'], button[data-testid='run-button']",

  // Output
  response_container: "[data-testid='response-container'], .response-block",
  response_text: "markdown-content, pre[data-testid='response-text']",

  // Status
  loading_indicator: "[aria-label*='Generating'], .generating-spinner",
  error_message: "[role='alert'], .error-state",

  // Auth
  login_form: "#email, input[name='email']",
  cookie_banner: "[aria-label*='Accept'], .cookie-banner button"
};
```

**Strategia Adaptive Selector:**
- Prova selettore primario → se non trovato (Timeout 2s)
- Prova selettore secondario → se non trovato
- Log warning e ritorna errore
- Invia metriche a sistema di monitoraggio per aggiornamento selettori

### 3.4 Gestione State Machine

```
┌──────────┐    init()    ┌──────────────┐
│  IDLE    │─────────────>│ INITIALIZING │
└──────────┘              └──────┬───────┘
     ▲                           │
     │                     page_loaded
     │                           │
     │                           ▼
     │                    ┌──────────────┐
     │                    │   LOADED     │
     │                    └──────┬───────┘
     │                           │
     │                    input_text()
     │                           │
     │                           ▼
     │                    ┌──────────────┐
     │                    │  SENDING     │
     │                    └──────┬───────┘
     │                           │
     │              response_received()
     │                           │
     │                           ▼
     │                    ┌──────────────┐
     │                    │  WAITING     │
     │                    └──────┬───────┘
     │                           │
     │              response_ready()
     │                           │
     │                           ▼
     │                    ┌──────────────┐
     └────────────────────│   DONE       │
                          └──────────────┘

  Stati di errore:
  ├──> TIMEOUT ──────────> ERROR_TIMEOUT
  ├──> DOM_CHANGED ──────> ERROR_DOM_CHANGED
  ├──> NETWORK_ERROR ────> ERROR_NETWORK
  └──> RATE_LIMITED ─────> ERROR_RATE_LIMITED
```

---

## 4. Requisiti di Sicurezza e Same-Origin

### 4.1 Politiche Same-Origin

`QWebEngineView` implementa le politiche same-origin di Chromium. Gemini è hosted su `https://gemini.google.com`, quindi:

| Politica | Applicazione | Implicazione |
|----------|--------------|--------------|
| **Same-Origin Policy (SOP)** | JavaScript in Gemini può accedere solo a risorse same-origin | ✅ Non influenza automazione |
| **Cross-Origin Resource Sharing (CORS)** | Chiamate API Gemini da JS page sono gestite dal browser | ✅ Funziona normalmente |
| **Content Security Policy (CSP)** | Gemini definisce CSP restrittive | ⚠️ Verificare che JS injection non violi CSP |
| **Iframe Policy** | Gemini X-Frame-Options o frame-ancestors | ✅ Non usiamo iframe |

**Nota:** QWebEngineView carica Gemini come URL principale, quindi è considered "first-party". Non ci sono restrizioni CORS per operazioni same-origin.

### 4.2 Rischi di Sicurezza e Mitigazioni

| Rischio | Probabilità | Impatto | Mitigazione |
|---------|-------------|---------|-------------|
| **Session Hijacking** | Bassa | Alto | Non memorizzare sessioni Gemini nel browser; usare API ufficiali |
| **XSS via Injection** | Molto bassa | Alto | JS injection è limited scope, no eval() con input utente |
| **Credential Exposure** | Bassa | Critico | Mai inviare credenziali via DOM; usare API key gestita separatamente |
| **Man-in-the-Middle** | Molto bassa | Alto | HTTPS enforced, validazione certificati da Qt Network |
| **Data Leakage** | Bassa | Medio | Log solo metadati operazione, mai contenuto risposte |

### 4.3 Raccomandazioni Sicurezza

1. **Nessuna memorizzazione persistente di sessioni Gemini** nel browser embedded
2. **Isolamento browser**: usare QWebEngineProfile dedicato per Minibrowser
3. **No loading di risorse esterne non trusted** nel contesto Gemini
4. **Timeout di inattività**: chiudere browser dopo 30 minuti di non uso
5. **Input sanitization**: validare tutto l'input testuale prima di injection
6. **Audit trail**: loggare tutte le operazioni di automazione (senza dati sensibili)

---

## 5. Gestione Errori

### 5.1 Timeout e Retry Strategy

| Tipo Timeout | Durata | Retry | Backoff | Azione Finale |
|--------------|--------|-------|---------|---------------|
| **DOM Ready** | 10s | 3 | 1s/2s/4s | Log + Fallback UI manuale |
| **Page Load** | 30s | 2 | 5s/10s | Refresh pagina + retry |
| **Response Wait** | 120s | 2 | 30s/60s | Check network + retry |
| **Total Operation** | 180s | 0 | N/A | Abort + errore utente |

### 5.2 Rilevamento Cambiamenti UI Gemini

Google modifica frequentemente l'interfaccia Gemini. Strategia di rilevamento:

```python
class DOMChangeDetector:
    """
    Rileva cambiamenti nella struttura DOM di Gemini.
    """

    def __init__(self):
        self.last_known_selectors = SELECTORS.copy()
        self.mutation_count_threshold = 50  # Mutazioni DOM in 5s

    def detect_change(self, page) -> bool:
        """
        Ritorna True se la pagina è cambiata significativamente.
        """
        # 1. Verifica esistenza selettori critici
        critical_selectors = ["textarea", "button[aria-label*='Run']"]
        for selector in critical_selectors:
            if not self._selector_exists(page, selector):
                self._report_selector_missing(selector)
                return True

        # 2. Monitora mutation rate
        mutations = self._get_mutation_count()
        if mutations > self.mutation_count_threshold:
            self._report_high_mutation_rate(mutations)
            return True

        return False

    def _selector_exists(self, page, selector) -> bool:
        script = f"""
            () => {{
                return document.querySelector('{selector}') !== null;
            }}
        """
        return page.runJavaScript(script)
```

### 5.3 Errori di Rete

| Errore | Rilevamento | Azione |
|--------|-------------|--------|
| **Connection Timeout** | `loadFinished(false)` + URL valido | Retry con backoff, poi fallback |
| **DNS Failure** | `loadFinished(false)` + URL valido | Check connessione sistema, avvisa utente |
| **SSL Error** | `QSslSocket::error()` | Log errore, non retry automatico |
| **Proxy Error** | Response header o timeout | Rileggi configurazione proxy sistema |
| **Rate Limit Gemini** | Response contains "rate limit" | Backoff 60s, poi retry |

### 5.4 Codici Errore

| Codice | Significato | Azione Utente |
|--------|-------------|---------------|
| `MINI_001` | Timeout DOM ready | Verificare connessione, riprovare |
| `MINI_002` | Selettori DOM non trovati | UI Gemini potrebbe essere cambiata, segnalare |
| `MINI_003` | Timeout response | Gemini potrebbe essere sovraccarico, riprovare |
| `MINI_004` | Network error | Check connessione internet |
| `MINI_005` | Rate limited | Attendere 60s prima di riprovare |
| `MINI_006` | Auth required | Effettuare login manuale in Minibrowser |

---

## 6. Vantaggi e Svantaggi Tecnici

### 6.1 Vantaggi

| Vantaggio | Descrizione | Impatto Quantitativo |
|-----------|-------------|----------------------|
| **Riduzione tempo operazione** | Automazione TXT IN/OUT vs input manuale | ~70% tempo risparmiato per operazione singola |
| **Eliminazione errore umano** | Input preciso, nessun typo, risposta esatta | Affidabilità ↑ 95% vs 80% manuale |
| **Scalabilità operazioni** | Batch processing automatico di N pagine | 10x throughput vs operazione manuale |
| **Accesso a funzionalità non API** | Utilizzo feature web-only non esposte via API | Feature parity con UI web |
| **Costo zero per Gemini** | Uso gratuito della UI web (nei limiti) | Risparmio €0.002/richiesta vs API |
| **Feedback visivo real-time** | Utente vede cosa succede, può intervenire | User experience migliorata |

### 6.2 Svantaggi

| Svantaggio | Descrizione | Gravità | Mitigazione |
|------------|-------------|---------|-------------|
| **Dipendenza UI soggetta a modifiche** | Google cambia DOM frequentemente | ⭐⭐⭐⭐ Alta | Sistema di rilevamento change, aggiornamenti rapidi |
| **Overhead prestazionale** | Browser embedded consuma ~150MB RAM | ⭐⭐ Media | Solo quando necessario, cleanup risorse |
| **Violazione ToS potenziale** | Automazione UI potrebbe violare termini Google | ⭐⭐⭐ Alta | Usare API ufficiali come fallback primario |
| **Complessità manutenzione** | Selettori, wait conditions, retry logic | ⭐⭐⭐ Media | Modularizzare, test automatizzati |
| **Rate limit unpredictibile** | Google non documenta limiti UI web | ⭐⭐⭐ Alta | Debouncing, retry con backoff |
| **Anti-bot detection** | Google può rilevare automazione | ⭐⭐ Media | User agent Linux, delay naturali |

### 6.3 Analisi Costo-Beneficio

| Scenario | Benefici | Costi | Verdetto |
|----------|----------|-------|----------|
| **Uso occasionale (<5 pg/sessione)** | Basso beneficio | Alta manutenzione | ❌ Non raccomandato |
| **Uso medio (10-30 pg/sessione)** | Alto beneficio | Media manutenzione | ⚠️ Raccomandato con API fallback |
| **Uso intensivo (>30 pg/sessione)** | Molto alto beneficio | Alta manutenzione | ⚠️ Solo con team dedicato manutenzione |

---

## 7. Metriche di Performance

### 7.1 Metriche Operazionali

| Metrica | Unità | Target | Soglia Warning | Soglia Fallimento |
|---------|-------|--------|----------------|-------------------|
| **Tempo TXT IN** (invio prompt) | secondi | < 2s | > 5s | > 10s |
| **Tempo TXT OUT** (estrazione risposta) | secondi | < 5s | > 15s | > 30s |
| **Tempo ciclo completo** (IN + OUT) | secondi | < 10s | > 30s | > 60s |
| **Throughput** | operazioni/minuto | > 6 | < 3 | < 1 |
| **Tasso successo** | % | > 95% | < 85% | < 70% |
| **Memory overhead** | MB | < 200 | > 350 | > 500 |

### 7.2 Metriche di Affidabilità

| Metrica | Target | Misurazione |
|---------|--------|-------------|
| **MTTR** (Mean Time To Recovery) | < 30s | Tempo medio recovery da errore |
| **MTBF** (Mean Time Between Failures) | > 50 operazioni | Operazioni tra failure |
| **Change Detection Success Rate** | > 80% | Rilevamento correct di UI changes |
| **False Positive Rate** | < 5% | Change detection quando UI è stabile |

### 7.3 Logging Metriche

```python
# Struttura metriche salvate in config/gemini_browser_metrics.json
{
  "session_id": "uuid",
  "operations": [
    {
      "timestamp": "ISO8601",
      "type": "TXT_IN|TXT_OUT",
      "duration_ms": 1234,
      "success": true,
      "error_code": null,
      "retry_count": 0,
      "dom_selectors_valid": true,
      "response_size_chars": 5678
    }
  ],
  "aggregates": {
    "total_operations": 100,
    "success_rate": 0.95,
    "avg_duration_ms": 8000,
    "ui_changes_detected": 2
  }
}
```

---

## 8. Piano di Testing Automatizzato

### 8.1 Test Suite Minibrowser

| ID Test | Categoria | Descrizione | Criterio Accettazione |
|---------|-----------|-------------|----------------------|
| MB-001 | Unit | TextInputService.format_prompt() | Prompt formattato correttamente |
| MB-002 | Unit | SelectorValidator.validate() con selettori validi | True per selettori noti |
| MB-003 | Unit | SelectorValidator.validate() con selettori invalidi | False + warning logged |
| MB-004 | Integration | Invia prompt a Gemini (se raggiungibile) | Response container appare |
| MB-005 | Integration | Estrai risposta da DOM | Testo estratto match atteso |
| MB-006 | Integration | Timeout handling (DOM non pronto) | Errore MINI_001 dopo 10s |
| MB-007 | Integration | Retry logic su failure | Retry count incrementato |
| MB-008 | Regression | UI change detection (mock DOM) | Change rilevato quando atteso |
| MB-009 | Performance | Ciclo completo IN+OUT | < 30s per operazione |
| MB-010 | Stress | 50 operazioni consecutive | Success rate > 80% |

### 8.2 Test Ibridi con Framework Esistenti

**Integrazione con Playwright per test E2E:**

```python
# Test playbook per verifica automatica selettori Gemini
# Utilizzato periodicamente per verificare che selettori siano ancora validi

async def test_gemini_selectors():
    """
    Verifica che i selettori DOM di Gemini siano ancora validi.
    Da eseguire semanalmente o dopo aggiornamenti Gemini.
    """
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()

    await page.goto("https://gemini.google.com/")
    await page.wait_for_load_state("networkidle")

    # Verifica selettori
    selectors = ["textarea", "button[aria-label*='Run']"]
    for selector in selectors:
        element = await page.query_selector(selector)
        if not element:
            log.warning(f"Selector invalid: {selector}")
            # Invia notifica team per aggiornamento

    await browser.close()
```

### 8.3 Pipeline CI/CD

```
┌─────────────┐    ┌──────────────┐    ┌────────────────┐
│  Commit     │───>│ Lint + Type  │───>│ Unit Tests     │
│  (PR/Merge) │    │ Check        │    │ (MB-001 → MB-003) │
└─────────────┘    └──────────────┘    └───────┬────────┘
                                                │
                                           (se passano)
                                                │
                                                ▼
                                       ┌────────────────┐
                                       │ Integration    │
                                       │ Tests          │
                                       │ (MB-004 → MB-008)
                                       └───────┬────────┘
                                                │
                                           (se passano)
                                                │
                                                ▼
                                       ┌────────────────┐
                                       │ Deploy Staging │
                                       └───────┬────────┘
                                                │
                                           (se passano)
                                                ▼
                                       ┌────────────────┐
                                       │ Performance    │
                                       │ Validation     │
                                       │ (MB-009 → MB-010)
                                       └────────────────┘
```

---

## 9. Procedure Fallback e Recovery

### 9.1 Strategia Fallback a Più Livelli

```
┌─────────────────────────────────────────────────────────────────┐
│                    Richiesta Traduzione/OCR                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ LIVELLO 1: Minibrowser Gemini Web (Automazione JS)              │
│  ├── TXT IN: runJavaScript() → textarea.value                  │
│  ├── TXT OUT: MutationObserver → extract response              │
│  └── Timeout: 120s → Retry 2x con backoff                       │
│                                                                   │
│  Esito:                                                           │
│  ├── ✅ Successo → Risultato                                    │
│  ├── ❌ DOM Change → Rileva e riprova (se selettori alternativi) │
│  ├── ❌ Timeout → Fallback LIVELLO 2                           │
│  ├── ❌ Rate Limit → Wait 60s → Retry (max 2)                   │
│  └── ❌ Error MINI_001-006 → Fallback LIVELLO 2                │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ LIVELLO 2: GeminiamoOCR (Web Cookie - DEPRECATO)                │
│  ├── Cookie Firefox con sessione attiva                        │
│  ├── Debouncing adattivo 2-4s                                   │
│  └── Timeout: 60s → Retry 3x                                    │
│                                                                   │
│  ⚠️ ATTENZIONE: Deprecato, usare solo se API non disponibile   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ LIVELLO 3: GeminiOCR (API Ufficiale)                            │
│  ├── API Key necessaria                                         │
│  ├── Rate limit: 60 RPM (free tier)                            │
│  └── Timeout: 30s → Retry con backoff                           │
│                                                                   │
│  Esito:                                                           │
│  ├── ✅ Successo → Risultato                                    │
│  └── ❌ Quota esaurita → Fallback LIVELLO 4                     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ LIVELLO 4: DocTR OCR + Traduzione DeepL/Google                 │
│  ├── Locale, nessuna API key necessaria                         │
│  ├── Qualità inferiore a Gemini                                 │
│  └── Fallback ultimo resort                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Recovery Procedure

**Recover da DOM Change:**

```
1. Rileva change (DOMChangeDetector)
2. Logga UI change con screenshot (se debug abilitato)
3. Prova selettori alternativi (max 3 tentativi)
4. Se ancora fallito:
   a. Notifica utente: "UI Gemini cambiata, segnalare al team"
   b. Invia metriche a sistema di monitoraggio
   c. Fallback a LIVELLO 2 o 3
```

**Recovery da Network Error:**

```
1. Rileva network error (loadFinished(false))
2. Verifica connessione sistema (ping gateway)
3. Se connessione OK:
   a. Retry: attendi 5s → reload page → riprova
   b. Se fail ancora: retry con backoff 10s
4. Se connessione KO:
   a. Notifica utente: "Connessione internet assente"
   b. Attendi ripristino (max 5 minuti)
   c. Retry automatico quando connessione ripristinata
```

### 9.3 Manual Override

L'utente può sempre intervenire manualmente:

| Scenario | Opzione Manuale |
|----------|-----------------|
| UI bloccata | Pulsante "Interrompi" nel Minibrowser |
| Login richiesto | Effettua login direttamente nel Minibrowser |
| Fallback completo | Usa API Key in Impostazioni |
| Segnalazione problema | Pulsante "Segnala problema UI" → invia diagnostica |

---

## 10. Raccomandazioni Finali

### 10.1 Quando Usare Minibrowser vs API

| Scenario | Raccomandazione |
|----------|-----------------|
| Batch processing 100+ pagine | ❌ Minibrowser (rate limit bloccherà) → **GeminiOCR API** |
| 10-50 pagine, budget limitato | ⚠️ Minibrowser con fallback API → **Minibrowser + API fallback** |
| < 10 pagine, testing | ✅ Minibrowser → **Minibrowser** |
| Qualità critica | ❌ UI web può variare → **API Ufficiale** |
| Offline/disconnesso | ❌ Impossibile → **DocTR + DeepL fallback** |

### 10.2 Priorità Implementazione

```
FASE 1 (Critico): Robust Error Handling
├── Implementare DOMChangeDetector
├── Aggiungere retry logic con backoff
├── Logging strutturato per diagnostica
└── Fallback automatico a API

FASE 2 (Importante): Stabilizzazione Selettori
├── Sistema di rilevamento selettori invalidi
├── Notifiche automatiche al team
├── Update selettori via config (no deploy)
└── Test automatici periodici con Playwright

FASE 3 (Ottimizzazione): Performance
├── Debouncing ottimizzato
├── Caching risposte (hash prompt → response)
├── Parallelismo per operazioni indipendenti
└── Memory cleanup periodico

FASE 4 (Futuro): AI-Powered Adaptation
├── ML per predizione change UI
├── Auto-update selettori basato su pattern
└── Anomaly detection per rate limit
```

### 10.3 Monitoraggio Continuo

| KPI | Target | Azione se Sotto Soglia |
|-----|--------|------------------------|
| Success Rate | > 90% | Investigare errori, aggiornare selettori |
| Avg Response Time | < 15s | Profilare, ottimizzare wait conditions |
| DOM Change Detection | < 10% false positive | Calibrare threshold |
| User Reports | < 1/week | Investigare pattern, patch emergenziale |

---

## Appendice A: Riferimenti

| Componente | File | Note |
|-----------|------|------|
| MiniBrowser esistente | `app/ui/widgets/mini_browser.py` | Base per automazione |
| Specifica tecnica OCR | `.trae/documents/specifica-tecnica-ocr-traduzione-json.md` | Architettura sistema OCR |
| GeminiamoOCR | `modules/ocr/geminiamo_ocr.py` | Approccio cookie deprecato |
| GeminiOCR | `modules/ocr/gemini_ocr.py` | API ufficiale, fallback primario |

---

*Documento creato: 15 Aprile 2026*
*Ultimo aggiornamento: 15 Aprile 2026*
*Versione Qt WebEngine supportata: Chromium 120+*