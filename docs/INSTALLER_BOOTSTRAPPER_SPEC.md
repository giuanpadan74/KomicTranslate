# KomicTranslate — Specifica net-installer + bootstrapper robusto

Documento handoff per una sessione OpenCode CLI con shell. Leggilo tutto prima di toccare codice.

## 1. Contesto

- App: KomicTranslate, desktop PySide6 + ML (torch, paddleocr, transformers, ultralytics, doctr, stanza), traduzione via browser (pywebview) e via cookie (geminiamo). Solo Windows.
- Directory lavoro: `E:\KomicTranslate`. Entry point: `comic.py` (accetta `.ctpr` da argv). Interprete: Python 3.12, venv attivo `.venv` (testato, potato, funzionante).
- `requirements.txt`: curato, solo pacchetti importati, variante CUDA (torch 2.5.1+cu121). Variante CPU in header del file.
- Stato verificato: `compileall` pulito, 86/86 test, smoke test app ok.

## 2. Decisioni bloccate (non rimetterle in discussione senza motivo)

1. **Net-installer**: installer piccolo (MB) che scarica tutto al primo avvio. Niente PyInstaller, niente freeze: l'app gira dai sorgenti `.py` in un venv isolato creato dal bootstrapper.
2. **Pesi modello in download** (non nell'installer). Esiste già uno schema in `modules/utils/download.py` e download ModelScope in `modules/ocr/ppocr/engine.py`: riusali, non reinventare.
3. **GPU auto-detect**: installa torch CPU, controlla `cuda.is_available()`, passa a cu121 solo se c'è NVIDIA. Niente doppio installer.
4. **Tutto versionato e firmato**: vedi sotto.

## 3. Architettura obiettivo

```
%ProgramFiles%\KomicTranslate\
  python-embed\        Python 3.12 embeddable ufficiale (~15 MB, dentro l'installer)
  bootstrapper.py      si scrive una volta, non cambia quasi mai
  manifest.json        per-release: versione app, requirements con hash, pin Python
  manifest.json.sig    firma Ed25519 del manifest (chiave privata OFFLINE, mai nel repo)
  versions\
    vX.Y.Z\            sorgenti app di quella versione
  venvs\
    vX.Y.Z\            venv di quella versione
  current.txt          puntatore "vX.Y.Z" (switch atomico = riscrittura file)
```

Flusso primo avvio: leggi manifest → verifica firma → crea venv con python-embed (+ get-pip) → `pip install --require-hashes` → GPU detect ed eventuale swap torch → download pesi modello → scrivi `current.txt` → lancia `comic.py`.

Flusso update: scarica nuovo manifest → diff pin dipendenze (scarica solo ciò che cambia) + codice app sempre intero (MB) → verifica hash → switch `current.txt` → tieni la versione precedente finché la nuova non parte una volta → poi pulisci.

Rollback: riscrivi `current.txt` alla versione precedente. Mai cancellare la vecchia prima del primo avvio riuscito della nuova.

## 4. Requisiti del bootstrapper (accettazione)

- **Resume**: download con header `Range`, ripartenza dal byte interrotto. La cache wheel di pip NON basta come resume: serve nel downloader proprio per pesi e pacchetti grandi.
- **Verifiche hash**: sha256 su ogni artefatto, da manifest. Fallimento = scarta il file, ritenta N volte, poi errore esplicito (mai proseguire con file dubbi).
- **Rollback**: vedi sopra. Mai stato intermedio senza via d'uscita.
- **Idempotenza**: rilanciato a metà, riprende invece di ricominciare.
- **Progress reale**: byte scaricati/totale per file + fase corrente. Niente barre finte.
- **Log su file** in `%APPDATA%\KomicTranslate\logs\bootstrap-*.log`, con causa esatta a ogni fallimento.
- **Firma manifest**: verifica prima di scaricare qualsiasi cosa. Chiave pubblica dentro il bootstrapper, privata solo dell'autore.
- **Pin totale**: anche l'interprete (`3.12.x` esatto). Cambio Python = rebootstrap completo, mai update incrementale.

## 5. Requisiti installer Inno (accettazione)

- Solo bootstrapper + python-embed + manifest iniziale. Niente pesi, niente venv.
- Check **WebView2 runtime** (serve a pywebview per Gemini/Dola): se manca, propone il bootstrapper Evergreen, non procede muto.
- Associazione **`.ctpr`** (doppio click apre l'app: `comic.py` già gestisce argv).
- Shortcut Start/Desktop, uninstaller che chiede se tenere i dati utente (`%APPDATA%\KomicTranslate`, registry `HKCU\SOFTWARE\ComicLabs`).
- `installer/.iss` NON esiste: il vecchio `build_installer.bat` punta al vuoto e stima "5-8 MB". Riscrivere entrambi.

## 6. Vincoli codice app (pochi ma rigidi)

- Niente AppUserModelID/registry/QSettings da cambiare: già ok su Windows.
- `logs/` NON deve stare sotto Program Files (non scrivibile): già deciso spostamento in `%APPDATA%`; se non ancora fatto, fallo tu per primo.
- Niente scritture nella cartella install (es. `.pyc`): avvia con `PYTHONDONTWRITEBYTECODE=1` o verifica che non serva.
- `bootstrap.py` esistente (pip-install all'avvio) NON va riusato: è pensato per env sviluppo, non per installazioni utente.
- Lingua risposte: italiano. Verifiche empiriche: ogni affermazione con prova (esecuzione, log, test). Se uno strumento manca, dillo invece di improvvisare.

## 7. Fasi obbligate (in ordine, una alla volta)

1. `resource_path`/log APPDATA + gate `bootstrap.py` (se mancanti). Prova: app parte da `.venv` come prima.
2. Formato `manifest.json` + generatore + firma/verifica. Prova: firma valida passa, file manomesso fallisce.
3. Downloader (resume/hash/retry/progress) + unit test con interruzioni simulate. Prova: kill a metà → riprende dal byte giusto.
4. Creazione venv + `pip install --require-hashes` + GPU detect/swap. Prova su macchina con e senza NVIDIA.
5. Update differenziale + switch atomico + rollback. Prova: update ok, update corrotto → rollback automatico alla vecchia che parte.
6. Download pesi modello integrato ( riuso `modules/utils/download.py`). Prova: primo avvio completo offline dopo (a parte login/servizi).
7. `.iss` + installer + test su VM pulita: niente Python, niente WebView2, utente non admin, rete che cade. Prova: tutti gli scenari, log alla mano.

## 8. Non-obiettivi

Auto-update silenzioso in background (fase futura), firma Authenticode dell'exe (costo annuo: decidere a parte, SmartScreen avviserà), supporto offline al primo install (impossibile per disegno).
