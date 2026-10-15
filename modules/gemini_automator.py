import threading
import time
import json
import logging
import webview
import os
from typing import Optional, Callable, Dict, List, Any
from modules.browser_sites import get_site, GEMINI
from modules.gemini_clipboard_fallback import extract_translations_from_clipboard, extract_keyed_json_from_clipboard
from modules.gemini_copy_guard import guarded_copy_response
from modules.gemini_extract_scripts import get_js_extract
from modules.gemini_translation_payload import parse_translation_payload
from modules.gemini_scripts import get_js_check_ready, get_js_inject, get_js_consent, get_js_wait_for_send_button, get_js_verify_input
from modules.gemini_scripts_image import get_js_paste_image, get_js_check_image_loaded, get_js_has_pending_image
from modules.gvb_scripts import get_js_attach_and_upload_image, get_js_focus_composer
from modules.gvb_keyboard import focus_and_paste


logger = logging.getLogger(__name__)


def get_site_storage_path(site) -> str:
    """Cartella del profilo webview per un sito, creata se non esiste.

    Funzione unica, usata sia dall'automator sia dalla sonda: se i due
    costruissero il percorso separatamente potrebbero divergere, e la
    sonda mostrerebbe una pagina non loggata mentre l'app e' loggata
    (o viceversa), portando a correggere selettori che vanno bene.
    """
    app_data = os.environ.get('APPDATA', os.getcwd())
    slug = site.key.lower()
    storage_dir = os.path.join(app_data, 'KomicTranslate', f'{slug}_session')
    os.makedirs(storage_dir, exist_ok=True)
    return storage_dir


class GeminiAutomator:
    # Deprecato: l URL viene ora dal sito in modules/browser_sites.
    GEMINI_URL = "https://gemini.google.com/app?hl=it"
    BASE_TIMEOUT = 600
    POLLING_INTERVAL = 2
    TIMEOUT_PER_BLOCK = 30
    MAX_TIMEOUT_BLOCKS = 50
    IMAGE_PATH_START = "[IMAGE_PATH]"
    IMAGE_PATH_END = "[/IMAGE_PATH]"

    def __init__(self, site=None):
        # Sito web da pilotare. None = Gemini, cosi' il comportamento
        # preesistente resta identico quando non se ne specifica uno.
        self.site = site or GEMINI
        self.window: Optional[webview.Window] = None
        self.is_running = False
        self.translations: Dict[str, str] = {}
        self._blocks: List[Dict] = []
        self._full_text = ""
        self._prompt_text = ""
        self._expected_count = 0
        self._progress_callback: Optional[Callable] = None
        self._storage_path = self._get_persistent_storage_path()
        self._start_time = 0
        self._pending_image_path: Optional[str] = None
        self._image_injection_failed = False
        self._automation_started = False
        self._stopped = False
        self._capture_image = False
        self.copied_image = False
        self._keyed_json_mode = False
        self._js_error_streak = 0
        self._last_js_ok_at = 0.0
        self._last_reload_at = 0.0
        self._reload_requested = False

    def _log(self, message: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] [{self.site.label} Auto] {message}"
        print(formatted)
        logger.info(formatted)

    def _get_persistent_storage_path(self) -> str:
        # Percorso condiviso con la sonda: vedi get_site_storage_path.
        return get_site_storage_path(self.site)

    def _extract_image_path(self, text: str) -> tuple[Optional[str], str]:
        start = text.find(self.IMAGE_PATH_START)
        end = text.find(self.IMAGE_PATH_END)
        if start == -1 or end == -1 or end <= start:
            return None, text
        image_path = text[start + len(self.IMAGE_PATH_START):end].strip()
        prompt = (text[:start] + text[end + len(self.IMAGE_PATH_END):]).strip()
        return image_path or None, prompt

    def _extract_capture_mode(self, text: str) -> tuple[bool, str]:
        marker = "[CAPTURE_IMAGE]"
        if marker not in text:
            return False, text
        return True, text.replace(marker, "").strip()

    def _extract_keyed_json_mode(self, text: str) -> tuple[bool, str]:
        marker = "[KEYED_JSON]"
        if marker not in text:
            return False, text
        return True, text.replace(marker, "").strip()

    def _on_loaded(self):
        if not self.window or self._stopped:
            return
        url = self.window.get_current_url()
        self._log(f"Window loaded: {url}")
        if "consent.google.com" in url:
            self._safe_evaluate_js(get_js_consent())
            return
        if "gemini.google.com" in url and not self._automation_started:
            self._automation_started = True
            threading.Thread(target=self._automation_thread, daemon=True).start()

    def _check_logged_in(self) -> bool:
        """True se la sessione sembra autenticata.

        Tre segnali, perche' uno solo da' falsi positivi: la pagina di login
        di Google (accounts.google.com) non ha alcun bottone "Accedi" ma un
        campo email + "Avanti", quindi contarli direbbe "loggato" su una
        pagina dove non lo siamo. Stessa logica della sonda (probe.py).

        Se il controllo stesso fallisce (JS non raggiungibile) risponde
        True: meglio procedere e lasciar emergere un timeout reale che
        bloccare tutto con un errore inventato.
        """
        js = (
            "(() => {"
            " const n = Array.from(document.querySelectorAll('button, a'))"
            "   .filter(b => /^(Accedi|Sign in|Log in)$/i.test((b.innerText||'').trim())).length;"
            " const suLogin = /accounts\\.google\\.com/i.test(location.href);"
            " const email = document.querySelector('input[type=\"email\"]') !== null;"
            " return JSON.stringify({n: n, suLogin: suLogin, email: email});"
            "})()"
        )
        try:
            raw = self.window.evaluate_js(js) if self.window else None
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            return (int(data.get("n", 0)) == 0
                    and not data.get("suLogin", False)
                    and not data.get("email", False))
        except Exception as exc:
            self._log(f"Controllo login non riuscito, procedo: {exc}")
            return True

    def _on_site_page(self) -> bool:
        """True se la finestra e' tornata sul sito, non sul login di Google.

        Serve perche' _check_logged_in risponde True quando il JS fallisce
        (scelta deliberata): durante la navigazione del login quel True
        transitorio farebbe procedere l'automator su accounts.google.com.
        Questo controllo lato Python chiude quel buco.
        """
        try:
            url = self.window.get_current_url() if self.window else ""
        except Exception:
            return False
        return bool(url) and "accounts.google.com" not in url

    def _safe_evaluate_js(self, script: str):
        if not self.window or self._stopped:
            return None
        try:
            result = self.window.evaluate_js(script)
            self._js_error_streak = 0
            self._last_js_ok_at = time.time()
            return result
        except Exception as exc:
            self._js_error_streak += 1
            self._log(f"evaluate_js fallito (streak={self._js_error_streak}): {exc}")
            now = time.time()
            if self._js_error_streak >= 5 and now - self._last_reload_at > 20:
                self._last_reload_at = now
                try:
                    self._log("Troppi errori JS consecutivi: ricarico la pagina Gemini e continuo.")
                    self._reload_requested = True
                    self.window.load_url(self.site.url)
                except Exception as reload_exc:
                    self._log(f"Reload fallito: {reload_exc}")
            return None

    def _consume_reload_requested(self) -> bool:
        if not self._reload_requested:
            return False
        self._reload_requested = False
        return True

    def _close_window(self):
        if self._stopped:
            return
        self._stopped = True
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass

    def _finalize_translation_success(self, translations: Dict[str, str], report: Dict[str, Any]):
        self.translations = translations
        self._log(
            "Risultato traduzione acquisito. "
            f"Blocchi trovati: {report.get('total_found', len(translations))}/{self._expected_count} "
            f"(source={report.get('source', 'unknown')})"
        )
        time.sleep(1)
        self._close_window()

    def _handle_terminal_json_error(
        self,
        raw_result: str,
        translations: Dict[str, str],
        report: Dict[str, Any],
    ):
        preview = (raw_result or "").strip().replace("\n", "\\n")[:500]
        self._log(
            "Payload JSON anomalo rilevato dopo generazione completa. "
            f"source={report.get('source')} missing={report.get('missing_blocks')} "
            f"empty={report.get('empty_blocks')} error={report.get('error')} preview={preview}"
        )
        if translations:
            self.translations = translations
        self._close_window()

    def _get_dynamic_timeout(self) -> int:
        block_count = max(self._expected_count, 1)
        effective_blocks = min(block_count, self.MAX_TIMEOUT_BLOCKS)
        dynamic_timeout = self.BASE_TIMEOUT + (effective_blocks - 1) * self.TIMEOUT_PER_BLOCK
        return min(dynamic_timeout, 2400)

    def _maybe_prepare_image(self) -> bool:
        if not self._pending_image_path:
            return True
        if not os.path.exists(self._pending_image_path):
            self._log(f"Immagine non trovata: {self._pending_image_path}")
            return False
        try:
            with open(self._pending_image_path, 'rb'):
                pass
        except Exception as exc:
            self._log(f"Impossibile leggere immagine: {exc}")
            return False
        return True

    def _wait_for_image_loaded(self) -> bool:
        for _ in range(12):
            status = self._safe_evaluate_js(get_js_check_image_loaded())
            if self._stopped:
                return False
            if status == 'loaded':
                self._log("Immagine agganciata correttamente all'input")
                return True
            if status == 'uploading':
                self._log("Upload immagine ancora in corso...")
                time.sleep(0.5)
                continue
            time.sleep(0.3)
        return False

    def _parse_upload_result(self, upload_result) -> Dict[str, object]:
        if isinstance(upload_result, str):
            try:
                parsed = json.loads(upload_result)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {'raw': upload_result}
        if isinstance(upload_result, dict):
            return upload_result
        return {'raw': repr(upload_result)}

    def _inject_image_if_needed(self) -> bool:
        if not self._pending_image_path:
            return True
        phase_state = self._safe_evaluate_js(get_js_has_pending_image())
        if self._stopped:
            return False
        if phase_state == 'uploading':
            self._log("Upload immagine ancora in corso...")
            return False
        composer_focus = self._safe_evaluate_js(get_js_focus_composer())
        self._log(f"Focus composer prima del paste: {composer_focus}")
        time.sleep(0.25)
        self._log("Provo Ctrl+V reale sulla finestra Gemini come strategia primaria...")
        pasted = focus_and_paste(self.window)
        if pasted:
            time.sleep(0.8)
        if self._stopped:
            return False
        if pasted and self._wait_for_image_loaded():
            self._log("Immagine inserita con Ctrl+V primario")
            return True
        self._log("Ctrl+V primario non sufficiente, rifocalizzo il composer e provo un secondo Ctrl+V reale...")
        composer_focus = self._safe_evaluate_js(get_js_focus_composer())
        self._log(f"Focus composer secondo tentativo: {composer_focus}")
        time.sleep(0.25)
        pasted = focus_and_paste(self.window)
        if pasted:
            time.sleep(0.8)
        if self._stopped:
            return False
        if pasted and self._wait_for_image_loaded():
            self._log("Immagine inserita con secondo Ctrl+V primario")
            return True
        self._log("Secondo Ctrl+V non sufficiente, provo paste JS secondario...")
        js_pasted = self._safe_evaluate_js(get_js_paste_image())
        if self._stopped:
            return False
        if js_pasted and self._wait_for_image_loaded():
            self._log("Immagine inserita con paste JS secondario")
            return True
        self._log("Paste automatico non sufficiente, raccolgo diagnostica DOM e provo fallback operativo su Caricamento e strumenti...")
        upload_result = self._safe_evaluate_js(get_js_attach_and_upload_image(self._pending_image_path))
        if self._stopped:
            return False
        upload_info = self._parse_upload_result(upload_result)
        self._log(f"Diagnostica upload fallback: {upload_info}")
        upload_step = str(upload_info.get('step', 'unknown'))
        if upload_step in ['file_input_ready', 'preview_already_present']:
            if self._wait_for_image_loaded():
                self._log("Immagine inserita con upload fallback")
                return True
            self._log(f"Input file trovato ma nessuna preview caricata. Stato: {upload_step}")
        elif upload_step in ['attach_clicked_no_input', 'no_attach_no_input', 'upload_menu_clicked_no_input']:
            self._log(f"Attach/input non disponibili per upload DOM. Stato: {upload_step}")
            self._log(
                "Composer diagnostic: "
                f"found={upload_info.get('composerFound')} "
                f"clicked={upload_info.get('composerClicked')}"
            )
            if upload_info.get('visibleButtonLabels'):
                self._log(f"Bottoni visibili rilevati: {upload_info.get('visibleButtonLabels')}")
            if upload_info.get('menuTexts'):
                self._log(f"Voci menu rilevate: {upload_info.get('menuTexts')}")
            if upload_info.get('createImageFound'):
                self._log("Voce 'Crea immagine' rilevata nel menu Gemini")
        self._image_injection_failed = True
        self._log("Immagine non rilevata nell'input dopo doppio Ctrl+V primario, paste JS secondario e fallback Caricamento e strumenti")
        return False

    def _automation_thread(self):
        self._start_time = time.time()
        self._dynamic_timeout = self._get_dynamic_timeout()
        injected = False
        send_clicked = False
        verify_start_time = 0
        image_ready = False
        self._image_injection_failed = False
        last_progress_at = time.time()
        last_ready_at = 0.0

        self._log(f"[TIMEOUT] Calcolato timeout dinamico: {self._dynamic_timeout}s per {self._expected_count} blocchi")

        # Login non ancora verificato: il controllo va fatto quando la pagina
        # e' pronta, non all'avvio. Su una pagina che sta ancora caricando i
        # pulsanti "Accedi" potrebbero non essere ancora nel DOM e il check
        # darebbe un falso "loggato".
        login_verified = False

        while time.time() - self._start_time < self._dynamic_timeout:
            if not self.window or self._stopped:
                break
            if self._consume_reload_requested():
                self._log("Rilevato reload di Gemini: reset del ciclo corrente e nuova attesa della pagina pronta.")
                injected = False
                send_clicked = False
                verify_start_time = 0
                image_ready = False
                last_progress_at = time.time()
                time.sleep(1)
                continue

            ready = self._safe_evaluate_js(get_js_check_ready())
            if self._stopped:
                break
            if not ready:
                if time.time() - last_progress_at > 90 and time.time() - self._last_reload_at > 20:
                    self._last_reload_at = time.time()
                    self._log("Pagina non pronta da troppo tempo: provo reload e riprendo l'automazione.")
                    try:
                        self.window.load_url(self.site.url)
                    except Exception as exc:
                        self._log(f"Reload fallito: {exc}")
                    injected = False
                    send_clicked = False
                    verify_start_time = 0
                    image_ready = False
                    time.sleep(2)
                time.sleep(self.POLLING_INTERVAL)
                continue
            last_ready_at = time.time()
            last_progress_at = time.time()

            # Pagina pronta: ora il DOM e' attendibile, si può giudicare il login.
            # Senza questo controllo l'automator andrebbe avanti comunque e
            # finirebbe con un timeout generico ("nessuna risposta"), che fa
            # sembrare un problema di selettori mentre il sito non è proprio
            # aperto. Il consenso GDPR era già gestito in _on_loaded, il login no.
            if not login_verified:
                login_verified = True
                if not (self._check_logged_in() and self._on_site_page()):
                    # Non chiudere subito: l'utente deve avere il tempo di
                    # digitare email e password. La finestra resta aperta e si
                    # aspetta fino a 5 minuti, come fa la sonda. Solo allo
                    # scadere si chiude e si fallisce.
                    self._log(
                        f"{self.site.label} non risulta loggato. Accedi nella "
                        "finestra: attendo fino a 5 minuti, poi procedo da solo. "
                        "Nessun testo e' stato inviato finora."
                    )
                    limite = time.time() + 300
                    loggato = False
                    while time.time() < limite:
                        if not self.window or self._stopped:
                            return
                        time.sleep(3)
                        if self._check_logged_in() and self._on_site_page():
                            loggato = True
                            break
                    if not loggato:
                        self._log(
                            f"Login non completato entro 5 minuti su "
                            f"{self.site.label}: chiudo senza inviare nulla."
                        )
                        # webview.start() blocca fino alla distruzione della
                        # finestra: senza chiuderla translate_blocks non
                        # tornerebbe mai e l'app resterebbe congelata.
                        # Chiamo _close_window() e basta: imposta lui stesso
                        # _stopped, quindi impostarlo prima qui farebbe uscire
                        # il metodo senza distruggere nulla.
                        self._close_window()
                        return
                    self._log("Login rilevato, procedo con la traduzione.")

            if self._pending_image_path and not image_ready:
                image_ready = self._inject_image_if_needed()
                if self._image_injection_failed:
                    self._log("Arresto automazione GVB: impossibile agganciare l'immagine all'input Gemini.")
                    self._close_window()
                    break
                time.sleep(0.5)
                continue

            if not injected:
                self._log("Area di input trovata. Iniezione prompt...")
                js_text_string = json.dumps(self._prompt_text)
                success = self._safe_evaluate_js(get_js_inject(js_text_string))
                if self._stopped:
                    break
                if success:
                    injected = True
                    verify_start_time = time.time()
                    last_progress_at = time.time()
                    self._log("Prompt iniettato. Verifica inserimento...")
            elif verify_start_time > 0:
                verified = self._safe_evaluate_js(get_js_verify_input())
                if self._stopped:
                    break
                if verified:
                    self._log("Testo verificato nell'input. Attesa del pulsante Invia...")
                    verify_start_time = 0
                    last_progress_at = time.time()
                else:
                    elapsed = time.time() - verify_start_time
                    self._log(f"Testo non ancora visibile nell'input (verifica da {elapsed:.1f}s)...")
                    time.sleep(0.5)
            elif not send_clicked:
                send_ready = self._safe_evaluate_js(get_js_wait_for_send_button())
                if self._stopped:
                    break
                if send_ready:
                    send_clicked = True
                    last_progress_at = time.time()
                    self._log("Pulsante Invia cliccato. In attesa della risposta JSON...")
                else:
                    self._log("Pulsante Invia non trovato, riprovo...")
            else:
                result_data = self._safe_evaluate_js(get_js_extract(self._expected_count, self._keyed_json_mode))
                if self._stopped:
                    break
                if result_data and result_data not in ["NOT_FINISHED", "JSON_NOT_FOUND", "INCOMPLETE_JSON", "INVALID_JSON"]:
                    translations, report = parse_translation_payload(result_data, self._expected_count)
                    if self._keyed_json_mode and "block_1" in translations:
                        self._finalize_translation_success(translations, report)
                        break
                    if report.get("is_valid") and "block_1" in translations:
                        self._finalize_translation_success(translations, report)
                        break
                    if translations:
                        self._handle_terminal_json_error(result_data, translations, report)
                        break
                    self._log(
                        "JSON non recuperabile dal DOM. "
                        f"source={report.get('source')} error={report.get('error')}"
                    )
                elif result_data == "NOT_FINISHED":
                    self._log("Generazione in corso...")
                    last_progress_at = time.time()
                elif result_data == "INCOMPLETE_JSON":
                    self._log(f"JSON incompleto (attesi {self._expected_count} blocchi). Attendo...")
                    last_progress_at = time.time()
                else:
                    if self._capture_image:
                        self._log("Modalità clean image attiva. Provo la cattura dell'immagine dalla risposta...")
                        clicked = guarded_copy_response(self.window, self._log)
                        if clicked:
                            self.copied_image = True
                            self._log("Click validato su bottone copia della risposta immagine.")
                            time.sleep(1)
                            self._close_window()
                            break
                        self._log("Bottone copia immagine non ancora pronto.")
                        time.sleep(self.POLLING_INTERVAL)
                        continue
                    self._log(f"Stato: {result_data}. Avvio la guardia esplicita su un bottone copia valido della risposta...")
                    clicked = guarded_copy_response(self.window, self._log)
                    if clicked:
                        last_progress_at = time.time()
                        self._log("Click validato su bottone copia della risposta. Verifico subito la clipboard...")
                        time.sleep(0.6)
                        clipboard_result = extract_keyed_json_from_clipboard() if self._keyed_json_mode else extract_translations_from_clipboard(self._expected_count)
                        if clipboard_result:
                            report = {
                                "is_valid": True,
                                "total_found": len(clipboard_result),
                                "source": "clipboard",
                            }
                            self._finalize_translation_success(clipboard_result, report)
                            break
                        self._log("Clipboard non ancora valida. Attendo il prossimo ciclo per l'estrazione...")
                    else:
                        self._log("Guardia copia fallita: il bottone corretto non e' ancora pronto o resta ambiguo.")

            time.sleep(self.POLLING_INTERVAL)

        if time.time() - self._start_time >= self._dynamic_timeout:
            self._log(f"Timeout: Rilevamento fallito dopo {self._dynamic_timeout}s.")
            self._close_window()

    def translate_blocks(self, blocks: List[Dict], full_text: str, expected_count: int = 0,
                        source_lang: str = 'en', target_lang: str = 'it',
                        progress_callback: Optional[Callable] = None) -> Dict[str, str]:
        self._blocks = blocks
        self._full_text = full_text
        self._expected_count = expected_count
        self._progress_callback = progress_callback
        self.translations = {}
        self._stopped = False
        self._automation_started = False
        self._image_injection_failed = False
        self._pending_image_path, self._prompt_text = self._extract_image_path(full_text)
        self._capture_image, self._prompt_text = self._extract_capture_mode(self._prompt_text)
        self._keyed_json_mode, self._prompt_text = self._extract_keyed_json_mode(self._prompt_text)
        self.copied_image = False
        self._reload_requested = False
        if not self._maybe_prepare_image():
            return {}
        if not self._prompt_text.strip():
            self._prompt_text = full_text.strip()
        print(f"[{self.site.label} Automator] Using persistent storage: {self._storage_path}")
        self.window = webview.create_window(
            f"{self.site.label} Auto-Translator",
            self.site.url,
            width=1100,
            height=850,
            resizable=True
        )
        self.window.events.loaded += self._on_loaded
        webview.start(
            storage_path=self._storage_path,
            debug=False,
            private_mode=False,
            http_server=True,
            http_port=18765
        )
        if not self.translations and not self._image_injection_failed:
            clipboard_result = extract_keyed_json_from_clipboard() if self._keyed_json_mode else extract_translations_from_clipboard(self._expected_count)
            if clipboard_result:
                if self._keyed_json_mode:
                    self._log(f"Recupero finale keyed da clipboard riuscito. Blocchi trovati: {len(clipboard_result)}")
                else:
                    self._log(f"Recupero finale da clipboard riuscito. Blocchi trovati: {len(clipboard_result)}/{self._expected_count}")
                self.translations = clipboard_result
        return self.translations

    def stop(self):
        self._close_window()
        self.window = None


def create_gemini_automator(site_key=None) -> GeminiAutomator:
    """Crea l'automator per un sito browser.

    site_key=None (o 'TXT') -> Gemini, quindi il comportamento di sempre.
    Passa la chiave di un altro sito ('Dola') per pilotarlo.
    """
    site = get_site(site_key) if site_key else None
    if site is None:
        site = GEMINI
    return GeminiAutomator(site)
