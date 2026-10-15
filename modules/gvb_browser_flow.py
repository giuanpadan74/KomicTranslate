import json
import time
from PySide6 import QtCore

from app.ui.messages import Messages
from modules.gemini_browser_pipeline.pywebview_session import PyWebviewSession


class GvbBrowserFlow:
    def __init__(self, host, upload_service):
        self.host = host
        self.upload_service = upload_service

    def open_with_image(self, image_path: str, on_closed, prompt_text: str | None = None):
        return self.host.open_simple_gemini_browser(
            return_window=True,
            on_loaded=lambda window: self._attach_image(image_path, prompt_text, window),
            on_closed=on_closed,
        )

    def _on_window_closed(self, callback):
        self.host._active_gvb_window = None
        if callback is not None:
            callback()

    def _attach_image(self, image_path: str, prompt_text: str | None, window):
        if window is None:
            return
        session = PyWebviewSession(window=window)
        self._run_attach(session, image_path, prompt_text)

    def _run_attach(self, session: PyWebviewSession, image_path: str, prompt_text: str | None):
        # ── Passo 1: Carica l'immagine (stesso codice di prima, invariato) ──
        result = self.upload_service.attach_image(session, image_path)
        print(f"[GVB DEBUG] attach_image result: {result}")
        image_ok = bool(result.get('success'))
        if not image_ok:
            QtCore.QTimer.singleShot(
                0,
                lambda: Messages.show_warning(
                    self.host,
                    'Caricamento manuale richiesto',
                    'Il caricamento automatico della regione non è riuscito. Puoi comunque allegarla manualmente in GVB.',
                ),
            )
            # Se non carica l'immagine, non ha senso procedere oltre
            return

        # ── Punto di sincronizzazione: aspetta un CAMBIAMENTO di stato.
        #    Se attach_image ha già confermato status=loaded, max 3 secondi.
        #    Altrimenti (caso di fallback) 20s.
        from modules.gvb_scripts import get_js_has_image_attachment

        # Timeout intelligente basato sull'esito dell'upload vero e proprio
        upload_confirmed = bool(
            result.get('success') and result.get('status') == 'loaded'
        )
        timeout_s = 3.0 if upload_confirmed else 20.0
        delay_s = 0.15 if upload_confirmed else 0.2
        print(f"[GVB DEBUG] Timeout sincronizzazione immagine: {timeout_s}s (upload_confirmed={upload_confirmed})")

        def _parse_state(value):
            if value is None:
                return {'ok': False, 'count': 0, 'marker': 'none'}
            if isinstance(value, dict):
                return {
                    'ok': bool(value.get('ok')),
                    'count': int(value.get('count') or 0),
                    'marker': value.get('marker') or 'none',
                }
            if isinstance(value, str):
                s = value.strip().lower()
                if s == 'true':
                    return {'ok': True, 'count': 1, 'marker': 'fallback_true'}
                if s.startswith('{'):
                    try:
                        import json as _json
                        parsed = _json.loads(value)
                        if isinstance(parsed, dict):
                            return {
                                'ok': bool(parsed.get('ok')),
                                'count': int(parsed.get('count') or 0),
                                'marker': parsed.get('marker') or 'none',
                            }
                    except Exception:
                        pass
                return {'ok': False, 'count': 0, 'marker': 'str_other'}
            if value is True:
                return {'ok': True, 'count': 1, 'marker': 'bool_true'}
            return {'ok': False, 'count': 0, 'marker': 'other'}

        # Stato iniziale (prima dell'upload paste, per confronto)
        try:
            _initial_raw = session.run_js(get_js_has_image_attachment())
        except Exception:
            _initial_raw = None
        initial = _parse_state(_initial_raw)
        print(f"[GVB DEBUG] Stato iniziale allegati: ok={initial['ok']} count={initial['count']} marker={initial['marker']}")

        img_attached = False
        deadline = time.time() + timeout_s
        tent = 0
        while time.time() < deadline:
            tent += 1
            try:
                cur_raw = session.run_js(get_js_has_image_attachment())
            except Exception:
                cur_raw = None
            cur = _parse_state(cur_raw)

            # Caso 1: transizione classica False → True
            if (not initial['ok']) and cur['ok']:
                print(f"[GVB DEBUG] ✓ Transizione ok (False→True) al tentativo {tent}: marker={cur['marker']} count={cur['count']}")
                img_attached = True
                break

            # Caso 2: inizialmente c'era già qualcosa ma il conteggio è aumentato
            if initial['ok'] and cur['ok'] and cur['count'] > initial['count']:
                print(f"[GVB DEBUG] ✓ Count aumentato al tentativo {tent}: {initial['count']}→{cur['count']} marker={cur['marker']}")
                img_attached = True
                break

            time.sleep(delay_s)

        print(f"[GVB DEBUG] Fine attesa: img_attached={img_attached} dopo {tent} tentativi")
        if not img_attached:
            print(f"[GVB DEBUG] WARNING: nessuna IMMAGINE NUOVA rilevata nel composer entro {int(timeout_s)}s, procedo comunque.")

        # ── Passo 2: Inietta il prompt di testo (se presente) ──
        prompt_ok = False
        if prompt_text and prompt_text.strip():
            prompt_ok = self._inject_prompt(session, prompt_text)
            print(f"[GVB DEBUG] inject_prompt result: {prompt_ok}")
            if not prompt_ok:
                QtCore.QTimer.singleShot(
                    0,
                    lambda: Messages.show_warning(
                        self.host,
                        'Prompt non inserito',
                        'Non è stato possibile inserire automaticamente il prompt. Puoi comunque incollarlo manualmente in Gemini.',
                    ),
                )

        # ── Passo 3: Premi il pulsante di Invio ──
        self._wait_and_click_send(session)

    def _inject_prompt(self, session: PyWebviewSession, prompt_text: str, attempts: int = 4, delay: float = 0.15) -> bool:
        """Inietta il prompt nel campo di input di Gemini.
        Veloce: max 4 tentativi × 0.15s = 0.6s worst case.
        Se una strategia ritorna True, usciamo SUBITO senza verify ridondanti.
        """
        from modules.gvb_scripts import get_js_focus_composer, get_js_inject_text

        # ── Strategia 0: focus composer PRIMA di tutto ──
        try:
            session.run_js(get_js_focus_composer())
        except Exception:
            pass

        # ── Strategia 1: inject_prompt() nativo PyWebviewSession (più veloce) ──
        for _ in range(2):
            try:
                if hasattr(session, "inject_prompt") and session.inject_prompt(prompt_text):
                    print(f"[GVB DEBUG] Prompt OK (strategia 1: nativo)")
                    return True
            except Exception:
                pass
            time.sleep(max(0.05, float(delay)))

        # ── Strategia 2: setter diretto contenteditable/textarea ──
        for _ in range(max(1, int(attempts) - 2)):
            try:
                injected = session.run_js(get_js_inject_text(prompt_text))
                if injected is True or str(injected).lower() == "true":
                    print(f"[GVB DEBUG] Prompt OK (strategia 2: setter)")
                    return True
            except Exception:
                pass
            time.sleep(max(0.05, float(delay)))

        print("[GVB DEBUG] Prompt fallito dopo tutti i tentativi.")
        return False

    def _wait_and_click_send(self, session: PyWebviewSession, max_attempts: int = 20, delay: float = 0.5):
        """Attende che il pulsante Invia sia disponibile e lo clicca.

        3 strategie, nello stesso ordine della versione originale "funzionante":
        1) JS avanzato vicino al composer (icona svgicon=send)
        2) upload_service.click_send_button
        3) click_send() nativo della sessione
        """
        from modules.gemini_scripts import get_js_wait_for_send_button

        for attempt in range(max_attempts):
            try:
                r1 = session.run_js(get_js_wait_for_send_button())
                if r1 is True or str(r1).lower() == "true":
                    print(f"[GVB DEBUG] Pulsante Invia cliccato con strategia 1 (vicino composer) al tentativo {attempt + 1}")
                    return
            except Exception as e:
                print(f"[GVB DEBUG] strategia1 click_send eccezione: {e}")

            try:
                if self.upload_service.click_send_button(session):
                    print(f"[GVB DEBUG] Pulsante Invia cliccato con strategia 2 (upload_service) al tentativo {attempt + 1}")
                    return
            except Exception as e:
                print(f"[GVB DEBUG] strategia2 click_send eccezione: {e}")

            try:
                if hasattr(session, "click_send") and session.click_send():
                    print(f"[GVB DEBUG] Pulsante Invia cliccato con strategia 3 (nativo) al tentativo {attempt + 1}")
                    return
            except Exception as e:
                print(f"[GVB DEBUG] strategia3 click_send eccezione: {e}")

            time.sleep(delay)
        print("[GVB DEBUG] Pulsante Invia non trovato dopo tutti i tentativi")
