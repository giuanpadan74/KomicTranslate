"""Sonda diagnostica per i siti browser.

Stampa cosa trova realmente nella pagina, cosi da correggere i selettori in
modules/browser_sites/<sito>.py senza dover indovinare.

Uso:
    python -m modules.browser_sites.probe Gemini
    python -m modules.browser_sites.probe Dola

Apre il sito in una finestra pywebview reale, sullo STESSO profilo
persistito che usa l'automator (percorso condiviso, vedi
get_site_storage_path). NON incolla niente e NON invia niente: si limita a
guardare la pagina. Scrive pero' un testo finto nel composer, perche' con
il campo vuoto il pulsante di invio non viene ne' creato ne' abilitato, e
"send non trovato" su una pagina vuota non dice nulla sui selettori.

Se il sito chiede il login, accedi a mano nella finestra: la sessione
viene salvata e la troveranno sia la sonda sia l'app.
"""
import sys
import json


PROBE_JS = r"""
(() => {
  const pick = (sels) => {
    for (const s of sels) {
      try {
        const el = document.querySelector(s);
        if (el) {
          return {
            selector: s,
            tag: el.tagName.toLowerCase(),
            cls: (el.className || '').toString().slice(0, 90),
            text: (el.innerText || el.value || '').trim().slice(0, 120),
            contenteditable: el.getAttribute('contenteditable'),
            role: el.getAttribute('role'),
          };
        }
      } catch (e) { /* selettore non valido: prova il prossimo */ }
    }
    return null;
  };

  const count = (sels) => sels.map(s => {
    try { return [s, document.querySelectorAll(s).length]; } catch (e) { return [s, -1]; }
  });

  const sel = window.__PROBE_SELECTORS__;
  // Login? Servono tre segnali, uno solo non basta: la pagina di login di
  // Google (accounts.google.com) non ha alcun bottone "Accedi" ma un campo
  // email + "Avanti", quindi contare i bottoni dava un falso "loggato" e la
  // sonda non aspettava il login manuale.
  const accedi = Array.from(document.querySelectorAll('button, a'))
    .filter(b => /^(Accedi|Sign in|Log in)$/i.test((b.innerText || '').trim()))
    .length;
  const suPaginaLogin = /accounts\.google\.com/i.test(location.href);
  const campoEmail = document.querySelector('input[type="email"]') !== null;

  const out = {
    url: location.href,
    title: document.title,
    logged_in: accedi === 0 && !suPaginaLogin && !campoEmail,
    login_buttons: accedi,
    login_page: suPaginaLogin,
    email_field: campoEmail,
    composer: pick(sel.composer),
    send: pick(sel.send),
    response: pick(sel.response),
    copy: pick(sel.copy_response),
    stop: pick(sel.stop),
    counts: {
      composer: count(sel.composer),
      response: count(sel.response),
      textarea: document.querySelectorAll('textarea').length,
      contenteditable: document.querySelectorAll('[contenteditable="true"]').length,
      buttons: document.querySelectorAll('button').length,
    },
    // Bottone-trova: aiuta a capire quale sia il submit vero. Il pulsante
    // di invio sta vicino al composer, cioe' a fine DOM: stampare solo i
    // primi N mostrava la sidebar e nascondeva quello che serve. Si stampano
    // testa + coda con indice, piu' i candidati che sembrano un invio
    // (IT/EN/FR/ES/DE/ZH: Dola ha aria-label anche in cinese).
    buttons: (() => {
      const all = Array.from(document.querySelectorAll('button')).map((b, i) => ({
        i: i,
        text: (b.innerText || '').trim().slice(0, 40),
        aria: b.getAttribute('aria-label') || '',
        type: b.getAttribute('type') || '',
        cls: (b.className || '').toString().slice(0, 60),
        disabled: b.disabled,
      }));
      const eInvio = (b) => /invia|send|submit|envoyer|enviar|trasmett|mand[ao]|run|发送|提交/i.test(b.text + ' ' + b.aria);
      return {
        total: all.length,
        head: all.slice(0, 8),
        tail: all.slice(-25),
        send_candidates: all.filter(eInvio),
      };
    })(),
    // Cerca il pulsante vicino al composer. Salire di livello non funziona:
    // gli antenati contengono anche la sidebar e non si scende mai sotto i 20
    // cliccabili. Si guarda invece cosa SEGUE il composer nel DOM: l'invio sta
    // quasi sempre dopo il campo. Include anche non-<button> (role=button,
    // icone SVG senza etichetta). In piu' stampa la catena degli antenati.
    near_composer: (() => {
      const comp = (() => {
        for (const s of sel.composer) {
          try { const el = document.querySelector(s); if (el) return el; } catch (e) {}
        }
        return null;
      })();
      if (!comp) return { error: 'composer non trovato' };
      const chain = [];
      let p = comp;
      for (let k = 0; k < 5 && p && p !== document.body; k++) {
        p = p.parentElement;
        if (!p) break;
        chain.push(p.tagName.toLowerCase() + '.' + (p.className || '').toString().split(/\s+/).slice(0, 3).join('.'));
      }
      // Distanza ad albero dal composer: trova il cliccabile piu' vicino in
      // qualunque direzione, senza presumere che stia dopo il campo.
      const anc = (el) => { const c = []; let x = el; while (x && x !== document.body) { c.push(x); x = x.parentElement; } return c; };
      const chainC = anc(comp);
      const setC = new Set(chainC);
      const dist = (el) => {
        let x = el, d = 0;
        while (x && x !== document.body && !setC.has(x)) { x = x.parentElement; d++; }
        if (!x || x === document.body) return 999;
        return d + chainC.indexOf(x);
      };
      const pos = (el) => (comp.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING ? 'after' : 'before');
      const cand = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'));
      const near = cand.map(b => ({
        d: dist(b),
        pos: pos(b),
        text: (b.innerText || '').trim().slice(0, 40),
        aria: b.getAttribute('aria-label') || '',
        role: b.getAttribute('role') || '',
        type: b.getAttribute('type') || '',
        tag: b.tagName.toLowerCase(),
        cls: (b.className || '').toString().slice(0, 80),
        kids: Array.from(b.children).map(c => c.tagName.toLowerCase()).join(','),
        disabled: !!b.disabled,
        html: (b.outerHTML || '').slice(0, 300),
      })).sort((a, b) => a.d - b.d).slice(0, 10);
      return { ancestor_chain: chain, nearest_clickables: near };
    })(),
  };
  return JSON.stringify(out);
})()
"""


# Scrive un testo finto nel composer SENZA inviare. Serve perche' molti siti
# creano il pulsante di invio solo quando il campo ha contenuto: su una pagina
# vuota "send non trovato" e' il risultato atteso, e non distingue un selettore
# sbagliato da un pulsante semplicemente non renderizzato.
PROBE_FILL_JS = r"""
(() => {
  const sels = window.__PROBE_SELECTORS__.composer;
  for (const s of sels) {
    try {
      const el = document.querySelector(s);
      if (!el) continue;
      el.focus();
      const testo = 'test';
      if (el.isContentEditable) {
        el.textContent = testo;
        el.dispatchEvent(new InputEvent('input', { bubbles: true }));
      } else if ('value' in el) {
        el.value = testo;
        el.dispatchEvent(new Event('input', { bubbles: true }));
      } else {
        continue;
      }
      return JSON.stringify({ ok: true, selector: s, mode: el.isContentEditable ? 'contenteditable' : 'value' });
    } catch (e) { /* prova il selettore successivo */ }
  }
  return JSON.stringify({ ok: false, error: 'nessun composer utilizzabile' });
})()
"""


# Controllo leggero: serve solo per sapere se il login e' avvenuto, senza
# ristampare l'intera sonda a ogni poll.
LOGIN_JS = r"""
(() => {
  const accedi = Array.from(document.querySelectorAll('button, a'))
    .filter(b => /^(Accedi|Sign in|Log in)$/i.test((b.innerText || '').trim()))
    .length;
  const suPaginaLogin = /accounts\.google\.com/i.test(location.href);
  const campoEmail = document.querySelector('input[type="email"]') !== null;
  return JSON.stringify({
    logged_in: accedi === 0 && !suPaginaLogin && !campoEmail,
    login_buttons: accedi
  });
})()
"""

# Svuota il composer, cosi' la sonda lascia la pagina come l'ha trovata.
PROBE_CLEAR_JS = r"""
(() => {
  const sels = window.__PROBE_SELECTORS__.composer;
  for (const s of sels) {
    try {
      const el = document.querySelector(s);
      if (!el) continue;
      el.focus();
      if (el.isContentEditable) { el.textContent = ''; }
      else if ('value' in el) { el.value = ''; }
      else { continue; }
      el.dispatchEvent(new InputEvent('input', { bubbles: true }));
      return 'ok';
    } catch (e) { /* prova il selettore successivo */ }
  }
  return 'ko';
})()
"""


def main(argv):
    site_key = argv[1] if len(argv) > 1 else "Gemini"
    sys.path.insert(0, ".")
    from modules.browser_sites import get_site

    site = get_site(site_key)
    if site is None:
        print(f"Sito sconosciuto: {site_key}")
        print("Disponibili:")
        from modules.browser_sites import site_keys
        for k in site_keys():
            print("  -", k)
        return 2

    import webview
    selectors = {
        "composer": site.composer,
        "send": site.send,
        "response": site.response,
        "copy_response": site.copy_response,
        "stop": site.stop,
    }
    js = "window.__PROBE_SELECTORS__ = " + json.dumps(selectors) + ";\n" + PROBE_JS

    print(f"=== Sonda: {site.label} ===")
    print(f"URL: {site.url}")

    # Stesso profilo dell'automator. Senza questo la sonda parte da una
    # sessione vuota e non vedrebbe mai un login fatto nell'app, e viceversa.
    from modules.gemini_automator import get_site_storage_path
    storage_path = get_site_storage_path(site)
    print(f"Profilo: {storage_path}")
    print("Se compare il login, accedi a mano: la sessione viene salvata e")
    print("vale sia per questa sonda sia per l'app. Poi rilancia la sonda.")
    print()

    win = webview.create_window(f"Sonda {site.label}", site.url, width=1200, height=900)

    _gia_partito = {"fatto": False}

    def _chiudi(w):
        try:
            w.destroy()
        except Exception:
            pass

    def _sonda(w, script):
        raw = w.evaluate_js(script)
        return json.loads(raw) if isinstance(raw, str) else (raw or {})

    def valuta(data, titolo):
        print(f"--- verdetto: {titolo} ---")
        print(f"  loggato:   {data.get('logged_in')}   (bottoni 'Accedi': {data.get('login_buttons')}"
              f", pagina login: {data.get('login_page')}, campo email: {data.get('email_field')})")
        print(f"  composer:  {bool(data.get('composer'))}")
        print(f"  send:      {bool(data.get('send'))}")
        print(f"  response:  {bool(data.get('response'))}")
        print(f"  copy:      {bool(data.get('copy'))}")
        print(f"  stop:      {bool(data.get('stop'))}")

    def on_loaded():
        try:
            vuoto = _sonda(win, js)

            print("=" * 60)
            print("1) CAMPO VUOTO")
            print("=" * 60)
            print(json.dumps(vuoto, indent=2, ensure_ascii=False))
            print()
            valuta(vuoto, "campo vuoto")

            if not vuoto.get("logged_in"):
                print()
                print(">> La pagina NON e' loggata.")
                print("   Accedi a mano nella finestra: resta aperta fino a 5")
                print("   minuti e riprovo da sola ogni 2 secondi.")

                import time as _t
                limite = _t.time() + 300
                loggato = False
                while _t.time() < limite:
                    _t.sleep(2.0)
                    try:
                        raw = win.evaluate_js(LOGIN_JS)
                        st = json.loads(raw) if isinstance(raw, str) else (raw or {})
                    except Exception:
                        continue
                    if st.get("logged_in"):
                        loggato = True
                        break
                if not loggato:
                    print()
                    print(">> Timeout: login non completato. Chiudo.")
                    print("   Una volta loggato, rilancia la sonda: la sessione")
                    print("   e' salvata e non si ricomincia da capo.")
                    return
                print()
                print(">> Login rilevato. Lascio assestare la pagina...")
                _t.sleep(3.0)
                vuoto = _sonda(win, js)
                print()
                valuta(vuoto, "campo vuoto, dopo il login")

            # Seconda passata: con testo nel composer il pulsante di invio
            # viene creato/abilitato, e il selettore e' finalmente testabile.
            print()
            print("(scrive 'test' nel composer, NON invia)")
            raw_fill = win.evaluate_js(
                "window.__PROBE_SELECTORS__ = " + json.dumps(selectors) + ";\n" + PROBE_FILL_JS)
            fill = json.loads(raw_fill) if isinstance(raw_fill, str) else raw_fill
            print(f"    riempimento: {fill}")

            import time
            time.sleep(1.2)

            pieno = _sonda(win, js)
            print()
            print("=" * 60)
            print("2) CAMPO CON TESTO")
            print("=" * 60)
            print(json.dumps(pieno, indent=2, ensure_ascii=False))
            print()
            valuta(pieno, "campo con testo")

            # Stessa intestazione delle altre chiamate: senza, se la pagina
            # ha ricaricato nel frattempo __PROBE_SELECTORS__ non esiste piu'
            # e la pulizia fallirebbe in silenzio lasciando 'test' nel campo.
            win.evaluate_js(
                "window.__PROBE_SELECTORS__ = " + json.dumps(selectors) + ";\n" + PROBE_CLEAR_JS)
            print("\n(compositore svuotato: la pagina e' come l'ho trovata)")

            print()
            print("--- come leggere questi due risultati ---")
            if not pieno.get("send"):
                print("  send assente anche con il campo pieno: il pulsante non c'e'.")
                print("  Guarda 'buttons.send_candidates' e 'buttons.tail' qui sopra")
                print("  per il suo aria-label reale e correggi il selettore in")
                print("  modules/browser_sites/<sito>.py.")
            else:
                print("  send trovato: la parte di scrittura e' a posto.")
            if not pieno.get("response"):
                print("  response assente: su una sessione nuova non ci sono ancora")
                print("  risposte da leggere. NON e' un selettore sbagliato: per")
                print("  verificarlo serve una chat con almeno una risposta.")
        except Exception as e:
            print(f"Sonda fallita: {e}")
        finally:
            _chiudi(win)

    def on_loaded_finished():
        # 'loaded' scatta a ogni navigazione, e il login di Google ne provoca
        # almeno una: senza questo blocco partirebbe una seconda sonda che
        # chiuderebbe la finestra sotto la prima, che sta ancora leggendo
        # i risultati. La sonda deve girare una volta sola.
        if _gia_partito.get("fatto"):
            return
        _gia_partito["fatto"] = True

        # attende un po' che il rendering si assesti, poi sonda
        import threading
        import time

        def later():
            time.sleep(2.5)
            on_loaded()

        threading.Thread(target=later, daemon=True).start()

    win.events.loaded += on_loaded_finished

    # storage_path: senza, la sonda usa un profilo temporaneo e non vede il
    # login dell'automator. Stessi parametri dell'automator, cosi' i due
    # condividono davvero la sessione. Se il profilo e' gia' in uso da un
    # altro processo (app aperta) webview.start solleva: va segnalato, non
    # ignorato, altrimenti la sonda "non funziona" senza dirlo.
    try:
        webview.start(storage_path=storage_path)
    except Exception as e:
        print(f"\nNon e' stato possibile aprire il profilo condiviso: {e}")
        print("Se KomicTranslate e' aperto, chiudilo e rilancia la sonda.")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))