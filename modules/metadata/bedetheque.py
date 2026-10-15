"""Provider Bedetheque (BD franco-belga): JSON autocomplete + scrape pagine.

Lezioni da ComicsBox applicate: niente eccezioni verso il chiamante,
scarto pagine di errore, encoding esplicito, quota request, label
distinte albo/serie, strip numero dalla query ('thorgal 3').
"""

import html
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

BASE = "https://www.bedetheque.com"
HEADERS = {"User-Agent": "KomicTranslate/1.0"}


def _decode(resp) -> str:
    raw = resp.content
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1252", errors="replace")


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _slug(text: str) -> str:
    ascii_txt = unicodedata.normalize(
        "NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"-+", "-", re.sub(r"[^A-Za-z0-9]+", "-", ascii_txt)
                  ).strip("-")


def _series_page(series_id: str, label: str) -> tuple[str, str] | None:
    """Ritorna (url, html) della pagina serie, provando gli slug plausibili."""
    if requests is None:
        return None
    short = re.split(r"\s+\(", label or "")[0].strip()
    candidates = []
    for txt in (label or "", short):
        slug = _slug(txt)
        if slug and slug not in candidates:
            candidates.append(slug)
    first_word = (re.findall(r"[A-Za-zÀ-ÿ]{4,}", short or "") or [""])[0]
    for slug in candidates:
        url = f"{BASE}/serie-{series_id}-BD-{slug}.html"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            page = _decode(resp)
            title = re.search(r"<title>(.*?)</title>", page, re.I | re.S)
            title_txt = _strip_tags(title.group(1)) if title else ""
            if first_word and first_word.lower() not in title_txt.lower():
                continue
            if re.search(r"404|non trouv|introuvable", title_txt, re.I):
                continue
            return url, page
        except Exception:
            continue
    return None


def _album_detail(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        page = _decode(resp)
        out: dict = {"LanguageISO": "fr", "source": "Bedetheque"}

        title = re.search(r"<title>(.*?)</title>", page, re.I | re.S)
        title_txt = _strip_tags(title.group(1)) if title else ""
        # 'Thorgal -1- La Magicienne trahie'
        m = re.match(r"^(.*?)\s*-(\d+[a-z]?)-\s*(.+)$", title_txt)
        if m:
            out["Series"] = m.group(1).strip()
            out["Number"] = m.group(2).strip()
            out["Title"] = html.unescape(m.group(3)).strip()
        elif title_txt:
            out["Series"] = html.unescape(title_txt).split(" - ")[0].strip()

        def _prop(name: str) -> str:
            pm = re.search(r'itemprop="%s"[^>]*>([^<]{1,200})<' % name, page)
            return _strip_tags(pm.group(1)) if pm else ""

        writers = [w.strip() for w in _prop("author").split(",") if w.strip()]
        # 'Rosinski, Grzegorz' -> 'Grzegorz Rosinski'
        fixed = []
        for w in writers:
            parts = [p.strip() for p in w.split(",")]
            fixed.append(f"{parts[1]} {parts[0]}" if len(parts) == 2 else w)
        if fixed:
            out["Writer"] = ", ".join(fixed)[:300]
        illus = _prop("illustrator")
        if illus:
            parts = [p.strip() for p in illus.split(",")]
            out["Penciller"] = (f"{parts[1]} {parts[0]}"
                                if len(parts) == 2 else illus)[:300]
        pub = _prop("publisher")
        if pub:
            out["Publisher"] = pub[:120]
        pages = _prop("numberOfPages")
        if pages and pages.isdigit():
            out["PageCount"] = pages

        meta = re.search(r'<meta name="description" content="([^"]{20,2000})"',
                         page, re.I)
        if meta:
            out["Summary"] = html.unescape(meta.group(1)).strip()[:2000]

        dlm = re.search(r"\b(?:EO|DL|DLM|DLQ|DLP)\s*(\d{2})/(\d{4})",
                        html.unescape(_strip_tags(page)))
        if dlm:
            out["Year"] = dlm.group(2)

        if not out.get("Series"):
            return None
        return out
    except Exception:
        return None


def search_bedetheque(query: str, limit: int = 5) -> list[dict]:
    query = (query or "").strip()
    if not query or requests is None:
        return []
    # 'thorgal 3' -> serie 'thorgal', albo 3 in cima
    wanted_number = ""
    m = re.match(r"^(.*?)\s+#?(\d{1,4})\s*$", query)
    search_query = query
    if m and not re.match(r"^\d+$", query):
        search_query, wanted_number = m.group(1).strip(), m.group(2)
    try:
        resp = requests.get(f"{BASE}/ajax/series", params={"term": search_query},
                            headers=HEADERS, timeout=15)
        series = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.warning(f"[ComicInfo] Bedetheque errore: {e}")
        return []
    out: list[dict] = []
    seen: set[str] = set()
    albo_quota = 10 if wanted_number else 3
    for entry in (series or [])[:limit]:
        sid = str(entry.get("id") or "")
        label = (entry.get("label") or "").strip()
        if not sid or not label:
            continue
        serie = _series_page(sid, label)
        if not serie:
            out.append({"source": "Bedetheque", "Series": label,
                        "LanguageISO": "fr"})
            continue
        _, page = serie
        out.append({"source": "Bedetheque", "Series": label,
                    "LanguageISO": "fr"})
        album_links = re.findall(
            r'href="(https://www\.bedetheque\.com/BD-[^"]+)"', page)
        # dedup mantenendo ordine, albo voluto prima
        uniq: list[str] = []
        for link in album_links:
            if link not in uniq:
                uniq.append(link)
        if wanted_number:
            uniq.sort(key=lambda u: 0 if re.search(
                r"[Tt]ome-%s(?:\D|$)" % wanted_number.lstrip("0"), u) or
                re.search(r"[Tt]ome-0*%s(?:\D|$)" % wanted_number, u) else 1)
        for link in uniq[:albo_quota]:
            if link in seen:
                continue
            seen.add(link)
            detail = _album_detail(link)
            if detail:
                out.append(detail)
            if len(out) >= limit * 2:
                break
        if len(out) >= limit * 2:
            break
    if wanted_number:
        out.sort(key=lambda c: 0 if (c.get("Number") or "").lstrip("0")
                 == wanted_number.lstrip("0") else 1)
    return out[:limit * 2]
