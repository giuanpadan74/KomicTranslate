"""
get_gemini_cookie.py
--------------------
Estrae i cookie di Gemini da Firefox.
Copia il database cookies in una cartella temporanea per evitare problemi di lock.
"""

import os
import platform
import glob
import shutil
import sqlite3
import tempfile
import json
import time
from pathlib import Path

COOKIE_NAME_1 = "__Secure-1PSID"
COOKIE_NAME_2 = "__Secure-1PSIDTS"
DOMAIN = ".google.com"
COOKIE_CACHE_TTL = 3600  # 1 ora di cache


def _find_firefox_profile() -> str | None:
    """Trova il percorso del profilo Firefox predefinito."""
    if platform.system() == "Windows":
        profile_base = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles")
    elif platform.system() == "Darwin":
        profile_base = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
    else:
        profile_base = os.path.expanduser("~/.mozilla/firefox")
    
    if not os.path.exists(profile_base):
        return None
    
    # Cerca profili default
    profiles = glob.glob(os.path.join(profile_base, "*.default*"))
    if not profiles:
        return None
    
    # Usa il primo profilo trovato (solitamente quello predefinito)
    return profiles[0]


def _read_cookies_from_sqlite(db_path: str) -> dict | None:
    """Legge i cookie Gemini dal database SQLite."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Query per estrarre i cookie di Google
        cursor.execute("""
            SELECT name, value 
            FROM moz_cookies 
            WHERE host LIKE '%google.com%'
            AND (name = ? OR name = ?)
        """, (COOKIE_NAME_1, COOKIE_NAME_2))
        
        result = {}
        for name, value in cursor.fetchall():
            result[name] = value
        
        conn.close()
        
        if COOKIE_NAME_1 in result:
            return result
        return None
        
    except Exception as e:
        print(f"[get_gemini_cookie] Errore lettura SQLite: {e}")
        return None


def _get_cache_path() -> str:
    """Restituisce il percorso del file cache."""
    temp_dir = tempfile.gettempdir()
    return os.path.join(temp_dir, "gemini_cookies_cache.json")


def _load_cache() -> dict | None:
    """Carica i cookie dalla cache se validi."""
    cache_path = _get_cache_path()
    if not os.path.exists(cache_path):
        return None

    try:
        age = time.time() - os.path.getmtime(cache_path)
        if age > COOKIE_CACHE_TTL:
            return None

        with open(cache_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(cookies: dict) -> None:
    """Salva i cookie in cache."""
    try:
        cache_path = _get_cache_path()
        with open(cache_path, "w") as f:
            json.dump(cookies, f)
    except Exception:
        pass  # Non critico


def get_firefox_cookies() -> dict | None:
    """
    Restituisce i cookie Gemini da Firefox:
        { "__Secure-1PSID": "...", "__Secure-1PSIDTS": "..." }
    oppure None se non disponibili.

    Copia il database cookies in una cartella temporanea per evitare
    problemi di lock quando Firefox è aperto.
    """
    cached = _load_cache()
    if cached is not None:
        print("[get_gemini_cookie] Cookie caricati dalla cache.")
        return cached

    # Trova il profilo Firefox
    profile_path = _find_firefox_profile()
    if not profile_path:
        print("[get_gemini_cookie] Profilo Firefox non trovato.")
        print("[get_gemini_cookie] Avvia Firefox almeno una volta per creare il profilo.")
        return None

    cookies_file = os.path.join(profile_path, "cookies.sqlite")
    if not os.path.exists(cookies_file):
        print(f"[get_gemini_cookie] File cookies.sqlite non trovato in: {profile_path}")
        return None

    print(f"[get_gemini_cookie] Profilo trovato: {os.path.basename(profile_path)}")

    # Crea una copia temporanea del database
    temp_dir = tempfile.gettempdir()
    temp_cookies = os.path.join(temp_dir, "firefox_cookies_temp.sqlite")

    try:
        # Copia il file (funziona anche se Firefox è aperto)
        shutil.copy2(cookies_file, temp_cookies)
        print(f"[get_gemini_cookie] Database copiato in: {temp_cookies}")

        # Leggi i cookie dalla copia
        result = _read_cookies_from_sqlite(temp_cookies)

        # Pulisci il file temporaneo
        try:
            os.remove(temp_cookies)
        except Exception:
            pass  # Non critico se non riusciamo a eliminare il temp

        if result:
            print("[get_gemini_cookie] Cookie letti con successo.")
            _save_cache(result)
            return result
        else:
            print("[get_gemini_cookie] Cookie __Secure-1PSID non trovato.")
            print("[get_gemini_cookie] Assicurati di aver effettuato l'accesso a gemini.google.com in Firefox.")
            return None

    except PermissionError as e:
        print(f"[get_gemini_cookie] Errore di permessi durante la copia: {e}")
        print("[get_gemini_cookie] Prova a eseguire l'applicazione come amministratore.")
        return None
    except Exception as e:
        print(f"[get_gemini_cookie] Errore: {e}")
        return None
