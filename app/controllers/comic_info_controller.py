"""Controller Scheda fumetto: dialog + sidecar + memoria progetto."""

import os
import re
import logging

from PySide6 import QtWidgets
from PySide6.QtCore import QSettings

from modules.metadata import comic_info as ci

logger = logging.getLogger(__name__)


def _project_directory(controller) -> str | None:
    files = getattr(controller, "image_files", []) or []
    idx = getattr(controller, "curr_img_idx", -1)
    if files and 0 <= idx < len(files):
        return os.path.dirname(files[idx])
    if files:
        return os.path.dirname(files[0])
    proj = getattr(controller, "project_file", None)
    if proj:
        return os.path.dirname(proj)
    return None


def _archive_source_directory(controller, image_path: str) -> str | None:
    """Se l'immagine proviene da un archivio, restituisce la cartella dell'archivio.

    Le immagini estratte da cbz/zip/pdf vivono in una cartella temporanea:
    il ComicInfo.xml va accanto all'archivio, non nel temp.
    """
    try:
        handler = getattr(controller, "file_handler", None)
        infos = getattr(handler, "archive_info", None) or []
        norm = os.path.normcase(os.path.abspath(image_path))
        for arch in infos:
            if not isinstance(arch, dict):
                continue
            for img in arch.get("extracted_images", []) or []:
                try:
                    if os.path.normcase(os.path.abspath(img)) == norm:
                        arc_path = arch.get("archive_path")
                        return os.path.dirname(os.path.abspath(arc_path)) if arc_path else None
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _last_image_directory(controller) -> str | None:
    """Cartella dell'ultima immagine caricata (image_files[-1])."""
    files = getattr(controller, "image_files", None) or []
    if files:
        last = files[-1]
        src = _archive_source_directory(controller, last)
        if src:
            return src
        try:
            return os.path.dirname(os.path.abspath(last))
        except Exception:
            return os.path.dirname(last)
    return _project_directory(controller)


def _existing_sidecar_path(directory: str) -> str | None:
    """Percorso del sidecar esistente, anche con maiuscole diverse
    (es. comicinfo.xml minuscolo)."""
    try:
        if not directory or not os.path.isdir(directory):
            return None
        for name in os.listdir(directory):
            if name.lower() == ci.FILENAME.lower():
                return os.path.join(directory, name)
    except Exception:
        pass
    return None


def _read_sidecar(directory: str | None) -> dict | None:
    if not directory:
        return None
    try:
        info = ci.read_sidecar(directory)
    except Exception:
        info = None
    if info:
        return info
    # Fallback case-insensitive (es. comicinfo.xml tutto minuscolo)
    path = _existing_sidecar_path(directory)
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                info = ci.from_xml(f.read())
            return info or None
        except Exception:
            return None
    return None


def _write_sidecar(directory: str, info: dict) -> str:
    """Scrive il sidecar (lo crea se non esiste). Se esiste una variante
    con nome diverso per maiuscole (su FS case-sensitive), riusa quel nome
    per non duplicare il file."""
    written = ci.write_sidecar(directory, info)
    try:
        existing = _existing_sidecar_path(directory)
        if (existing and os.path.normcase(existing) != os.path.normcase(written)
                and os.path.isfile(written)):
            with open(written, "r", encoding="utf-8") as f:
                content = f.read()
            with open(existing, "w", encoding="utf-8") as f:
                f.write(content)
            os.remove(written)
            return existing
    except Exception:
        pass
    return written


_PAGE_LIKE = re.compile(
    r"^(page|pag|img|image|scan|p|cap|ch|chapter)[\s_\-]*\d+.*$", re.I)
_NUMERIC_LIKE = re.compile(r"^\d+([\s_\-].*)?$")


def _parse_folder_name(folder: str) -> dict:
    """'Celestia (Manuele Fior)' -> Series=Celestia, Writer=Manuele Fior."""
    folder = (folder or "").strip()
    if not folder:
        return {}
    out: dict = {}
    # Autore tra parentesi tonde/quadre finali
    m = re.match(r"^(.*?)[\s_\-]+[\(\[](.*?)[\)\]]\s*$", folder)
    if m:
        out["Series"] = m.group(1).replace("_", " ").strip()
        out["Writer"] = m.group(2).replace("_", " ").strip()
        return out
    # 'Serie - Autore'
    m = re.match(r"^(.*?)\s+-\s+(.+)$", folder)
    if m and len(m.group(2).split()) <= 4:
        out["Series"] = m.group(1).replace("_", " ").strip()
        out["Writer"] = m.group(2).replace("_", " ").strip()
        return out
    out["Series"] = folder.replace("_", " ").strip()
    return out


def _guess_series(files: list[str]) -> dict:
    """Se il nome file e' tipo page_025_0, usa la cartella, non il file."""
    if not files:
        return {}
    first_base = os.path.splitext(os.path.basename(files[0]))[0]
    folder = os.path.basename(os.path.dirname(files[0]))
    generic = bool(_PAGE_LIKE.match(first_base) or _NUMERIC_LIKE.match(first_base))
    if generic and folder:
        return _parse_folder_name(folder)
    if folder and len(files) == 1:
        # singola immagine con nome sensato: preferisci comunque la cartella
        # se il file sembra una pagina numerata, altrimenti il file
        return _parse_folder_name(folder) if generic else {
            "Series": first_base.replace("_", " ").strip()}
    return {"Series": first_base.replace("_", " ").strip()}


def _base_info(controller) -> dict:
    info = dict(getattr(controller, "comic_info", None) or {})
    files = getattr(controller, "image_files", None) or []
    if files and not info.get("Series"):
        try:
            info.update({k: v for k, v in _guess_series(files).items()
                         if v and not info.get(k)})
        except Exception:
            pass
    if not files and not info:
        # Nessuna immagine aperta: riparti dagli ultimi valori salvati
        try:
            settings = QSettings("ComicLabs", "KomicTranslate")
            settings.beginGroup("comic_info")
            for key in settings.childKeys():
                info[key] = settings.value(key, "")
            settings.endGroup()
        except Exception:
            pass
    if not info.get("PageCount") and getattr(controller, "image_files", None):
        info["PageCount"] = str(len(controller.image_files))
    try:
        from PySide6.QtCore import QCoreApplication
        t = getattr(controller, "t_combo", None)
        if t is not None and not info.get("LanguageISO"):
            lang = t.currentText()
            mapping = {"Italiano": "it", "English": "en", "Japanese": "ja",
                       "Français": "fr", "Español": "es", "Deutsch": "de"}
            info["LanguageISO"] = mapping.get(lang, "it")
    except Exception:
        pass
    return ci.normalize(info)


def open_comic_info_dialog(controller) -> dict | None:
    # Cartella dell'ultima immagine caricata: e' li' che il ComicInfo.xml
    # viene letto e (su OK) creato se mancante.
    directory = _last_image_directory(controller)
    existing = _read_sidecar(directory)
    # la memoria progetto vince sul sidecar se piu' recente/non vuota
    mem = getattr(controller, "comic_info", None)
    base = _base_info(controller)
    if existing and not mem:
        base = dict(existing)

    from app.ui.comic_info_dialog import ComicInfoDialog
    dlg = ComicInfoDialog(base, existing, controller)
    if dlg.exec() != QtWidgets.QDialog.Accepted:
        return None
    result = dlg.result()
    controller.comic_info = result

    # 1. su OK chiede sempre dove salvare: il dialogo parte dalla cartella
    #    dell'ultima immagine caricata (o dalla home se non c'e').
    start_dir = (directory if directory and os.path.isdir(directory)
                 else os.path.expanduser("~"))
    directory = QtWidgets.QFileDialog.getExistingDirectory(
        controller,
        "Dove salvare ComicInfo.xml",
        start_dir,
    ) or None
    if directory:
        # Su OK il file viene creato se non esiste, aggiornato se esiste.
        already_there = _existing_sidecar_path(directory) is not None
        try:
            written = _write_sidecar(directory, result)
        except Exception as e:
            logger.warning(f"[ComicInfo] sidecar non scritto: {e}")
            QtWidgets.QMessageBox.warning(
                controller, "ComicInfo.xml",
                f"Non riesco a scrivere in:\n{directory}\n{e}")
        else:
            if not os.path.isfile(written):
                logger.warning(f"[ComicInfo] sidecar non trovato dopo la scrittura: {written}")
                QtWidgets.QMessageBox.warning(
                    controller, "ComicInfo.xml",
                    f"Non riesco a scrivere in:\n{directory}")
            elif not already_there:
                logger.info(f"[ComicInfo] creato: {written}")
            QtWidgets.QMessageBox.information(
                controller, "ComicInfo.xml",
                f"Salvato in:\n{written}")
    else:
        QtWidgets.QMessageBox.information(
            controller, "ComicInfo.xml",
            "Salvataggio annullato: scheda tenuta solo in memoria.")

    # 2. ricorda ultimi valori
    try:
        settings = QSettings("ComicLabs", "KomicTranslate")
        settings.beginGroup("comic_info")
        for k, v in result.items():
            settings.setValue(k, v)
        settings.endGroup()
    except Exception:
        pass
    return result


def get_comic_info_xml(controller) -> str | None:
    info = getattr(controller, "comic_info", None)
    if not info:
        directory = _last_image_directory(controller)
        info = _read_sidecar(directory)
        if not info:
            # Fallback alla cartella dell'immagine corrente/progetto
            info = _read_sidecar(_project_directory(controller))
    if not info:
        return None
    xml_text = ci.to_xml(info)
    return xml_text if isinstance(xml_text, str) else str(xml_text)
