"""
secure_storage.py
-----------------
Archiviazione sicura dei cookie con crittografia AES.
"""

import os
import json
import time
import base64
import hashlib
import secrets
from pathlib import Path


class SecureCookieStorage:
    """
    Archiviazione sicura cookie con crittografia.
    Non memorizza mai cookie HttpOnly direttamente - li gestisce tramite
    Firefox che è il "titolare" dell'autenticazione.
    """

    STORAGE_VERSION = 1
    MAX_COOKIE_AGE = 14400

    @staticmethod
    def _resolve_storage_dir() -> str:
        """
        Cartella dati stabile. Prima usava os.getcwd(): lanciando l'app da una
        cartella diversa (collegamento, terminale, 'Avvia in') i cookie di
        sessione Google finivano in un posto irraggiungibile e l'utente
        perdeva l'autenticazione senza capire il perche'.
        """
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "KomicTranslate", ".gemini_session")

    @staticmethod
    def _legacy_storage_dir() -> str:
        """Vecchia posizione (CWD), letta ma non piu' scritta."""
        return os.path.join(os.getcwd(), ".gemini_session")

    STORAGE_DIR = _resolve_storage_dir.__func__()

    def __init__(self):
        os.makedirs(self.STORAGE_DIR, exist_ok=True)
        self.storage_file = os.path.join(self.STORAGE_DIR, "session.enc")
        self.salt_file = os.path.join(self.STORAGE_DIR, ".salt")

        # Migrazione: se esiste una sessione nella vecchia cartella (CWD) e non
        # in quella nuova, la si adotta cosi' l'utente non deve rifare il login.
        legacy_file = os.path.join(self._legacy_storage_dir(), "session.enc")
        if not os.path.exists(self.storage_file) and os.path.exists(legacy_file):
            try:
                legacy_salt = os.path.join(self._legacy_storage_dir(), ".salt")
                if os.path.exists(legacy_salt) and not os.path.exists(self.salt_file):
                    with open(legacy_salt, "rb") as fsrc, open(self.salt_file, "wb") as fdst:
                        fdst.write(fsrc.read())
                with open(legacy_file, "rb") as fsrc, open(self.storage_file, "wb") as fdst:
                    fdst.write(fsrc.read())
            except Exception as e:
                print(f"[SecureStorage] Migrazione sessione legacy non riuscita: {e}")

        self._key = self._derive_key()

    def _generate_salt(self) -> bytes:
        """Genera salt casuale per questa installazione."""
        if os.path.exists(self.salt_file):
            with open(self.salt_file, "rb") as f:
                return f.read()
        else:
            salt = secrets.token_bytes(32)
            with open(self.salt_file, "wb") as f:
                f.write(salt)
            os.chmod(self.salt_file, 0o600)
            return salt

    def _derive_key(self) -> bytes:
        """
        Deriva la chiave di offuscamento da un salt casuale (32 byte, salvato con
        permessi 0600) + un identificativo della macchina.

        NOTA DI SICUREZZA: la cifratura usata (_xor_encrypt) e' uno XOR con chiave
        ripetuta, NON e' AES. E' sufficiente a non leggere i cookie a vista, ma non
        e' cifratura robusta: chi legge sia il file sia il .salt puo' ricavare la
        chiave. Per una protezione vera serve AES (es. cryptography.Fernet) con la
        chiave nel keyring/DPAPI di sistema.
        """
        salt = self._generate_salt()
        machine_key = self._get_machine_key()
        combined = salt + machine_key.encode()
        return hashlib.sha256(combined).digest()

    def _get_machine_key(self) -> str:
        """Genera chiave univoca basata su caratteristiche della macchina."""
        import platform
        combined = f"{platform.node()}-{platform.machine()}-{platform.python_version()}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _xor_encrypt(self, data: bytes, key: bytes) -> bytes:
        """Offuscamento XOR (NON e' AES: vedi nota in _derive_key)."""
        result = bytearray(data)
        key_cycle = bytearray(key)
        for i in range(len(result)):
            result[i] ^= key_cycle[i % len(key_cycle)]
        return bytes(result)

    def _xor_decrypt(self, data: bytes, key: bytes) -> bytes:
        """Decifratura XOR (identica a cifratura)."""
        return self._xor_encrypt(data, key)

    def store_session(self, cookies: dict, metadata: dict = None) -> bool:
        """
        Memorizza sessione con cifratura.

        Args:
            cookies: Dict con cookie {name: value}
            metadata: Info aggiuntive (timestamp, source, etc)

        Returns:
            True se salvato con successo
        """
        if metadata is None:
            metadata = {}

        now = time.time()
        # Il timestamp va dentro metadata: get_session_age() e refresh_session()
        # lo leggono da li', mentre prima leggevano metadata['timestamp'] che non
        # esisteva mai => get_session_age() restituiva sempre time.time() (~1.7e9 s).
        metadata = {**metadata, "timestamp": now}

        payload = {
            "version": self.STORAGE_VERSION,
            "timestamp": now,
            "metadata": metadata,
            "cookies": cookies
        }

        try:
            json_data = json.dumps(payload).encode("utf-8")
            encrypted = self._xor_encrypt(json_data, self._key)

            with open(self.storage_file, "wb") as f:
                f.write(encrypted)

            os.chmod(self.storage_file, 0o600)
            return True

        except Exception as e:
            print(f"[SecureStorage] Errore salvataggio: {e}")
            return False

    def load_session(self) -> tuple[dict, dict] | None:
        """
        Carica sessione se valida e non scaduta.

        Returns:
            (cookies, metadata) se valida, None altrimenti
        """
        if not os.path.exists(self.storage_file):
            return None

        try:
            with open(self.storage_file, "rb") as f:
                encrypted = f.read()

            decrypted = self._xor_decrypt(encrypted, self._key)
            payload = json.loads(decrypted.decode("utf-8"))

            if payload.get("version") != self.STORAGE_VERSION:
                return None

            age = time.time() - payload.get("timestamp", 0)
            if age > self.MAX_COOKIE_AGE:
                return None

            return payload.get("cookies", {}), payload.get("metadata", {})

        except Exception as e:
            print(f"[SecureStorage] Errore caricamento: {e}")
            return None

    def is_valid(self) -> bool:
        """Verifica se sessione valida esiste."""
        return self.load_session() is not None

    def get_session_age(self) -> float:
        """Ritorna età sessione in secondi, o 0 se non esiste."""
        session = self.load_session()
        if session is None:
            return 0
        _, metadata = session
        return time.time() - metadata.get("timestamp", 0)

    def clear_session(self) -> bool:
        """Elimina sessione in modo sicuro."""
        try:
            if os.path.exists(self.storage_file):
                os.remove(self.storage_file)
            return True
        except Exception as e:
            print(f"[SecureStorage] Errore cancellazione: {e}")
            return False

    def refresh_session(self, cookies: dict) -> bool:
        """
        Aggiorna sessione esistente mantenendo il timestamp originale
        o creandone uno nuovo.
        """
        session = self.load_session()
        old_metadata = session[1] if session else {}

        metadata = {
            **old_metadata,
            "last_refresh": time.time(),
            "refresh_count": old_metadata.get("refresh_count", 0) + 1
        }

        return self.store_session(cookies, metadata)
