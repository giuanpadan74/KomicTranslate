# -*- coding: utf-8 -*-
"""KomicTranslate - Installer macOS (porting di installer/installer_exe.py).

Stesso file, due usi:
  * come script:  python3 installer/installer_macos.py [--setup|--launch|--self-test]
  * compilato con PyInstaller (--windowed + payload.zip embedded):
    diventa KomicTranslate-Setup.app, l'equivalente Mac di KomicTranslate-Setup.exe.

Flusso al primo doppio click:
  1. trova un Python >= 3.11 (/usr/bin/python3 o python3.12 del PATH)
  2. crea il venv in ~/Library/Application Support/KomicTranslate/venv
  3. pip install -r requirements-macos.txt (torch CPU, Paddle non fatale)
  4. estrae payload.zip (sorgenti) in .../KomicTranslate/app
  5. marca .installed e avvia comic.py col python del venv

Dai lanci successivi rileva l'installazione e avvia direttamente.
Solo stdlib: tkinter, zipfile, subprocess, shutil.

Differenze rispetto alla versione Windows:
  - niente VC++ Redist / WebView2 / Program Files / registro
  - niente nvidia-smi: torch CPU/MPS, quindi sempre requirements-macos.txt
  - la wheel Rust in wheels/ e' solo win_amd64: su Mac NON si installa
    (fallback Python puro, come su Windows quando manca)
"""

import os
import shutil
import subprocess
import sys
import zipfile

APP = "KomicTranslate"
PYTHON_MIN = (3, 11)
PYTHON_WANTED = "3.12"
SPACE_NEEDED_GB = 10.0
PAYLOAD_NAMES = ("payload.zip", "pacchetto.zip")
SOURCE_DIR_NAME = "app"  # sotto ~/Library/Application Support/KomicTranslate/


# ---------------------------------------------------------------- percorsi

def program_dir():
    """Cartella dello script o dell'eseguibile dentro l'.app."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def support_dir():
    """~/Library/Application Support/KomicTranslate (creato on demand)."""
    return os.path.expanduser(f"~/Library/Application Support/{APP}")


def source_dir():
    return os.path.join(support_dir(), SOURCE_DIR_NAME)


def venv_python(venv_dir=None):
    """Interprete del venv in bin/python (Mac non usa Scripts/)."""
    vd = venv_dir or os.path.join(support_dir(), "venv")
    for rel in ("bin/python3", "bin/python"):
        p = os.path.join(vd, *rel.split("/"))
        if os.path.isfile(p):
            return p
    return None


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
        dirnames[:] = [d for d in dirnames
                       if d not in (".venv", "venv", "__pycache__", ".git")]
        for fn in filenames:
            if fn.lower().endswith(".zip"):
                p = os.path.join(dirpath, fn)
                try:
                    mtime = os.path.getmtime(p)
                except OSError:
                    continue
                if mtime > best_mtime:
                    best, best_mtime = p, mtime
    return best


def resolve_payload(explicit=None):
    """(percorso, origine) oppure (None, None)."""
    if explicit:
        if os.path.isfile(explicit) and zipfile.is_zipfile(explicit):
            return os.path.abspath(explicit), "argomento --zip"
        raise SystemExit(f"ERRORE: zip non valido: {explicit}")
    emb = embedded_payload()
    if emb:
        return emb, "incluso nell'app"
    here = program_dir()
    for name in PAYLOAD_NAMES:
        cand = os.path.join(here, name)
        if os.path.isfile(cand) and zipfile.is_zipfile(cand):
            return cand, f"pacchetto accanto all'installer ({name})"
    found = newest_zip(here)
    if found:
        return found, "piu' recente in cartella/sottocartelle"
    return None, None


def log(msg, sink=None):
    print(msg, flush=True)
    if sink is not None:
        try:
            sink.write(msg + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------- controlli

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
    has_req = any(n.endswith("requirements-macos.txt")
                  or n.endswith("requirements.txt") for n in names)
    detail = f"{len(names)} file, root: {', '.join(top[:8])}"
    if not has_req:
        return False, detail + " - MANCA requirements-macos.txt"
    return True, detail


def _candidate_pythons():
    cands = []
    # PATH (python3.x lanciato da Homebrew/installer ufficiale)
    for name in ("python3.13", "python3.12", "python3.11", "python3", "python"):
        path = shutil.which(name)
        if path:
            cands.append([path])
    # percorsi tipici se il PATH e' minimale (dmg aperto da Finder)
    for extra in ("/usr/bin/python3", "/opt/homebrew/bin/python3.13",
                  "/opt/homebrew/bin/python3.12", "/opt/homebrew/bin/python3",
                  "/usr/local/bin/python3"):
        if os.path.isfile(extra):
            cands.append([extra])
    # toglie duplicati mantenendo l'ordine
    seen, uniq = set(), []
    for c in cands:
        if tuple(c) not in seen:
            seen.add(tuple(c))
            uniq.append(c)
    return uniq


def find_system_python():
    """Trova un Python >= 3.11. Ritorna ([cmd], vers) oppure (None, None)."""
    for cmd in _candidate_pythons():
        try:
            r = subprocess.run(
                cmd + ["-c",
                       "import sys;print('%d.%d.%d'%sys.version_info[:3])"],
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


def disk_free_gb(path):
    try:
        anchor = os.path.abspath(path)
        while anchor and not os.path.exists(anchor):
            anchor = os.path.dirname(anchor)
        return shutil.disk_usage(anchor or "/").free / (1024 ** 3)
    except OSError:
        return -1.0


def total_ram_gb():
    try:
        pages = os.sysconf("SC_PAGE_SIZE")
        phys = os.sysconf("SC_PHYS_PAGES")
        return pages * phys / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return -1.0


def safe_extract(zpath, dest):
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            norm = m.replace("\\", "/")
            if norm.startswith("/") or ".." in norm.split("/"):
                raise RuntimeError(f"zip non sicuro: {m!r}")
        z.extractall(dest)


def run_step(cmd, cwd=None, timeout=7200):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"comando non avviato o timeout: {e}")
    if r.returncode != 0:
        tail = ((r.stdout or "") + "\n" + (r.stderr or ""))[-6000:]
        raise RuntimeError(f"exit {r.returncode}:\n{tail}")
    return r


def run_pip_install(vpy, req, cwd, log_path, on_log=None):
    """pip install -r req con log completo su file (come installer_exe.py)."""
    cmd = [vpy, "-m", "pip", "install", "--disable-pip-version-check",
           "--prefer-binary", "-r", req]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=7200)
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
        raise RuntimeError(
            f"pip install fallito (exit {r.returncode}). Causa (ultime righe):\n"
            f"{full[-6000:].strip()}\n\nLog completo: {log_path}")
    if on_log:
        for line in full[-2000:].strip().splitlines()[-8:]:
            if line.strip():
                on_log("  pip: " + line.strip()[:300])
    return r


def requirements_file(dest):
    """requirements-macos.txt se presente, altrimenti requirements.txt."""
    for name in ("requirements-macos.txt", "requirements-cpu.txt",
                 "requirements.txt"):
        path = os.path.join(dest, name)
        if os.path.isfile(path):
            return path
    return None


# ---------------------------------------------------------------- install

def do_install(payload, dest, pybase, on_log=None, on_progress=None):
    """Esegue l'installazione. Solleva RuntimeError in caso di errore."""
    def emit(msg, pct=None):
        log(msg)
        if on_log:
            on_log(msg)
        if pct is not None and on_progress:
            on_progress(pct)

    dest = os.path.abspath(dest)
    src = source_dir()
    venv_dir = os.path.join(dest, "venv")
    log_path = os.path.join(dest, "install.log")
    os.makedirs(dest, exist_ok=True)

    def emit2(msg, pct=None):
        emit(msg, pct)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except OSError:
            pass

    emit2(f"Installazione in: {dest}", 2)
    ok, detail = check_zip_integrity(payload)
    if not ok:
        raise RuntimeError(f"payload non valido: {detail}")
    emit2(f"Payload integro ({detail})", 5)

    free = disk_free_gb(dest)
    if 0 <= free < SPACE_NEEDED_GB:
        raise RuntimeError(
            f"spazio disco insufficiente: {free:.1f} GB liberi, "
            f"servono almeno {SPACE_NEEDED_GB:.0f} GB per torch+OCR.")
    elif free >= 0:
        emit2(f"Disco: {free:.1f} GB liberi (ok).", 6)

    emit2("Estrazione sorgenti in corso...", 10)
    os.makedirs(src, exist_ok=True)
    safe_extract(payload, src)
    emit2("Estrazione completata.", 25)

    req = requirements_file(src)
    if not req:
        raise RuntimeError("requirements-macos.txt assente dopo "
                           "l'estrazione: zip non valido per KomicTranslate.")
    emit2(f"Requisiti: {os.path.basename(req)}", 27)

    emit2("Creazione venv (puo' durare minuti)...", 30)
    if not os.path.isdir(os.path.join(venv_dir, "bin")):
        run_step(pybase + ["-m", "venv", venv_dir], timeout=600)
    vpy = venv_python(venv_dir)
    if not vpy:
        raise RuntimeError("interprete venv non creato")
    emit2(f"venv pronto: {vpy}", 40)

    emit2("Aggiorno pip...", 45)
    try:
        run_step([vpy, "-m", "pip", "install", "--upgrade", "pip", "wheel"],
                  timeout=600)
    except RuntimeError as e:
        emit2(f"WARN: aggiornamento pip fallito ({str(e)[-300:]}), proseguo.",
              45)
    emit2("Installo requirements (10-30 min, non chiudere)...", 50)
    emit2("Dettaglio avanzamento in install.log.", 50)
    run_pip_install(vpy, req, cwd=src, log_path=log_path, on_log=on_log)
    emit2("Dipendenze installate.", 80)

    # La wheel Rust in wheels/ e' solo win_amd64: su Mac va saltata.
    wheels = os.path.join(src, "wheels")
    if os.path.isdir(wheels):
        mac_wheels = [w for w in os.listdir(wheels)
                      if w.endswith(".whl") and "macosx" in w]
        if mac_wheels:
            emit2(f"Installo estensione Rust ({len(mac_wheels)} wheel)...", 82)
            try:
                run_step([vpy, "-m", "pip", "install", "--no-index",
                          "--find-links", wheels, "komic_core_rs"],
                         cwd=src, timeout=600)
                emit2("Estensione Rust installata.", 84)
            except RuntimeError as e:
                emit2(f"WARN: estensione Rust non installata ({e}), "
                      "proseguo in fallback Python.", 84)
        else:
            emit2("INFO: nessuna wheel Rust per macOS, salto (fallback "
                  "Python puro).", 82)

    emit2("Verifica ambiente...", 85)
    failed = verify_install(dest)
    for name, ok_, det in failed:
        emit2(f"  [{'OK' if ok_ else 'FAIL'}] {name}: {det}")
    bad = [n for n, ok_, _d in failed if not ok_]
    if bad:
        raise RuntimeError("verifica fallita: " + ", ".join(bad))

    # marker: da qui in poi l'app e' "installata" (bootstrap disabilitato)
    try:
        with open(os.path.join(dest, ".installed"), "w",
                  encoding="utf-8") as f:
            f.write(f"{APP} installato\n")
    except OSError:
        pass

    comic = os.path.join(src, "comic.py")
    if not os.path.isfile(comic):
        raise RuntimeError(f"comic.py assente in {src}")
    emit2(f"INSTALLAZIONE COMPLETATA in {src}", 100)
    return dest


def verify_install(dest):
    """Ritorna [(nome, ok, dettaglio)]. Import base + torch + comic.py."""
    out = []
    vpy = venv_python()
    if not vpy:
        return [("venv presente", False, "interprete venv assente")]
    out.append(("venv presente", True, vpy))
    try:
        r = run_step([vpy, "-c",
                      "import sys;print('%d.%d.%d'%sys.version_info[:3])"],
                     timeout=60)
        ver = r.stdout.strip()
        tup = tuple(int(x) for x in ver.split("."))
        out.append(("python venv", tup[:2] >= PYTHON_MIN,
                    ver if tup[:2] >= PYTHON_MIN
                    else f"{ver} (serve >= {PYTHON_MIN[0]}.{PYTHON_MIN[1]})"))
    except (RuntimeError, ValueError) as e:
        out.append(("python venv", False, str(e)[:300]))
        return out
    src = source_dir()
    for label, code, tmo in (
            ("import base (PySide6/PIL/numpy/cv2)",
             "import PySide6, PIL, numpy, cv2", 180),
            ("torch (CPU/MPS)", "import torch", 180),
            ("supporto .7z (py7zr)", "import py7zr", 120)):
        try:
            run_step([vpy, "-c", code], cwd=src, timeout=tmo)
            out.append((label, True, "ok"))
        except RuntimeError as e:
            out.append((label, False, str(e)[-300:]))
    comic = os.path.join(src, "comic.py")
    if os.path.isfile(comic):
        try:
            run_step([vpy, "-m", "py_compile", comic], cwd=src, timeout=120)
            out.append(("comic.py compila", True, "ok"))
        except RuntimeError as e:
            out.append(("comic.py compila", False, str(e)[-300:]))
    else:
        out.append(("comic.py presente", False, "file assente"))
    return out


def launch_app():
    """Avvia comic.py col python del venv. Ritorna exit code o messaggio."""
    vpy = venv_python()
    comic = os.path.join(source_dir(), "comic.py")
    if not vpy or not os.path.isfile(comic):
        return ("KomicTranslate non e' installato: apri "
                "KomicTranslate-Setup.app (primo avvio guidato).")
    env = dict(os.environ)
    env["KOMIC_TRANSLATE_INSTALLED"] = "1"
    try:
        # processo staccato: il launcher puo' chiudersi, l'app resta viva
        subprocess.Popen([vpy, comic], cwd=source_dir(), env=env,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as e:
        return f"avvio fallito: {e}"
    return None


def find_logo():
    here = program_dir()
    cands = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(os.path.join(meipass, "logo.png"))
    cands += [os.path.join(here, "installer", "logo.png"),
              os.path.join(here, "logo.png"),
              os.path.join(source_dir(), "installer", "logo.png")]
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


# ---------------------------------------------------------------- self-test

def self_test():
    print(f"=== {APP} macOS Setup - self-test ===")
    payload, origin = resolve_payload()
    if not payload:
        print("FAIL: nessun payload trovato")
        return 1
    print(f"payload ({origin}): {payload}")
    try:
        print(f"dimensione: {os.path.getsize(payload) / 1024 ** 2:.1f} MB")
    except OSError:
        pass
    ok, detail = check_zip_integrity(payload)
    print(f"integrita': {'OK' if ok else 'FAIL'} ({detail})")
    pybase, ver = find_system_python()
    print(f"python sistema: {ver if pybase else 'NON TROVATO (serve 3.11+)'}")
    print(f"installato in: {support_dir()}")
    print(f"venv: {venv_python() or 'assente (primo avvio lo crea)'}")
    print(f"disco: {disk_free_gb(support_dir()):.1f} GB liberi")
    print(f"RAM: {total_ram_gb():.0f} GB")
    print("=== self-test: " + ("OK" if ok else "FAIL") + " ===")
    return 0 if ok else 1


# ---------------------------------------------------------------- GUI

def gui_install(payload, origin):
    """Primo avvio: finestra tkinter con avanzamento (come installer_exe.py)."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import threading

    dest = support_dir()
    rows = [
        ("Sistema operativo", "macOS 13+", "macOS 14/15 ARM", "ricevuto"),
        ("Python", "3.11 (usa quello di sistema)", "3.12",
         (find_system_python()[1] or "assente")),
        ("RAM", "8 GB", "16 GB", f"{total_ram_gb():.0f} GB"
         if total_ram_gb() > 0 else "n/d"),
        ("Spazio disco", "10 GB liberi", "20 GB liberi",
         f"{disk_free_gb(dest):.1f} GB liberi"
         if disk_free_gb(dest) >= 0 else "n/d"),
        ("GPU", "CPU (OCR piu' lento)", "Apple Silicon MPS", "CPU/MPS"),
        ("Destinazione", dest, dest, dest),
        ("Tempo stimato", "10-30 min", "rete veloce", "dipende dalla rete"),
    ]

    root = tk.Tk()
    root.title(f"{APP} - Installazione")
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
    ttk.Label(frm, text=f"{APP} - Installazione macOS",
              font=("", 14, "bold")).pack(pady=(8, 2))
    ttk.Label(frm, text=f"Backup: {os.path.basename(payload)} "
                        f"({origin})").pack()

    ttk.Label(frm, text="Requisiti e destinazione:",
              font=("", 10, "bold")).pack(pady=(10, 4))
    tree = ttk.Treeview(frm, columns=("v",), height=len(rows))
    tree.heading("#0", text="Voce")
    tree.heading("v", text="Questo Mac")
    tree.column("#0", width=170)
    tree.column("v", width=270)
    for name, _mn, _rec, pc in rows:
        tree.insert("", "end", text=name, values=(pc,))
    tree.pack()

    state = {"rc": 1}

    def on_cancel():
        state["rc"] = 1
        root.destroy()

    def on_install():
        pybase, ver = find_system_python()
        if not pybase:
            messagebox.showerror(
                "Python mancante",
                "Serve Python 3.11 o superiore (Apple lo distribuisce coi "
                "Command Line Tools o scaricabile da python.org).\n"
                "Con Homebrew: brew install python@3.12")
            return
        summary = (f"Backup: {os.path.basename(payload)}\n"
                   f"Destinazione: {dest}\nPython: {ver}\n"
                   f"Spazio: ~4 GB (torch CPU + OCR)\n\nProcedo?")
        if not messagebox.askyesno(f"{APP} - riepilogo", summary):
            return

        win = tk.Toplevel(root)
        win.title(f"{APP} - installazione in corso...")
        win.geometry("620x420")
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
                do_install(payload, dest, pybase, on_log, on_progress)
                result["ok"] = True
            except Exception as e:  # noqa: BLE001 - mostrato all'utente
                on_log(f"ERRORE: {e}")
                result["ok"] = False
                result["err"] = str(e)

        def poll():
            if "ok" not in result:
                win.after(250, poll)
                return
            if result["ok"]:
                messagebox.showinfo(
                    "Installato",
                    f"{APP} installato in:\n{dest}\n\nAl prossimo doppio click "
                    "si aprira' direttamente.")
                state["rc"] = 0
                root.destroy()
            else:
                messagebox.showerror(
                    "Installazione fallita",
                    result.get("err", "?")[-3000:]
                    + "\n\nVedi install.log nella cartella scelta.")
                on_cancel()

        threading.Thread(target=worker, daemon=True).start()
        win.after(250, poll)

    btns = ttk.Frame(frm)
    btns.pack(pady=(12, 0))
    ttk.Button(btns, text="Annulla", command=on_cancel).pack(side="left",
                                                           padx=5)
    ttk.Button(btns, text="Installa", command=on_install).pack(side="left",
                                                              padx=5)
    root.mainloop()
    return state["rc"]


# ---------------------------------------------------------------- CLI

def cli_setup(payload, assume_yes):
    dest = support_dir()
    pybase, ver = find_system_python()
    if not pybase:
        print("ERRORE: serve Python 3.11+ (>= 3.11). Su macOS i Command Line "
              "Tools portano /usr/bin/python3, oppure: brew install python@3.12")
        return 1
    print(f"Payload : {payload}")
    print(f"Dest    : {dest}")
    print(f"Python  : {ver}")
    if not assume_yes:
        ans = input("Procedo? [S/N] ").strip().lower()
        if ans not in ("s", "si", "sì", "y", "yes"):
            print("Annullato.")
            return 0
    try:
        do_install(payload, dest, pybase)
    except RuntimeError as e:
        print(f"INSTALLAZIONE FALLITA: {e}")
        return 1
    return 0


def print_help():
    print("Uso:")
    print("  installer_macos.py              (primo avvio guidato GUI / "
          "avvio se gia' installato)")
    print("  installer_macos.py --setup       (installazione da terminale)")
    print("  installer_macos.py --launch      (avvia l'app gia' installata)")
    print("  installer_macos.py --self-test   (controllo payload, non installa)")


def main(argv=None):
    args = list(argv or sys.argv[1:])
    if "--help" in args or "-h" in args:
        print_help()
        return 0
    if "--self-test" in args:
        return self_test()

    # Gia' installato: avvia diretto (nessuna finestra di setup).
    if venv_python() and os.path.isfile(os.path.join(source_dir(), "comic.py")):
        if "--setup" not in args:
            err = launch_app()
            if err:
                print(f"ERRORE: {err}")
                return 1
            return 0

    try:
        payload, origin = resolve_payload()
    except SystemExit as e:
        print(e)
        return 1

    if "--launch" in args:
        err = launch_app()
        print(err or "avviato.")
        return 0 if not err else 1

    assume_yes = "--yes" in args
    if "--setup" in args or assume_yes:
        if not payload:
            print("ERRORE: nessun payload trovato (usa --zip).")
            return 1
        return cli_setup(payload, assume_yes)
    try:
        return gui_install(payload, origin)
    except ImportError:
        print("tkinter non disponibile, passo a riga di comando.")
        if not payload:
            print("ERRORE: nessun payload trovato (usa --zip).")
            return 1
        return cli_setup(payload, assume_yes)


if __name__ == "__main__":
    sys.exit(main())
