import json
import time
from typing import Any, Callable, Dict

from modules.gemini_response_scripts import (
    get_js_click_response_copy,
    get_js_copy_response_state,
)

COPY_WAIT_TIMEOUT = 25.0
COPY_POLL_INTERVAL = 0.5
COPY_RETRY_COUNT = 6


def _parse_js_result(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"status": "invalid_payload", "raw": raw}
    return {"status": "invalid_payload", "raw": repr(raw)}


def guarded_copy_response(window: Any, log: Callable[[str], None]) -> bool:
    deadline = time.time() + COPY_WAIT_TIMEOUT
    last_state: Dict[str, Any] = {}

    while time.time() < deadline:
        try:
            last_state = _parse_js_result(window.evaluate_js(get_js_copy_response_state()))
        except Exception as exc:
            log(f"Errore evaluate_js durante copy-state: {exc}. Riprovo...")
            time.sleep(COPY_POLL_INTERVAL)
            continue
        if last_state.get("ready"):
            break
        if last_state.get("image_menu_item_found"):
            log("Rilevata voce 'Copia immagine' nel menu contestuale: provo la copia dell'immagine.")
        elif last_state.get("more_button_found"):
            log("Rilevato pulsante 'Altro': provo ad aprire il menu per cercare 'Copia immagine'.")
        elif last_state.get("prompt_button_visible") and not last_state.get("exact_response_match"):
            log("Rilevato solo 'Copia prompt': attendo 'Copia risposta', 'Copia codice', 'Copia risultato' o 'Copia immagine'.")
        elif last_state.get("generic_copy_match") and not last_state.get("exact_response_match"):
            log("Rilevato un bottone copia icon-only associato alla risposta: provo ad attenderne la stabilizzazione.")
        elif last_state.get("exact_response_match") and not last_state.get("response_has_useful_content"):
            log("Bottone copia risposta individuato ma il contenuto della risposta non sembra ancora pronto.")
        time.sleep(COPY_POLL_INTERVAL)
    else:
        log(f"Timeout in attesa di un bottone copia valido della risposta: {last_state}")
        return False

    for attempt in range(1, COPY_RETRY_COUNT + 1):
        try:
            click_state = _parse_js_result(window.evaluate_js(get_js_click_response_copy()))
        except Exception as exc:
            log(f"Errore evaluate_js durante click-copia: {exc}. Retry {attempt}/{COPY_RETRY_COUNT}.")
            time.sleep(COPY_POLL_INTERVAL)
            continue
        if (
            click_state.get("status") == "clicked"
            and click_state.get("post_click_valid")
            and not click_state.get("exact_prompt_match")
        ):
            labels = click_state.get("labels") or []
            log(f"Click validato su bottone copia risposta {labels} al tentativo {attempt}.")
            return True
        log(f"Click ambiguo su copia, retry {attempt}/{COPY_RETRY_COUNT}: {click_state}")
        time.sleep(COPY_POLL_INTERVAL)

    return False
