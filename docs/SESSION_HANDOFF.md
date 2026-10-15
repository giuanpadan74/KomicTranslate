# Handoff sessione — KomicTranslate (2026-10-06)

Leggimi per primo in una sessione nuova. Contesto operativo del progetto, decisioni bloccate, lavori aperti.

## Stato verificato

- App PySide6 + ML, solo Windows. Root `E:\KomicTranslate`, entry `comic.py`, Python 3.12, venv `.venv`.
- Net-installer fasi 1-7 COMPLETE + RELEASE 1.0.0 compilata (2026-10-07):
  `E:\sicuro\release\KomicTranslate-Setup-1.0.0.exe` (15,6 MB, chiave privata
  offline in `E:\sicuro\komic-sign.key`, MAI nel repo). Release GitHub:
  `github.com/giuanpadan74/KomicTranslate/releases/download/v1.0.0/app-v1.0.0.zip`
  (zip 4.14 MB). Riferimenti ComicLabs->giuanpadan74 in bootstrap.py e .iss.
- Suite: 153 test, 2/3 run verdi; 1 run con 1 failure non identificato
  (log encoding, non riprodotto: probabile flaky su timing/server locale).
- `compileall` pulito.

## Decisioni bloccate

1. Traduttori: `Gemini` (sito browser, ex TXT) + `geminiamo` (cookie Firefox, serve Firefox) visibili; **Dola nascosta** (`hidden=True` in `modules/browser_sites/dola.py`) finché invio/risposta non sono verificati.
2. Chiave config legacy `TXT` → si risolve in `Gemini` ovunque (value_mappings, factory, processor). Chiave persistenza prompt `txt_prompt` e costante `TXT_PROMPT_DEFAULT` NON rinominare (compatibilità config salvati).
3. Registry siti in `modules/browser_sites/` (`base.py`, `__init__.py`, `gemini.py`, `dola.py`, `probe.py`). Aggiungere un sito = un file + una riga. Percorso profilo webview unico in `gemini_automator.get_site_storage_path`, condiviso con la sonda.
4. Installer: **net-installer** (installer piccolo + bootstrapper che scarica tutto), pesi modello in download, GPU auto-detect (torch CPU poi swap cu121 se NVIDIA). Spec in `docs/INSTALLER_BOOTSTRAPPER_SPEC.md` — ESEGUITA fasi 1-7.
5. `requirements.txt` curato: solo pacchetti importati. `modules/ocr/easy_ocr.py` è morto (zero riferimenti) ma ancora presente: cancellabile.
6. Lingua di lavoro: italiano. Regola: verifiche empiriche, mai speculazioni; se uno strumento manca, dirlo.
7. installer/ e' solo-stdlib (gira su python-embed). Ed25519 puro verificato
   contro `cryptography`+PyCryptodome (formula twisted: y3 con `+`).
8. python-embed NON ha venv/ensurepip: venv manuale (exe+dll+pyvenv.cfg) +
   get-pip bundlato (provato: pip --require-hashes offline ok).
9. WebView2 check: HKLM+HKCU, viste 64+32 bit (su questa macchina pv 154.0.4258.53
   solo in WOW6432Node). Questa macchina: NVIDIA RTX 3060, torch.cuda True.
10. Chiave privata Ed25519 OFFLINE mai nel repo; pubblica iniettata dal build.
    Inno Setup 6.7 per-utente (`%LOCALAPPDATA%\Programs\Inno Setup 6`,
    rilevato dal build). Setup DEV compilato e provato il 2026-10-07:
    `kt-output\KomicTranslate-Setup-1.0.0.exe` (15,6 MB, chiave effimera,
    NON distribuire): install silenzioso ok (layout+firma+assoc .ctpr),
    uninstall rimuove tutto. AppId GUID stabile in .iss.

## Bug noti / trappole (già sistemati, non reintrodurre)

## Decisioni bloccate

1. Traduttori: `Gemini` (sito browser, ex TXT) + `geminiamo` (cookie Firefox, serve Firefox) visibili; **Dola nascosta** (`hidden=True` in `modules/browser_sites/dola.py`) finché invio/risposta non sono verificati.
2. Chiave config legacy `TXT` → si risolve in `Gemini` ovunque (value_mappings, factory, processor). Chiave persistenza prompt `txt_prompt` e costante `TXT_PROMPT_DEFAULT` NON rinominare (compatibilità config salvati).
3. Registry siti in `modules/browser_sites/` (`base.py`, `__init__.py`, `gemini.py`, `dola.py`, `probe.py`). Aggiungere un sito = un file + una riga. Percorso profilo webview unico in `gemini_automator.get_site_storage_path`, condiviso con la sonda.
4. Installer: **net-installer** (installer piccolo + bootstrapper che scarica tutto), pesi modello in download, GPU auto-detect (torch CPU poi swap cu121 se NVIDIA). Spec completa in `docs/INSTALLER_BOOTSTRAPPER_SPEC.md` —-working agreement a fasi, eseguire in ordine.
5. `requirements.txt` curato: solo pacchetti importati. Rimosso: easyocr, openai, anthropic, google-generativeai, cerebras, deepl, deep-translator, fugashi, psutil, rookiepy. `modules/ocr/easy_ocr.py` è morto (zero riferimenti) ma ancora presente: cancellabile.
6. Lingua di lavoro: italiano. Regola: verifiche empiriche, mai speculazioni; se uno strumento manca, dirlo.

## Bug noti / trappole (già sistemati, non reintrodurre)

- `pipeline.py` → `ui_controller._run_browser_automation_sync`: il sito viaggia su `self._browser_site_key`, MAI come 6° argomento Qt (QMetaObject non risolve le firme con default; `Q_ARG(str, None)` invalido). Controllo preventivo d'arità presente (attenzione: `co_argcount` include `self` sui bound method).
- Invariante slot: scrive SEMPRE `json_result` oppure `error`. Entrambi None = slot mai partito, non ritentare.
- Login check: tre segnali (bottoni Accedi, URL accounts.google.com, campo email) — uno solo dà falsi positivi. Automator attende fino a 5 min il login manuale, poi chiude.
- Sonda e automator condividono il profilo: `webview.start()` senza `storage_path` usa profilo temporaneo (bug già preso una volta).
- `show_firefox_not_found_error` ora parla di Geminiamo (Firefox serve solo a lui), ed è cablata.
- `translator_utils.format_translations`: import `stanza` aggiunto (mancava → NameError su target zh/ja/th).

## Lavori aperti

1. **Dola** (nascosta): composer ok (`div[contenteditable]` ProseMirror), send NON trovato (non è un `<button>` con etichetta; `near_composer` in sonda ora misura distanza ad albero — rilanciare `python -m modules.browser_sites.probe Dola` e leggere `nearest_clickables`). Response senza conversazione: serve un giro reale dopo il send.
2. **Release installer**: riempire `packages.hashes` + `embed_sha256` + `app_code.url/sha256`, build con `--private-key` su macchina con Inno Setup 6, eseguire `installer/VM_TEST_PLAN.md` su VM pulita. ISCC assente qui.
3. `bootstrap.py` (pip-install all'avvio) disattivato in installazione (gate); `logs/` ora in `%APPDATA%`.
4. `build_installer.bat` riscritto (wrapper di `installer/build_installer.py`); `installer/KomicTranslate.iss` creato.

## Comandi utili

```powershell
cd E:\KomicTranslate
.venv\Scripts\python.exe -m pytest tests -q --no-header -p no:cacheprovider
.venv\Scripts\python.exe -m modules.browser_sites.probe Gemini  # o Dola
.venv\Scripts\python.exe comic.py
```
