"""Provider metadati: MangaDex (API) + ComicsBox (scraper leggero stdlib)."""

import html
import logging
import re
import urllib.parse

logger = logging.getLogger(__name__)

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


def _http_get(url, params=None, headers=None, timeout=15):
    if requests is None:
        raise RuntimeError("requests non disponibile")
    return requests.get(url, params=params, headers=headers, timeout=timeout)


# ---------------- MangaDex ---------------- #

def search_mangadex(query: str, limit: int = 5) -> list[dict]:
    """Cerca su MangaDex API (nessuna key). Ritorna candidati normalizzati."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        resp = _http_get(
            "https://api.mangadex.org/manga",
            params={
                "title": query,
                "limit": limit,
                "includes[]": ["author", "artist"],
                "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"],
            },
            headers={"User-Agent": "KomicTranslate/1.0"},
        )
        data = resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"[ComicInfo] MangaDex errore: {e}")
        return []
    out = []
    for item in data:
        attrs = item.get("attributes", {}) or {}
        rels = item.get("relationships", []) or []
        writers = [r.get("attributes", {}).get("name", "") for r in rels
                   if r.get("type") == "author"]
        artists = [r.get("attributes", {}).get("name", "") for r in rels
                   if r.get("type") == "artist"]
        titles = attrs.get("title", {}) or {}
        title = titles.get("en") or titles.get("ja-ro") or next(iter(titles.values()), "")
        desc = attrs.get("description", {}) or {}
        summary = desc.get("it") or desc.get("en") or next(iter(desc.values()), "")
        tags = [t.get("attributes", {}).get("name", {}).get("en", "")
                for t in (attrs.get("tags", []) or [])]
        out.append({
            "source": "MangaDex",
            "Series": title or "",
            "Writer": ", ".join(w for w in writers if w),
            "Penciller": ", ".join(a for a in artists if a),
            "Year": str(attrs.get("year") or ""),
            "Genre": ", ".join(g for g in tags if g)[:200],
            "Summary": (summary or "")[:2000],
            "LanguageISO": "it",
            "Manga": "YesAndRightToLeft",
        })
    return out


# ---------------- ComicsBox (scraper) ---------------- #

def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def search_comicsbox(query: str, limit: int = 5) -> list[dict]:
    """Scraper leggero (solo stdlib+requests): cerca serie italiane.

    Usa la ricerca interna del sito e le pagine serie/*. Fragile per
    natura: mai eccezioni verso il chiamante, ritorna [] se il layout cambia.
    """
    query = (query or "").strip()
    if not query:
        return []
    # 'dylan dog 400' -> cerca 'dylan dog' e mette l'albo 400 in cima
    # (la search interna con numero non trova nulla).
    wanted_number = ""
    m = re.match(r"^(.*?)\s+#?(\d{1,4})\s*$", query)
    search_query = query
    if m and not re.match(r"^\d+$", query):
        search_query, wanted_number = m.group(1).strip(), m.group(2)
    try:
        out: list[dict] = []
        seen: set[str] = set()
        # La ricerca e' POST /search.php con campi stringa+criterio
        # (GET ?q= risponde "specificare la serie"). Prova sia edizioni
        # italiane che serie straniere.
        for criterio in ("ita", "originali"):
            try:
                resp = _http_post_search(search_query, criterio)
                page = resp
            except Exception:
                continue
            serie_links = re.findall(r'href="(serie/[A-Z0-9_]+)"[^>]*>([^<]{2,120})<', page)
            albo_links = re.findall(r'href="(albo/[A-Z0-9_]+)"[^>]*>([^<]{2,120})<', page)
            # albo in coda ma con quota propria: le serie riempirebbero tutto.
            # Dettagli albo = 1 request l'uno: max 3, 10 se cerchi un numero.
            albo_quota = 10 if wanted_number else 3
            pool = (serie_links[:limit]
                    + albo_links[:albo_quota])
            for code, label in pool:
                if code in seen:
                    continue
                seen.add(code)
                detail = _fetch_comicsbox_detail(code)
                if detail:
                    detail["source"] = "ComicsBox"
                    if not detail.get("Series"):
                        detail["Series"] = _strip_tags(label)
                    out.append(detail)
                else:
                    out.append({"source": "ComicsBox", "Series": _strip_tags(label)})
                if len(out) >= limit * 2:
                    break
            if len(out) >= limit * 2:
                break
        # 'DANDADAN (J-Pop)' -> Series=DANDADAN, Publisher=J-Pop.
        # Ma '(giornale)'/'(libretto)' sono parte del nome serie, NON editore.
        _PUB_HINT = re.compile(
            r"editore|comics|mondadori|panini|disney|bonelli|pop\b|star\b"
            r"|bao|nerbini|api\b|npe|tunu|obelix|coconino|feltrinelli|magic press"
            r"|salda|lion\b|j-pop|edizioni", re.I)
        for cand in out:
            try:
                series = (cand.get("Series") or "").strip()
                if series and not cand.get("Publisher"):
                    m = re.match(r"^(.*?)\s*\(([^)]{2,60})\)\s*$", series)
                    if m and _PUB_HINT.search(m.group(2)):
                        cand["Series"] = m.group(1).strip()
                        cand["Publisher"] = m.group(2).strip()
            except Exception:
                pass
        if wanted_number:
            out.sort(key=lambda c: 0 if (c.get("Number") or "").lstrip("0") == wanted_number.lstrip("0") else 1)
            # Tentativo diretto albo: i codici sono SERIE_### ma la prima
            # serie trovata puo' essere quella sbagliata (giornale vs
            # libretto): prova i primi codici serie finche' uno risponde.
            try:
                found = any((c.get("Number") or "").lstrip("0") == wanted_number.lstrip("0") for c in out)
                if not found:
                    probe = _http_post_search(search_query, "ita")
                    tried = 0
                    for mcode in re.finditer(r'href="serie/([A-Z0-9_]+)"', probe):
                        if tried >= 4:
                            break
                        tried += 1
                        code = f"albo/{mcode.group(1)}_{int(wanted_number):03d}"
                        if code in seen:
                            continue
                        detail = _fetch_comicsbox_detail(code)
                        if detail and (detail.get("Number") or "").lstrip("0") == wanted_number.lstrip("0"):
                            detail["source"] = "ComicsBox"
                            out.insert(0, detail)
                            seen.add(code)
                            break
            except Exception:
                pass
        return out[:limit * 2]
    except Exception as e:
        logger.warning(f"[ComicInfo] ComicsBox errore: {e}")
        return []


def _decode(resp) -> str:
    """Il sito dichiara UTF-8 ma serve byte windows-1252: senza questo
    gli apostrofi diventano �."""
    raw = resp.content
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1252", errors="replace")


def _http_post_search(query: str, criterio: str) -> str:
    if requests is None:
        raise RuntimeError("requests non disponibile")
    resp = requests.post(
        "https://www.comicsbox.it/search.php",
        data={"stringa": query, "criterio": criterio},
        headers={"User-Agent": "KomicTranslate/1.0"},
        timeout=15,
    )
    resp.raise_for_status()
    return _decode(resp)


def _fetch_comicsbox_detail(code: str) -> dict | None:
    try:
        resp = _http_get(f"https://www.comicsbox.it/{code}",
                         headers={"User-Agent": "KomicTranslate/1.0"})
        page = _decode(resp)
        # Pagina di errore (es. albo indovinato inesistente): niente dati
        t_err = re.search(r"<title>(.*?)</title>", page, re.I | re.S)
        if t_err and re.search(r"ooops|non trovata|errore",
                               _strip_tags(t_err.group(1)), re.I):
            return None
        out: dict = {"LanguageISO": "it"}

        # h1 albo: 'Dylan Dog # 481 | Prima che sia l'alba'
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S | re.I)
        h1_text = _strip_tags(h1.group(1)) if h1 else ""
        m = re.match(r"^(.*?)\s*#\s*(\d+)\s*\|\s*(.+)$",
                     html.unescape(h1_text))
        if m:
            out["Series"] = m.group(1).strip()
            out["Number"] = m.group(2).strip()
            out["Title"] = m.group(3).strip()
        else:
            m2 = re.match(r"^(.*?)\s*#\s*(\d+)\s*$",
                          html.unescape(h1_text))
            if m2:
                out["Series"] = m2.group(1).strip()
                out["Number"] = m2.group(2).strip()
            elif h1_text:
                out["Series"] = html.unescape(h1_text).strip()
        if not out.get("Series"):
            # pagine serie: niente h1, ma <title>Dylan Dog :: ComicsBox</title>
            t = re.search(r"<title>(.*?)\s*::\s*ComicsBox</title>", page, re.I)
            if t:
                out["Series"] = html.unescape(_strip_tags(t.group(1))).strip()

        # sinossi: prima div.sinossi esplicito, poi div narrativo piu' lungo
        best = ""
        sm = re.search(r'<div class="sinossi"[^>]*>([\s\S]{50,4000}?)</div>',
                       page, re.I)
        if sm:
            best = html.unescape(_strip_tags(sm.group(1))).strip()
        if not best:
            for dm in re.finditer(
                    r'<div class="(?:testo|descrizione|sinossi|trama|scheda)[^"]*"[^>]*>([\s\S]{100,4000}?)</div>',
                    page, re.I):
                txt = html.unescape(_strip_tags(dm.group(1))).strip()
                if len(txt) > len(best):
                    best = txt
        if best:
            out["Summary"] = best[:2000]

        plain = html.unescape(_strip_tags(page))

        writers: list[str] = []
        pencillers: list[str] = []
        covers: list[str] = []

        def _credit_bucket(role: str) -> list[str] | None:
            r = (role or "").lower()
            if r in ("script", "testi", "soggetto", "sceneggiatura",
                     "storia", "testo"):
                return writers
            if r in ("art", "disegni", "matite", "chine"):
                return pencillers
            if r in ("cover", "copertina"):
                return covers
            return None

        # --- storie dell'albo (Topolino: N blocchi alboita_dettagli) ---
        # 'Personaggi | TITOLO | Nome (script) / Nome (art)' + 'NN pagine'
        stories: list[dict] = []
        dett_blocks = list(re.finditer(
            r'<div class="alboita_dettagli">([\s\S]{1,3000}?)</div>',
            page, re.I))
        for idx, dm in enumerate(dett_blocks):
            block_html = dm.group(1)
            seg_end = (dett_blocks[idx + 1].start()
                       if idx + 1 < len(dett_blocks) else len(page))
            seg_text = html.unescape(
                _strip_tags(page[dm.end():seg_end]))[:500]
            parts = [p.strip() for p in
                     _strip_tags(block_html).split("|")]
            parts = [p for p in (re.sub(r"\s+", " ", p).strip()
                                 for p in parts) if p]
            # titolo = parte in <strong> o la seconda riga
            tm = re.search(
                r'<span class="titolo_storia"><strong>(.*?)</strong></span>',
                block_html, re.I | re.S)
            title = (_strip_tags(tm.group(1)).strip() if tm
                     else (parts[1] if len(parts) > 1 else ""))
            characters = parts[0] if parts and not tm else (
                parts[0] if len(parts) > 2 else "")
            if tm and parts and parts[0] != title:
                characters = parts[0]
            creds: list[str] = []
            for cm in re.finditer(
                    r'<a href="/autore/[^"]*"[^>]*>([^<]{2,60})</a>\s*\((script|art|cover|testi|disegni|soggetto|sceneggiatura|storia|matite|chine|copertina|colors|colori)\)',
                    block_html, re.I):
                creds.append(f"{_strip_tags(cm.group(1)).strip()} "
                             f"({cm.group(2).lower()})")
            pgm = re.search(r"(\d{1,4})\s+pagine", seg_text, re.I)
            stories.append({
                "characters": characters,
                "title": html.unescape(title).strip(),
                "credits": creds,
                "pages": pgm.group(1) if pgm else "",
            })
        stories = [s for s in stories if s["title"]]
        if len(stories) > 1:
            # crediti aggregati di tutte le storie
            for s in stories:
                for c in s["credits"]:
                    cm = re.match(r"^(.*?)\s*\((\w+)\)\s*$", c)
                    if not cm:
                        continue
                    bucket = _credit_bucket(cm.group(2))
                    if bucket is not None and cm.group(1) not in bucket:
                        bucket.append(cm.group(1))
            lines = []
            for i, s in enumerate(stories, 1):
                line = f"{i}. {s['title']}"
                extra = " / ".join(s["credits"])
                if extra:
                    line += f" — {extra}"
                if s["pages"]:
                    line += f" ({s['pages']} pp.)"
                lines.append(line)
            out["_stories"] = lines

        # crediti 'Nome (script) / Nome (art)': link autore o testo libero
        for cm in re.finditer(
                r'<a href="/autore/[^"]*"[^>]*>([^<]{2,60})</a>\s*\((script|art|cover|testi|disegni|soggetto|sceneggiatura|storia|matite|chine|copertina)\)',
                page, re.I):
            bucket = _credit_bucket(cm.group(2))
            if bucket is not None:
                name = _strip_tags(cm.group(1)).strip()
                if name and name not in bucket:
                    bucket.append(name)
        if not writers and not pencillers:
            for cm in re.finditer(
                    r"([A-ZÀ-Þ][^()/<>]{2,50}?)\s*\((script|art|cover|testi|disegni|soggetto|sceneggiatura|storia|matite|chine|copertina)\)",
                    plain):
                bucket = _credit_bucket(cm.group(2))
                if bucket is not None:
                    name = cm.group(1).strip()
                    if name and name not in bucket:
                        bucket.append(name)
        if writers:
            out["Writer"] = ", ".join(writers)[:300]
        if pencillers:
            out["Penciller"] = ", ".join(pencillers)[:300]

        # 'Copertina di Cristiano Spadoni': prima la versione con link
        # (nome delimitato da </a>), poi fallback a esattamente 2 parole
        if not covers:
            cop = re.search(r"Copertina di\s+<a[^>]*>([^<]{2,60})</a>",
                            page, re.I)
            if not cop:
                cop = re.search(
                    r"Copertina di\s+([A-ZÀ-Þ][\w'’.\-]+\s+[A-ZÀ-Þ][\w'’.\-]+)",
                    plain)
            if cop:
                covers.append(_strip_tags(cop.group(1)).strip())
        if covers and not out.get("CoverArtist"):
            out["CoverArtist"] = ", ".join(covers)[:300]

        # meta description albo: '...collana Julia pubblicato da Sergio
        # Bonelli Editore nel Agosto del 2023 intitolato ...'
        meta = re.search(
            r'<meta name="description" content="([^"]{20,400})"', page, re.I)
        if meta:
            desc = html.unescape(meta.group(1))
            pm = re.search(r"pubblicato da (.+?) nel .*?(\d{4})", desc, re.I)
            if pm:
                out.setdefault("Publisher", pm.group(1).strip())
                out.setdefault("Year", pm.group(2))
        # header 'Sergio Bonelli Editore | Agosto 2023'
        if not out.get("Publisher") or not out.get("Year"):
            hm = re.search(
                r"([A-ZÀ-Þ][\w\s.'&()-]{2,60}Editore)\s*\|\s*(\w+\s+(\d{4}))",
                plain)
            if hm:
                out.setdefault("Publisher", hm.group(1).strip())
                out.setdefault("Year", hm.group(3))

        # '116 pagine'
        pgm = re.search(r"(\d{1,4})\s+pagine", plain, re.I)
        if pgm:
            out.setdefault("PageCount", pgm.group(1))

        # Elenco storie in coda alla sinossi (ComicInfo non ha un campo
        # storie: Summary resta leggibile da tutti i lettori)
        story_lines = out.pop("_stories", None)
        if story_lines:
            section = ("Storie contenute (%d):\n%s"
                       % (len(story_lines),
                          "\n".join("• " + line for line in story_lines)))
            if out.get("Summary"):
                out["Summary"] = out["Summary"].rstrip() + "\n\n" + section
            else:
                out["Summary"] = section

        if not out.get("Series"):
            return None
        return out
    except Exception:
        return None


def _fetch_comicsbox_search_fallback(query: str) -> list[dict]:
    return []


def search_all(query: str, use_mangadex: bool = True,
               use_comicsbox: bool = True, use_bedetheque: bool = True,
               limit: int = 5) -> list[dict]:
    results: list[dict] = []
    if use_mangadex:
        results.extend(search_mangadex(query, limit))
    if use_comicsbox:
        results.extend(search_comicsbox(query, limit))
    if use_bedetheque:
        try:
            from .bedetheque import search_bedetheque
            results.extend(search_bedetheque(query, limit))
        except Exception as e:
            logger.warning(f"[ComicInfo] Bedetheque errore: {e}")
    return results[: limit * 3]


def merge_candidates(picked: list[dict], base: dict | None = None) -> dict:
    """Unisce: MangaDex -> opera originale, ComicsBox -> edizione IT.

    I campi non vuoti dei picked vincono su base, con priorita' al primo.
    """
    from .comic_info import normalize
    merged = normalize(base)
    for cand in picked:
        for k, v in (cand or {}).items():
            if k == "source":
                continue
            if v and not merged.get(k):
                merged[k] = v
    return merged
