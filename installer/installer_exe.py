# -*- coding: utf-8 -*-
"""KomicTranslate - Installer unico.

Stesso file, due usi:
  * come script:  python installer/installer_exe.py [--zip FILE] [--dest DIR]
  * compilato con PyInstaller (--onefile + payload.zip embedded):
    diventa KomicTranslate-Setup.exe, il file di distribuzione.

Il payload (backup .zip) viene cercato in questo ordine:
  1. argomento --zip
  2. payload embedded nell'exe (sys._MEIPASS/payload.zip)
  3. pacchetto.zip accanto a script/exe
  4. lo .zip piu' recente nella cartella del programma e sottocartelle

Solo stdlib: tkinter, zipfile, subprocess, shutil.
"""

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

APP = "KomicTranslate"
PYTHON_MIN = (3, 11)
PYTHON_WANTED = "3.12.10"
PYTHON_URL = ("https://www.python.org/ftp/python/3.12.10/"
              "python-3.12.10-amd64.exe")
PAYLOAD_NAMES = ("payload.zip", "pacchetto.zip")
SPACE_NEEDED_GB = 10.0


def log(msg, sink=None):
    print(msg, flush=True)
    if sink is not None:
        try:
            sink.write(msg + "\n")
        except OSError:
            pass


def program_dir():
    """Cartella dello script o dell'exe compilato."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def embedded_payload():
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = os.path.join(meipass, "payload.zip")
        if os.path.isfile(cand):
            return cand
    return None


def newest_zip(search_root):
    best, best_mtime = None, -1.0
    for dirpath, dirnames, filenames in os.walk(search_root):
        # evita venv e cache: inutili e lentissimi da scansionare
        dirnames[:] = [d for d in dirnames
                       if d not in (".venv", "venv", "__pycache__", ".git")]
        for fn in filenames:
            if fn.lower().endswith(".zip"):
                p = os.path.join(dirpath, fn)
                try:
                    m = os.path.getmtime(p)
                except OSError:
                    continue
                if m > best_mtime:
                    best, best_mtime = p, m
    return best


def resolve_payload(explicit=None):
    """(percorso, origine) oppure (None, None)."""
    if explicit:
        if os.path.isfile(explicit) and zipfile.is_zipfile(explicit):
            return os.path.abspath(explicit), "argomento --zip"
        raise SystemExit(f"ERRORE: zip non valido: {explicit}")
    emb = embedded_payload()
    if emb:
        return emb, "incluso nell'exe"
    here = program_dir()
    for name in PAYLOAD_NAMES:
        cand = os.path.join(here, name)
        if os.path.isfile(cand) and zipfile.is_zipfile(cand):
            return cand, f"pacchetto accanto all'installer ({name})"
    found = newest_zip(here)
    if found:
        return found, "piu' recente in cartella/sottocartelle"
    return None, None


def check_zip_integrity(path):
    """Ritorna (ok, dettaglio). Non estrae nulla."""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad is not None:
                return False, f"file corrotto nello zip: {bad}"
            names = z.namelist()
    except zipfile.BadZipFile as e:
        return False, f"zip illeggibile: {e}"
    top = sorted({n.split("/")[0] for n in names if n.strip("/")})
    has_req = any(n.endswith("requirements.txt") for n in names)
    detail = f"{len(names)} file, root: {', '.join(top[:8])}"
    if not has_req:
        return False, detail + " - MANCA requirements.txt"
    return True, detail


def _candidate_pythons():
    local = os.environ.get("LocalAppData", "")
    cands = [["py", "-3.12"], ["py", "-3"], ["python"]]
    for base in (local, r"C:\Program Files", r"C:\Program Files (x86)"):
        for ver in ("Python312", "Python311"):
            if base:
                cands.append([os.path.join(base, "Programs", "Python",
                                           ver, "python.exe")]
                             if base == local else
                             [os.path.join(base, ver, "python.exe")])
    cands.append([r"C:\Python312\python.exe"])
    cands.append([r"C:\Python311\python.exe"])
    # toglie duplicati mantenendo l'ordine
    seen, uniq = set(), []
    for c in cands:
        key = tuple(c)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def find_system_python():
    """Trova un Python di sistema >= 3.11 con venv. Ritorna ([cmd], vers)."""
    for cmd in _candidate_pythons():
        try:
            r = subprocess.run(
                cmd + ["-c", "import sys,venv;print('%d.%d.%d'%"
                                   "sys.version_info[:3])"],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0:
            continue
        ver = (r.stdout or "").strip()
        try:
            tup = tuple(int(x) for x in ver.split("."))
        except ValueError:
            continue
        if len(tup) == 3 and tup[:2] >= PYTHON_MIN:
            return cmd, ver
    return None, None


def download_file(url, dest, on_log=None):
    """Scarica url in dest (stdlib). Solleva RuntimeError in caso di errore."""
    def _hook(block, block_size, total):
        if total > 0 and on_log and block % 50 == 0:
            pct = min(100, block * block_size * 100 // total)
            on_log(f"  download... {pct}%")
    if on_log:
        on_log(f"Scarico {url}")
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_hook)
    except Exception as e:  # noqa: BLE001 - rete: riportata al chiamante
        raise RuntimeError(f"download fallito: {e}")
    if on_log:
        try:
            mb = os.path.getsize(dest) / 1024 ** 2
        except OSError:
            mb = -1
        on_log(f"Scaricato ({mb:.1f} MB).")


def install_python_windows(installer_exe, on_log=None):
    """Installa Python in silenzio (per-utente, niente admin)."""
    target = os.path.join(os.environ.get("LocalAppData", r"C:\Temp"),
                          "Programs", "Python", "Python312")
    cmd = [installer_exe, "/quiet", "InstallAllUsers=0",
           f'TargetDir={target}', "PrependPath=1", "Include_pip=1",
           "Include_test=0"]
    if on_log:
        on_log("Installo Python 3.12 (silenzioso, qualche minuto)...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"setup Python non avviato o timeout: {e}")
    if r.returncode != 0:
        tail = ((r.stdout or "") + "\n" + (r.stderr or ""))[-1000:]
        raise RuntimeError(f"setup Python fallito (exit {r.returncode}):\n"
                           f"{tail}")
    if on_log:
        on_log("Setup Python terminato.")


def ensure_system_python(on_log=None, ask_yes_no=None):
    """(cmd, vers) con Python >= 3.11, scaricandolo se serve.

    ask_yes_no(domanda) -> bool: chiede all'utente (GUI o console).
    Con ask_yes_no=None si procede in automatico (modalita' --yes).
    """
    cmd, ver = find_system_python()
    if cmd:
        return cmd, ver
    q = ("Python 3.11/3.12 a 64 bit non trovato.\n"
         f"Scarico e installo Python {PYTHON_WANTED} da python.org?\n"
         "(installazione per-utente, ~15 MB di download)")
    if on_log:
        on_log("Python >= 3.11 non trovato nel sistema.")
    if ask_yes_no is not None and not ask_yes_no(q):
        return None, None
    tmp = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                       f"python-{PYTHON_WANTED}-amd64.exe")
    try:
        download_file(PYTHON_URL, tmp, on_log)
        install_python_windows(tmp, on_log)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    cmd, ver = find_system_python()
    if cmd and on_log:
        on_log(f"Python pronto: {ver}")
    return cmd, ver


def disk_free_gb(path):
    try:
        anchor = os.path.abspath(path)
        while anchor and not os.path.exists(anchor):
            anchor = os.path.dirname(anchor)
        return shutil.disk_usage(anchor or os.sep).free / (1024 ** 3)
    except OSError:
        return -1.0


def check_vcredist():
    if sys.platform != "win32":
        return True
    try:
        import winreg as wr
    except ImportError:
        return False
    for flag in (0, getattr(wr, "KEY_WOW64_64KEY", 0)):
        for path in (r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
                     r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0"
                     r"\VC\Runtimes\x64"):
            try:
                with wr.OpenKey(wr.HKEY_LOCAL_MACHINE, path, 0,
                                wr.KEY_READ | flag) as k:
                    if wr.QueryValueEx(k, "Installed")[0] == 1:
                        return True
            except OSError:
                continue
    return False


def check_webview2():
    if sys.platform != "win32":
        return True
    try:
        import winreg as wr
    except ImportError:
        return False
    key = (r"SOFTWARE\Microsoft\EdgeUpdate\ClientState"
           r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")
    for root in (wr.HKEY_LOCAL_MACHINE, wr.HKEY_CURRENT_USER):
        for flag in (0, getattr(wr, "KEY_WOW64_64KEY", 0),
                     getattr(wr, "KEY_WOW64_32KEY", 0)):
            try:
                with wr.OpenKey(root, key, 0, wr.KEY_READ | flag) as k:
                    if wr.QueryValueEx(k, "pv")[0]:
                        return True
            except OSError:
                continue
    return False


def check_nvidia():
    smi = shutil.which("nvidia-smi")
    if not smi and sys.platform == "win32":
        cand = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                             "System32", "nvidia-smi.exe")
        if os.path.isfile(cand):
            smi = cand
    if not smi:
        return False
    try:
        r = subprocess.run([smi, "-L"], capture_output=True, text=True,
                           timeout=30)
        return r.returncode == 0 and "GPU" in (r.stdout or "").upper()
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve_torch_flavor(explicit=None):
    """'cuda' o 'cpu'. Precedenza: flag/env esplicito, poi nvidia-smi.

    explicit: None (auto), 'cuda' o 'cpu'. Anche env KOMICTRANSLATE_TORCH.
    """
    env = (os.environ.get("KOMICTRANSLATE_TORCH") or "").strip().lower()
    want = (explicit or env or "").strip().lower()
    if want in ("cuda", "gpu"):
        return "cuda"
    if want in ("cpu",):
        return "cpu"
    return "cuda" if check_nvidia() else "cpu"


def requirements_for_flavor(dest, flavor):
    """Percorso requirements per flavor, con fallback al base se manca il cpu."""
    if flavor == "cpu":
        cand = os.path.join(dest, "requirements-cpu.txt")
        if os.path.isfile(cand):
            return cand, "requirements-cpu.txt"
    return os.path.join(dest, "requirements.txt"), "requirements.txt"


def total_ram_gb():
    """RAM totale in GB (Windows via ctypes), -1 se non rilevabile."""
    if sys.platform != "win32":
        return -1.0
    try:
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _MS()
        st.dwLength = ctypes.sizeof(_MS)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return -1.0
        return st.ullTotalPhys / (1024 ** 3)
    except Exception:
        return -1.0


def find_logo():
    """logo.png per tkinter (niente jpg: Tk non li legge)."""
    here = program_dir()
    cands = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(os.path.join(meipass, "logo.png"))
    cands += [os.path.join(here, "installer", "logo.png"),
              os.path.join(here, "logo.png")]
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


def requirement_rows():
    """[(requisito, minimo, consigliato, questo_pc)]."""
    import platform
    pybase, ver = find_system_python()
    ram = total_ram_gb()
    disk = disk_free_gb("C:")
    return [
        ("Sistema operativo", "Windows 10 64-bit", "Windows 11 64-bit",
         f"{platform.system()} {platform.release()}".strip()),
        ("Python", "3.11 a 64 bit", "3.12.x a 64 bit",
         ver if pybase else "assente (verra' installato)"),
        ("RAM", "8 GB", "16 GB",
         f"{ram:.0f} GB" if ram > 0 else "n/d"),
        ("Spazio disco", "10 GB liberi", "20 GB liberi",
         f"{disk:.1f} GB liberi" if disk >= 0 else "n/d"),
        ("GPU", "CPU (OCR piu' lento)", "NVIDIA con CUDA",
         "NVIDIA rilevata" if check_nvidia() else "solo CPU"),
        ("VC++ Redist", "2015-2022 x64", "2015-2022 x64",
         "presente" if check_vcredist() else "ASSENTE (avviso)"),
        ("WebView2", "solo per browser", "solo per browser",
         "presente" if check_webview2() else "ASSENTE (avviso)"),
        ("Internet", "si' (pip + modelli)", "si'", "richiesta"),
    ]


def run_step(cmd, cwd=None, timeout=3600, tail_len=6000):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"comando non avviato o timeout: {e}")
    if r.returncode != 0:
        tail = ((r.stdout or "") + "\n" + (r.stderr or ""))[-tail_len:]
        raise RuntimeError(f"exit {r.returncode}:\n{tail}")
    return r


def run_pip_install(vpy, req, cwd, log_path, on_log=None, timeout=3600):
    """pip install -r req con log completo su file.

    Ritorna None se ok, altrimenti solleva RuntimeError che contiene le
    ULTIME righe (la causa reale) + il percorso del log completo.
    Il vecchio codice mostrava le PRIME righe ("Using cached ..."),
    nascondendo l'errore vero.
    """
    cmd = [vpy, "-m", "pip", "install",
           "--disable-pip-version-check", "--prefer-binary",
           "-r", req]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"pip non avviato o timeout: {e}\n"
                           f"Log completo: {log_path}")
    full = (r.stdout or "") + "\n" + (r.stderr or "")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== pip install -r {os.path.basename(req)} "
                    f"(exit {r.returncode}) =====\n")
            f.write(full)
            f.write("\n===== fine pip =====\n")
    except OSError:
        pass
    if r.returncode != 0:
        tail = full[-6000:].strip()
        raise RuntimeError(
            f"pip install fallito (exit {r.returncode}). Causa (ultime righe):\n"
            f"{tail}\n\nLog completo: {log_path}")
    # logga anche in GUI le ultime righe utili (non solo "Using cached")
    if on_log:
        for line in full[-2000:].strip().splitlines()[-8:]:
            if line.strip():
                on_log("  pip: " + line.strip()[:300])
    return r


def safe_extract(zpath, dest):
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            norm = m.replace("\\", "/")
            if norm.startswith("/") or ".." in norm.split("/"):
                raise RuntimeError(f"zip non sicuro: {m!r}")
        z.extractall(dest)


def venv_python(venv_dir):
    cand = os.path.join(venv_dir, "Scripts", "python.exe")
    if os.path.isfile(cand):
        return cand
    cand = os.path.join(venv_dir, "bin", "python")
    if os.path.isfile(cand):
        return cand
    raise RuntimeError(f"interprete venv non creato in {venv_dir}")


def do_install(payload, dest, pybase, on_log=None, on_progress=None,
               flavor=None):
    """Esegue l'installazione. Solleva RuntimeError in caso di errore.

    flavor: None (auto da nvidia-smi), 'cuda' o 'cpu'. Sceglie
    requirements.txt o requirements-cpu.txt (~4 GB di differenza).
    """
    def emit(msg, pct=None):
        log(msg)
        if on_log:
            on_log(msg)
        if pct is not None and on_progress:
            on_progress(pct)

    dest = os.path.abspath(dest)
    venv_dir = os.path.join(dest, ".venv")
    os.makedirs(dest, exist_ok=True)
    log_path = os.path.join(dest, "install.log")

    def emit2(msg, pct=None):
        emit(msg, pct)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except OSError:
            pass

    emit2(f"Payload: {payload}", 2)
    ok, detail = check_zip_integrity(payload)
    if not ok:
        raise RuntimeError(f"payload non valido: {detail}")
    emit2(f"Payload integro ({detail})", 5)

    free = disk_free_gb(dest)
    if 0 <= free < SPACE_NEEDED_GB:
        raise RuntimeError(
            f"spazio disco insufficiente in {dest}: {free:.1f} GB liberi, "
            f"servono almeno {SPACE_NEEDED_GB:.0f} GB per torch+OCR. "
            f"Libera spazio e riprova.")
    elif free >= 0:
        emit2(f"Disco: {free:.1f} GB liberi (ok).", 6)

    emit2("Estrazione in corso...", 10)
    safe_extract(payload, dest)
    emit2("Estrazione completata.", 25)

    chosen = resolve_torch_flavor(flavor)
    req, req_name = requirements_for_flavor(dest, chosen)
    if not os.path.isfile(req):
        raise RuntimeError("requirements.txt assente dopo l'estrazione: "
                           "zip non valido per KomicTranslate.")
    if chosen == "cpu":
        emit2("GPU NVIDIA non rilevata: installo la variante CPU "
              f"({req_name}, ~4 GB in meno).", 27)
    else:
        emit2("GPU NVIDIA rilevata: installo la variante CUDA "
              f"({req_name}).", 27)

    emit2("Creazione .venv (puo' durare minuti)...", 30)
    run_step(pybase + ["-m", "venv", venv_dir], timeout=600)
    vpy = venv_python(venv_dir)
    emit2(f".venv pronto: {vpy}", 40)

    emit2("Aggiorno pip...", 45)
    try:
        run_step([vpy, "-m", "pip", "install", "--upgrade", "pip", "wheel"],
                 timeout=600)
    except RuntimeError as e:
        # pip vecchio non e' fatale: proseguo, il log dira' tutto
        emit2(f"WARN: aggiornamento pip fallito ({str(e)[-300:]}), proseguo.", 45)
    emit2("Installo requirements (10-30 min, non chiudere)...", 50)
    emit2("Dettaglio avanzamento in install.log (cartella di destinazione).", 50)
    run_pip_install(vpy, req, cwd=dest, log_path=log_path,
                    on_log=on_log, timeout=7200)
    emit2("Dipendenze installate.", 80)

    # Estensione Rust opzionale (komic_core_rs): wheel precompilato in wheels/,
    # nessuna toolchain Rust richiesta sul PC utente. Fallimento = WARN,
    # l'app gira in fallback Python puro (modules/_rs_bridge.py).
    try:
        import glob as _glob
        _wheels = sorted(_glob.glob(os.path.join(dest, "wheels", "*.whl")))
        if _wheels:
            emit2(f"Installo estensione Rust ({len(_wheels)} wheel)...", 82)
            run_step([vpy, "-m", "pip", "install", "--no-index",
                      "--find-links", os.path.join(dest, "wheels"),
                      "komic_core_rs"], cwd=dest, timeout=600)
            emit2("Estensione Rust installata.", 84)
        else:
            emit2("INFO: cartella wheels/ assente o vuota, salto RS "
                  "(fallback Python).", 82)
    except RuntimeError as e:
        emit2(f"WARN: estensione Rust non installata ({e}), "
              "proseguo in fallback Python.", 84)

    emit2("Verifica ambiente .venv...", 85)
    results = verify_install(dest)
    failed = [name for name, ok_, _det in results if not ok_]
    for name, ok_, det in results:
        emit2(f"  [{'OK' if ok_ else 'FAIL'}] {name}: {det}")
    if failed:
        raise RuntimeError("verifica fallita: " + ", ".join(failed))

    launcher = os.path.join(dest, "avvia.exe")
    if os.path.isfile(launcher):
        emit2("Launcher pronto: avvia.exe (doppio click per avviare).", 95)
    else:
        emit2("WARN: avvia.exe non trovato nel payload; avvio manuale: "
              + os.path.join(dest, ".venv", "Scripts", "python.exe")
              + " comic.py", 95)
    emit2(f"INSTALLAZIONE COMPLETATA in {dest}", 100)
    return dest


def verify_install(dest):
    """Verifica un'installazione. Ritorna [(nome, ok, dettaglio)]."""
    out = []
    venv_dir = os.path.join(dest, ".venv")
    try:
        vpy = venv_python(venv_dir)
        out.append(("venv presente", True, vpy))
    except RuntimeError as e:
        return [("venv presente", False, str(e))]
    try:
        r = run_step([vpy, "-c",
                      "import sys;print('%d.%d.%d'%sys.version_info[:3])"],
                     timeout=60)
        ver = r.stdout.strip()
        tup = tuple(int(x) for x in ver.split("."))
        out.append(("python .venv", tup[:2] >= PYTHON_MIN,
                    ver + (" (richiesto >= 3.11)" if tup[:2] < PYTHON_MIN
                           else "")))
    except (RuntimeError, ValueError) as e:
        out.append(("python .venv", False, str(e)[:300]))
        return out
    try:
        run_step([vpy, "-c", "import PySide6, PIL, numpy, cv2"],
                 cwd=dest, timeout=180)
        out.append(("import base (PySide6/PIL/numpy/cv2)", True, "ok"))
    except RuntimeError as e:
        out.append(("import base (PySide6/PIL/numpy/cv2)", False,
                    str(e)[-300:]))
    try:
        r = run_step([vpy, "-c", "import torch;print(torch.__version__, "
                                 "torch.cuda.is_available())"],
                     cwd=dest, timeout=180)
        out.append(("torch", True, "versione " + r.stdout.strip()))
    except RuntimeError as e:
        out.append(("torch", False, str(e)[-300:]))
    try:
        run_step([vpy, "-c", "import py7zr"], cwd=dest, timeout=120)
        out.append(("supporto .7z (py7zr)", True, "ok"))
    except RuntimeError as e:
        out.append(("supporto .7z (py7zr)", False,
                    "DLL nativa bloccata da policy? " + str(e)[-300:]))
    try:
        r = run_step([vpy, "-c", "import komic_core_rs;print(komic_core_rs.parse_translation_payload_rs('{}', 0)[1]['source'])"], cwd=dest, timeout=120)
        out.append(("estensione Rust komic_core_rs", True, "attiva (" + r.stdout.strip() + ")"))
    except RuntimeError as e:
        # Opzionale: fallback Python puro, non blocca l'installazione.
        out.append(("estensione Rust komic_core_rs", True, "assente (fallback Python puro)"))
    comic = os.path.join(dest, "comic.py")
    if os.path.isfile(comic):
        try:
            run_step([vpy, "-m", "py_compile", comic], timeout=120)
            out.append(("comic.py compila", True, "ok"))
        except RuntimeError as e:
            out.append(("comic.py compila", False, str(e)[-300:]))
    else:
        out.append(("comic.py presente", False, "file assente"))
    return out


def self_test():
    """Controllo rapido dell'exe: payload integro + report ambiente."""
    print(f"=== {APP} Setup - self-test ===")
    payload, origin = resolve_payload()
    if not payload:
        print("FAIL: nessun payload trovato")
        return 1
    print(f"payload ({origin}): {payload}")
    try:
        size_mb = os.path.getsize(payload) / 1024 ** 2
    except OSError:
        size_mb = -1
    print(f"dimensione: {size_mb:.1f} MB")
    ok, detail = check_zip_integrity(payload)
    print(f"integrita': {'OK' if ok else 'FAIL'} ({detail})")
    try:
        with zipfile.ZipFile(payload) as z:
            names = set(z.namelist())
        print("launcher avvia.exe nel payload: "
              + ("si" if "avvia.exe" in names else "NO"))
        print("logo nel payload: "
              + ("si" if "LogoSetup.jpg" in names else "no"))
    except zipfile.BadZipFile:
        pass
    pybase, ver = find_system_python()
    print(f"python sistema: {ver if pybase else 'NON TROVATO (serve 3.11+)'}")
    print(f"VC++ Redist: {'ok' if check_vcredist() else 'ASSENTE (avviso)'}")
    print(f"WebView2: {'ok' if check_webview2() else 'ASSENTE (avviso)'}")
    print(f"GPU NVIDIA: {'si' if check_nvidia() else 'no (verra usata CPU)'}")
    print(f"variante torch: {resolve_torch_flavor().upper()} (auto; override --cpu/--gpu)")
    print(f"disco C: {disk_free_gb('C:'):.1f} GB liberi")
    print("=== self-test: " + ("OK" if ok else "FAIL") + " ===")
    return 0 if ok else 1


def gui_install(payload, origin, flavor=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import threading

    rows = requirement_rows()

    root = tk.Tk()
    root.title(f"{APP} - Setup")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=14)
    frm.pack(fill="both", expand=True)

    logo = find_logo()
    img = None
    if logo:
        try:
            img = tk.PhotoImage(file=logo)
        except tk.TclError:
            img = None
    if img:
        ttk.Label(frm, image=img).pack()
    ttk.Label(frm, text=f"{APP} - Installazione",
              font=("", 14, "bold")).pack(pady=(8, 2))
    if payload:
        ttk.Label(frm, text=f"Backup: {os.path.basename(payload)} "
                            f"({origin})").pack()
    else:
        ttk.Label(frm, text="Backup: da scegliere...").pack()

    ttk.Label(frm, text="Requisiti minimi e consigliati:",
              font=("", 10, "bold")).pack(pady=(10, 4))
    tree = ttk.Treeview(frm, columns=("min", "rec", "pc"), height=8)
    tree.heading("#0", text="Requisito")
    tree.heading("min", text="Minimo")
    tree.heading("rec", text="Consigliato")
    tree.heading("pc", text="Questo PC")
    tree.column("#0", width=130)
    tree.column("min", width=150)
    tree.column("rec", width=150)
    tree.column("pc", width=190)
    for name, mn, rec, pc in rows:
        tree.insert("", "end", text=name, values=(mn, rec, pc))
    tree.pack()

    state = {"rc": 1}

    def on_cancel():
        state["rc"] = 1
        root.destroy()

    def on_install():
        pload = payload
        if pload is None:
            pload = filedialog.askopenfilename(
                title="Seleziona backup .zip",
                filetypes=[("Archivi ZIP", "*.zip")])
            if not pload:
                return
        dest = filedialog.askdirectory(
            title=f"{APP} - scegli cartella di destinazione")
        if not dest:
            return
        pybase, ver = ensure_system_python(
            ask_yes_no=lambda q: messagebox.askyesno(
                f"{APP} - Python mancante",
                q + "\n\nNOTA: Python 3.8.12 NON e' compatibile "
                "(serve >= 3.11)."))
        if not pybase:
            messagebox.showerror(
                "Python mancante",
                "Installazione annullata: senza Python 3.11/3.12 il .venv "
                "non puo' essere creato.")
            return
        summary = (f"Backup: {os.path.basename(pload)}\n"
                   f"Destinazione: {dest}\nPython: {ver}\n"
                   f"Versione: {resolve_torch_flavor(flavor).upper()} "
                   f"({'scelta manuale' if flavor else 'auto da GPU'})\n\nProcedo?")
        if not messagebox.askyesno(f"{APP} - riepilogo", summary):
            return

        win = tk.Toplevel(root)
        win.title(f"{APP} - installazione in corso...")
        win.geometry("560x380")
        bar = ttk.Progressbar(win, mode="determinate", maximum=100)
        bar.pack(fill="x", padx=10, pady=10)
        txt = tk.Text(win, state="disabled", wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        def on_log(msg):
            def _w():
                txt.configure(state="normal")
                txt.insert("end", msg + "\n")
                txt.see("end")
                txt.configure(state="disabled")
            win.after(0, _w)

        def on_progress(pct):
            win.after(0, lambda: bar.configure(value=pct))

        result = {}

        def worker():
            try:
                do_install(pload, dest, pybase, on_log, on_progress,
                           flavor=flavor)
                result["ok"] = True
            except Exception as e:  # noqa: BLE001 - mostrato all'utente
                on_log(f"ERRORE: {e}")
                result["ok"] = False
                result["err"] = str(e)

        def poll():
            if "ok" not in result:
                win.after(200, poll)
                return
            if result["ok"]:
                messagebox.showinfo("Completato",
                                    f"{APP} installato in:\n{dest}\n"
                                    "Avvialo con avvia.exe")
                state["rc"] = 0
            else:
                err = result.get("err", "?")
                # Mostra le ULTIME righe (la causa), non le prime
                # ("Using cached ..." non serve a diagnosticare).
                messagebox.showerror(
                    "Installazione fallita",
                    err[-3000:] + "\n\nVedi install.log nella cartella scelta.")
                state["rc"] = 1
            root.destroy()

        threading.Thread(target=worker, daemon=True).start()
        win.after(200, poll)

    btns = ttk.Frame(frm)
    btns.pack(pady=(12, 0))
    ttk.Button(btns, text="Annulla", command=on_cancel).pack(side="left",
                                                             padx=5)
    ttk.Button(btns, text="Installa", command=on_install).pack(side="left",
                                                               padx=5)
    root.mainloop()
    return state["rc"]


def cli_install(payload, dest, assume_yes, flavor=None):
    if payload is None:
        print("ERRORE: nessun payload trovato (usa --zip).")
        return 1
    if not dest:
        print("ERRORE: indica --dest.")
        return 1
    if assume_yes:
        ask = None  # automatico: scarica/installa senza chiedere
    else:
        def ask(q):
            print(q)
            ans = input("Procedo? [S/N] ").strip().lower()
            return ans in ("s", "si", "sì", "y", "yes")
    pybase, ver = ensure_system_python(on_log=print, ask_yes_no=ask)
    if not pybase:
        print("ERRORE: serve Python 64-bit >= 3.11 (3.8.12 non compatibile).")
        return 1
    print(f"Payload : {payload}")
    print(f"Dest    : {dest}")
    print(f"Python  : {ver}")
    print(f"Versione: {resolve_torch_flavor(flavor).upper()} "
          f"({'forzata' if (flavor or os.environ.get('KOMICTRANSLATE_TORCH')) else 'auto da nvidia-smi'})")
    if not assume_yes:
        ans = input("Procedo? [S/N] ").strip().lower()
        if ans not in ("s", "si", "sì", "y", "yes"):
            print("Annullato.")
            return 0
    try:
        do_install(payload, dest, pybase, flavor=flavor)
    except RuntimeError as e:
        print(f"INSTALLAZIONE FALLITA: {e}")
        return 1
    return 0


def print_help():
    print("Uso:")
    print("  installer_exe.py [--zip FILE] [--dest DIR] [--yes] [--no-gui]")
    print("  installer_exe.py [--cpu | --gpu]   (forza variante torch, default: auto)")
    print("  installer_exe.py --self-test   (controllo payload, non installa)")
    print("Senza argomenti: interfaccia grafica guidata.")
    print("Env KOMICTRANSLATE_TORCH=cpu|cuda: stesso override dei flag.")


def main(argv=None):
    args = list(argv or sys.argv[1:])
    if "--help" in args or "-h" in args or "/?" in args:
        print_help()
        return 0
    if "--self-test" in args:
        return self_test()
    explicit = None
    dest = None
    assume_yes = "--yes" in args
    no_gui = "--no-gui" in args
    flavor = None
    if "--cpu" in args:
        flavor = "cpu"
    if "--gpu" in args:
        flavor = "cuda"
    for i, a in enumerate(args):
        if a == "--zip" and i + 1 < len(args):
            explicit = args[i + 1]
        if a == "--dest" and i + 1 < len(args):
            dest = args[i + 1]
    try:
        payload, origin = resolve_payload(explicit)
    except SystemExit as e:
        print(e)
        return 1
    if no_gui or dest:
        return cli_install(payload, dest, assume_yes, flavor)
    try:
        return gui_install(payload, origin, flavor)
    except ImportError:
        print("tkinter non disponibile, passo a riga di comando.")
        return cli_install(payload, dest or os.path.join(
            os.path.expanduser("~"), APP), assume_yes, flavor)


if __name__ == "__main__":
    sys.exit(main())
