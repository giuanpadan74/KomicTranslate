# -*- mode: python ; coding: utf-8 -*-
"""
KomicTranslate Bootstrap Script
Installs ML dependencies on first run if not present
"""

import os
import sys
import subprocess
import tempfile
from datetime import datetime
import requests
from loguru import logger

REQUIREMENTS_URL = "https://raw.githubusercontent.com/giuanpadan74/KomicTranslate/main/requirements.txt"

ESSENTIAL_PACKAGES = [
    'torch', 'torchvision', 'torchaudio',
    'transformers', 'sentencepiece', 'tokenizers',
    'paddleocr', 'paddlepaddle',
    'easyocr', 'doctr',
    'ultralytics', 'opencv-python',
    'pillow', 'numpy',
    'stanza', 'scipy',
    'sklearn', 'scikit-learn',
    'onnxruntime',
    'openai', 'anthropic', 'google-generativeai',
    'cerebras-cloud-sdk',
    'deepl', 'deep-translator',
    'reportlab', 'pdfplumber', 'img2pdf',
    'rarfile', 'py7zr',
    'pywebview', 'webview',
    'jaconv',
    'dayu-widgets', 'dayu-path',
    'msgpack', 'wget', 'largestinteriorrectangle',
]

BOOTSTRAP_LOG = None
try:
    from modules.utils.paths import get_log_dir as _get_bootstrap_log_dir
    BOOTSTRAP_LOG = os.path.join(_get_bootstrap_log_dir(create=True), 'bootstrap.log')
except Exception:
    BOOTSTRAP_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bootstrap.log')

def log(msg):
    # datetime invece di subprocess.getoutput('date /t'): i comandi 'date'
    # e 'time' sono specifici di Windows, lanciavano una shell due volte
    # per ogni messaggio e producevano una riga vuota su altri sistemi.
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(BOOTSTRAP_LOG, 'a', encoding='utf-8') as f:
        f.write(f'[{timestamp}] {msg}\n')
    logger.info(msg)

def check_package_installed(package_name):
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', package_name],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False

def install_package(package):
    try:
        log(f'Installing {package}...')
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        return True
    except Exception as e:
        log(f'Failed to install {package}: {e}')
        return False

def install_packages_batch(packages):
    try:
        packages_str = ' '.join(packages)
        log(f'Installing packages: {packages_str[:100]}...')
        # Lista di argomenti, non stringa con shell=True: con shell=True un
        # path di Python contenente spazi (es. "C:\Program Files\...") o un
        # nome pacchetto con metacaratteri di shell romperebbe il comando.
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '--upgrade'] + list(packages),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        return True
    except Exception as e:
        log(f'Batch install failed: {e}')
        return False

def get_missing_packages():
    missing = []
    for pkg in ESSENTIAL_PACKAGES:
        if not check_package_installed(pkg):
            missing.append(pkg)
    return missing

def run_bootstrap():
    # bootstrap.py e' solo per env sviluppo. In installazione
    # (%ProgramFiles% / marker .installed / KOMIC_TRANSLATE_INSTALLED=1) non deve
    # mai fare pip-install: il venv isolato lo crea il setup.
    try:
        from modules.utils.paths import is_bootstrap_gated as _is_gated
        if _is_gated():
            msg = ('Bootstrap disabilitato in installazione: usare il setup '
                   '(venv isolato), non pip-install all\'avvio.')
            try:
                log(msg)
            except Exception:
                pass
            logger.warning(msg)
            return False
    except ImportError:
        pass
    log('=== KomicTranslate Bootstrap Starting ===')
    log(f'Python: {sys.version}')

    missing = get_missing_packages()

    if not missing:
        log('All essential packages are installed.')
        return True

    log(f'Found {len(missing)} missing packages: {", ".join(missing[:10])}...')

    groups = [
        ['torch', 'torchvision', 'torchaudio'],
        ['transformers', 'sentencepiece', 'tokenizers'],
        ['paddleocr', 'paddlepaddle'],
        ['easyocr', 'doctr'],
        ['ultralytics', 'scipy', 'scikit-learn', 'onnxruntime'],
        ['openai', 'anthropic', 'google-generativeai', 'cerebras-cloud-sdk'],
        ['deepl', 'deep-translator', 'reportlab', 'pdfplumber', 'img2pdf'],
        ['rarfile', 'py7zr', 'pywebview'],
        ['stanza', 'jaconv', 'dayu-widgets', 'dayu-path'],
    ]

    for group in groups:
        group_to_install = [p for p in group if p in missing]
        if group_to_install:
            install_packages_batch(group_to_install)

    final_check = get_missing_packages()
    if final_check:
        log(f'Still missing after bootstrap: {final_check}')
        return False

    log('=== Bootstrap Completed Successfully ===')
    return True

if __name__ == '__main__':
    success = run_bootstrap()
    sys.exit(0 if success else 1)
