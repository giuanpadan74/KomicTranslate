"""ComicInfo.xml helpers (standard ComicRack/Anansi, singolare)."""

import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

FILENAME = "ComicInfo.xml"

FIELDS = [
    "Series", "Volume", "Number", "Title",
    "Writer", "Penciller", "CoverArtist", "Publisher", "Year",
    "Genre", "LanguageISO", "PageCount", "Summary",
    "Manga", "Translator",
]

DEFAULTS = {
    "Series": "",
    "Volume": "",
    "Number": "",
    "Title": "",
    "Writer": "",
    "Penciller": "",
    "Publisher": "",
    "Year": "",
    "Genre": "",
    "LanguageISO": "it",
    "PageCount": "",
    "Summary": "",
    "Manga": "YesAndRightToLeft",
    "Translator": "KomicTranslate",
}


def normalize(info: dict | None) -> dict:
    out = dict(DEFAULTS)
    for k, v in (info or {}).items():
        if k in FIELDS and v is not None:
            out[k] = str(v)
    return out


def to_xml(info: dict) -> str:
    data = normalize(info)
    root = ET.Element("ComicInfo")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    for key in FIELDS:
        val = data.get(key, "")
        if val == "" and key not in ("LanguageISO", "Translator", "Manga"):
            continue
        child = ET.SubElement(root, key)
        child.text = val
    # Pages: prima pagina come copertina
    try:
        pages = ET.SubElement(root, "Pages")
        ET.SubElement(pages, "Page", {"Image": "0", "Type": "FrontCover"})
    except Exception:
        pass
    raw = ET.tostring(root, encoding="unicode")
    try:
        return minidom.parseString(raw).toprettyxml(indent="  ", encoding=None)
    except Exception:
        return raw


def from_xml(xml_text: str) -> dict:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return {}
    out: dict = {}
    for child in root:
        if child.tag in FIELDS and child.text:
            out[child.tag] = child.text.strip()
    return normalize(out)


def sidecar_path(directory: str) -> str:
    return os.path.join(directory, FILENAME)


def read_sidecar(directory: str) -> dict | None:
    path = sidecar_path(directory)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return from_xml(f.read())
    except Exception:
        return None


def write_sidecar(directory: str, info: dict) -> str:
    os.makedirs(directory, exist_ok=True)
    path = sidecar_path(directory)
    xml_text = to_xml(info)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(xml_text if isinstance(xml_text, str) else str(xml_text))
    os.replace(tmp, path)
    return path


def diff_fields(old: dict, new: dict) -> list[tuple[str, str, str, bool]]:
    """Ritorna [(campo, vecchio, nuovo, diverso)]."""
    o, n = normalize(old), normalize(new)
    rows = []
    for key in FIELDS:
        rows.append((key, o.get(key, ""), n.get(key, ""), o.get(key, "") != n.get(key, "")))
    return rows
