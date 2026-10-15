# -*- coding: utf-8 -*-
"""Crea payload.zip per la build macOS (equivalente della fase 1 di crea_setup.bat).

Uso (dalla root del repo, su qualsiasi OS):
    python installer/stage_payload.py build-macos/payload.zip

Include solo sorgenti e risorse: niente venv, modelli, log, backup, build
Rust o wheel (le wheel in wheels/ sono win_amd64 e su Mac non servono).
"""

import os
import sys
import zipfile

# Copiato da crea_setup.bat (robocopy /XD + pattern *.py *.txt ...)
EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                "models", "Backups", "dist", "build", "logs", "_tmp",
                "wheels", "target", ".github"}
EXCLUDE_EXT = {".exe", ".zip", ".spec", ".pyc", ".pdb", ".dll", ".lib",
               ".exp", ".rlib"}
# Estensioni/osservati da copiare anche fuori dai pattern storici
EXTRA_ROOT_FILES = {"LICENSE", "LogoSetup.jpg", "version_info.txt",
                    "font_models.json", "report.json", "history.txt",
                    "installer/logo.png"}


def keep_dir(name, rel):
    if rel == ".":
        return name not in EXCLUDE_DIRS
    if name in EXCLUDE_DIRS:
        return False
    # rs_core/ e' sorgente Rust: includilo ma non il suo target/
    if name == "target" and rel == "rs_core":
        return False
    return True


def keep_file(name, rel):
    ext = os.path.splitext(name)[1].lower()
    if ext in EXCLUDE_EXT:
        return False
    return True


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    out = os.path.abspath(sys.argv[1])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(root):
            rel = os.path.relpath(dirpath, root)
            if rel == ".":
                rel = "."
            dirnames[:] = [d for d in dirnames
                           if keep_dir(d, os.path.relpath(os.path.join(dirpath, d), root))]
            for fn in filenames:
                r = os.path.relpath(os.path.join(dirpath, fn), root)
                if not keep_file(fn, r):
                    continue
                z.write(os.path.join(root, r), r.replace(os.sep, "/"))
                count += 1
    mb = os.path.getsize(out) / 1024 ** 2
    print(f"payload creato: {out} ({count} file, {mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
