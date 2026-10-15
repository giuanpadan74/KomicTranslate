import logging
import os
import tempfile

from app.ui.messages import Messages

logger = logging.getLogger(__name__)


def normalize_ctpr_path(file_name: str) -> str:
    """Normalizza il path di destinazione e forza l'estensione .ctpr."""
    normalized = (file_name or "").strip()
    if not normalized:
        return ""
    if not normalized.lower().endswith(".ctpr"):
        normalized += ".ctpr"
    return os.path.abspath(normalized)


def validate_ctpr_target(file_name: str) -> tuple[bool, str]:
    """Verifica che la cartella di destinazione esista e sia scrivibile."""
    normalized = normalize_ctpr_path(file_name)
    if not normalized:
        return False, "Percorso file non valido."

    parent_dir = os.path.dirname(normalized)
    if not parent_dir or not os.path.isdir(parent_dir):
        return False, f"Cartella di destinazione non trovata:\n{parent_dir}"

    try:
        fd, probe_path = tempfile.mkstemp(
            prefix="ctpr_write_test_",
            suffix=".tmp",
            dir=parent_dir,
        )
        os.close(fd)
        os.remove(probe_path)
    except Exception as exc:
        return False, (
            "La cartella di destinazione non e' scrivibile.\n"
            f"Dettagli: {exc}"
        )

    return True, normalized


def execute_ctpr_save(parent, file_name: str, save_callback, operation_label: str) -> tuple[bool, str]:
    """Esegue il salvataggio .ctpr con validazione, log e feedback UI."""
    ok, target_or_error = validate_ctpr_target(file_name)
    if not ok:
        logger.error("[CTPR_SAVE] Target non valido per %s: %s", operation_label, target_or_error)
        Messages.show_error(parent, "Salvataggio progetto", target_or_error)
        return False, ""

    target_path = target_or_error
    logger.info("[CTPR_SAVE] Avvio %s -> %s", operation_label, target_path)

    try:
        success = bool(save_callback(target_path))
    except Exception as exc:
        logger.exception("[CTPR_SAVE] Eccezione durante %s -> %s", operation_label, target_path)
        Messages.show_error(
            parent,
            "Salvataggio progetto",
            f"Errore durante il salvataggio del progetto:\n{exc}",
        )
        return False, target_path

    if not success:
        logger.error("[CTPR_SAVE] Salvataggio fallito senza eccezione -> %s", target_path)
        detail = "La procedura di salvataggio non ha completato correttamente."
        if not os.path.exists(target_path):
            detail += "\nIl file .ctpr non e' stato creato."
        Messages.show_error(parent, "Salvataggio progetto", detail)
        return False, target_path

    if not os.path.exists(target_path):
        logger.error("[CTPR_SAVE] Callback OK ma file assente -> %s", target_path)
        Messages.show_error(
            parent,
            "Salvataggio progetto",
            "Il salvataggio ha restituito successo, ma il file .ctpr non esiste sul disco.",
        )
        return False, target_path

    if os.path.getsize(target_path) == 0:
        logger.error("[CTPR_SAVE] File .ctpr vuoto -> %s", target_path)
        Messages.show_error(
            parent,
            "Salvataggio progetto",
            "Il file .ctpr creato e' vuoto.",
        )
        return False, target_path

    logger.info(
        "[CTPR_SAVE] Salvataggio completato: %s (%d byte)",
        target_path,
        os.path.getsize(target_path),
    )
    return True, target_path
