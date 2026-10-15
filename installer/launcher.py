# -*- coding: utf-8 -*-
"""KomicTranslate launcher (sorgente di avvia.exe). Solo stdlib.

Doppio click: splash con logo, poi avvia comic.py col python del .venv
accanto all'exe e si chiude. Uso come script in sviluppo, compilato
(PyInstaller --onefile --noconsole) come avvia.exe distribuito.
"""

import os
import subprocess
import sys

APP = "KomicTranslate"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_logo():
    """logo.png per tkinter (niente jpg: Tk non li legge)."""
    here = app_dir()
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


def venv_python(base):
    cands = [os.path.join(base, ".venv", "Scripts", "pythonw.exe"),
             os.path.join(base, ".venv", "Scripts", "python.exe"),
             os.path.join(base, ".venv", "bin", "python")]
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


def check():
    """Verifica senza GUI: exit 0 se avviabile, 1 altrimenti."""
    base = app_dir()
    vpy = venv_python(base)
    comic = os.path.join(base, "comic.py")
    problems = []
    if not vpy:
        problems.append(".venv assente (installare prima)")
    if not os.path.isfile(comic):
        problems.append("comic.py assente")
    if vpy and os.path.isfile(comic):
        try:
            r = subprocess.run([vpy, "-m", "py_compile", comic],
                               capture_output=True, timeout=120)
            if r.returncode != 0:
                problems.append("comic.py non compila")
        except (OSError, subprocess.TimeoutExpired) as e:
            problems.append(f"check fallito: {e}")
    if problems:
        print("AVVIO IMPOSSIBILE:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"pronto: {vpy} {comic}")
    return 0


def launch(base, vpy, comic):
    flags = getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen([vpy, comic], cwd=base, close_fds=True,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=flags)
        return None
    except OSError as e:
        return str(e)


def gui():
    import tkinter as tk
    base = app_dir()
    vpy = venv_python(base)
    comic = os.path.join(base, "comic.py")

    root = tk.Tk()
    root.title(APP)
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    logo = find_logo()
    img = None
    if logo:
        try:
            img = tk.PhotoImage(file=logo)
        except tk.TclError:
            img = None
    w = img.width() if img else 360
    h = (img.height() if img else 100) + 60
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    if img:
        tk.Label(root, image=img).pack()
    tk.Label(root, text="Avvio KomicTranslate...",
             font=("", 11)).pack(pady=10)
    root.update()

    err = None
    if not vpy or not os.path.isfile(comic):
        missing = []
        if not vpy:
            missing.append(".venv non trovato")
        if not os.path.isfile(comic):
            missing.append("comic.py non trovato")
        err = " + ".join(missing) + f"\nCartella: {base}"
    else:
        err = launch(base, vpy, comic)

    if err:
        root.destroy()
        root2 = tk.Tk()
        root2.withdraw()
        from tkinter import messagebox
        messagebox.showerror(f"{APP} - avvio impossibile", err)
        root2.destroy()
        return 1
    root.after(3000, root.destroy)
    root.mainloop()
    return 0


def main(argv=None):
    args = list(argv or sys.argv[1:])
    if "--help" in args or "-h" in args or "/?" in args:
        print("Uso: avvia.exe [--check]  (doppio click per avviare)")
        return 0
    if "--check" in args:
        return check()
    try:
        return gui()
    except ImportError:
        # tkinter assente: avvio diretto senza splash
        base = app_dir()
        vpy = venv_python(base)
        comic = os.path.join(base, "comic.py")
        if not vpy or not os.path.isfile(comic):
            print("ERRORE: .venv o comic.py mancanti.")
            return 1
        err = launch(base, vpy, comic)
        if err:
            print(f"ERRORE: {err}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
