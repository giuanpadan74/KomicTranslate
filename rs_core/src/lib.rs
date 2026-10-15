use pyo3::prelude::*;
use pyo3::types::PyDict;
use regex::Regex;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::OnceLock;

// ---------------------------------------------------------------------------
// Helpers: state machine (port of translator_utils._extract_json_object)
// ---------------------------------------------------------------------------

fn extract_braced(text: &str, start: usize) -> Option<String> {
    let bytes = text.as_bytes();
    if start >= text.len() || bytes[start] != b'{' {
        return None;
    }
    let mut brace: i64 = 0;
    let mut in_str = false;
    let mut esc = false;
    // iterate char-by-char to stay unicode-safe
    let mut end_byte: Option<usize> = None;
    for (rel, ch) in text[start..].char_indices() {
        if in_str {
            if esc {
                esc = false;
            } else if ch == '\\' {
                esc = true;
            } else if ch == '"' {
                in_str = false;
            }
        } else if ch == '"' {
            in_str = true;
        } else if ch == '{' {
            brace += 1;
        } else if ch == '}' {
            brace -= 1;
            if brace == 0 {
                end_byte = Some(start + rel + ch.len_utf8());
                break;
            }
        }
    }
    end_byte.map(|e| text[start..e].to_string())
}

#[pyfunction]
fn extract_json_object_rs(text: &str) -> Option<String> {
    extract_json_object(text)
}

fn extract_json_object(text: &str) -> Option<String> {
    // 1. code fence ```json ... ```
    if let Some(fence_start) = text.find("```") {
        if let Some(fence_end_rel) = text[fence_start..].find("```") {
            // careful: find first fence then second fence
            let first = fence_start;
            let after_first = &text[first..];
            // locate closing fence after opening line
            let open_end = after_first.find('\n').map(|i| first + i).unwrap_or(first + 3);
            let rest = &text[open_end..];
            if let Some(close_rel) = rest.find("```") {
                let inner = &rest[..close_rel];
                if let Some(s) = inner.find('{') {
                    if let Some(obj) = extract_braced(inner, s) {
                        return Some(obj);
                    }
                }
            }
            let _ = fence_end_rel;
        }
    }
    // 2. first '{' in whole text
    text.find('{')
        .and_then(|s| extract_braced(text, s))
}

fn is_word_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

fn quote_bare_block_keys(text: &str) -> String {
    // Port of BARE_BLOCK_KEY_PATTERN = (?<!["\w])block_(\d+)(\s*[:=])
    // `regex` crate has no look-around: manual scan.
    let bytes = text.as_bytes();
    let mut out = String::with_capacity(text.len() + 16);
    let mut i = 0usize;
    while i < bytes.len() {
        let remaining = &text[i..];
        // check "block_" prefix (case-sensitive like LLM output; Python regex is IGNORECASE
        // but bare keys are always lowercase in practice — handle both by lowercase compare)
        let matches_block = remaining.len() >= 6
            && remaining.as_bytes()[..6].eq_ignore_ascii_case(b"block_");
        if matches_block {
            // preceding char guard
            let prev_ok = if i == 0 {
                true
            } else {
                let p = bytes[i - 1];
                p != b'"' && !is_word_byte(p)
            };
            if prev_ok {
                // parse digits
                let mut j = i + 6;
                while j < bytes.len() && bytes[j].is_ascii_digit() {
                    j += 1;
                }
                if j > i + 6 {
                    // parse optional spaces + [: =]
                    let mut k = j;
                    while k < bytes.len() && (bytes[k] == b' ' || bytes[k] == b'\t' || bytes[k] == b'\n' || bytes[k] == b'\r') {
                        k += 1;
                    }
                    if k < bytes.len() && (bytes[k] == b':' || bytes[k] == b'=') {
                        let digits = &text[i + 6..j];
                        let sep = &text[j..k + 1];
                        out.push('"');
                        out.push_str(&text[i..i + 6]);
                        out.push_str(digits);
                        out.push('"');
                        out.push_str(sep);
                        i = k + 1;
                        continue;
                    }
                }
            }
        }
        // push current char (unicode-safe)
        let ch = remaining.chars().next().unwrap();
        out.push(ch);
        i += ch.len_utf8();
    }
    out
}

#[pyfunction]
fn quote_bare_block_keys_rs(text: &str) -> String {
    quote_bare_block_keys(text)
}

fn unescape_json_string(s: &str) -> String {
    s.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\'", "'")
        .replace("\\\"", "\"")
        .replace("\\\\", "\\")
}

fn clean_regex_value(raw: &str) -> String {
    let mut value = raw.trim().to_string();
    if value.starts_with('"') && value.ends_with('"') && value.len() >= 2 {
        let inner = &value[1..value.len() - 1];
        // try json loads of the quoted string
        let quoted = format!("\"{}\"", inner.replace('"', "\\\""));
        let _ = quoted; // best-effort below
        match serde_json::from_str::<String>(&value) {
            Ok(s) => return s,
            Err(_) => value = inner.to_string(),
        }
    }
    if value.starts_with('\'') && value.ends_with('\'') && value.len() >= 2 {
        value = value[1..value.len() - 1].to_string();
    }
    unescape_json_string(&value).trim().to_string()
}

// regex rescue: "block_N": "value" (dotall)
fn repair_truncated_json(text: &str) -> HashMap<String, String> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| {
        Regex::new(r#""block_(\d+)"\s*:\s*"((?:[^"\\]|\\.)*)""#).unwrap()
    });
    let mut out: HashMap<String, String> = HashMap::new();
    for cap in re.captures_iter(text) {
        let idx = cap[1].to_string();
        let val = unescape_json_string(&cap[2]);
        let key = format!("block_{}", idx);
        // keep longest non-empty like Python merge
        match out.get(&key) {
            Some(prev) if prev.trim().len() >= val.trim().len() && !val.trim().is_empty() => {}
            _ => {
                out.insert(key, val);
            }
        }
    }
    // last-block / unescaped-quotes rescue
    for (k, v) in repair_last_block(text) {
        match out.get(&k) {
            Some(prev) if prev.trim().len() >= v.trim().len() => {}
            _ => {
                out.insert(k, v);
            }
        }
    }
    out
}

fn repair_last_block(text: &str) -> HashMap<String, String> {
    static START_RE: OnceLock<Regex> = OnceLock::new();
    static NEXT_RE: OnceLock<Regex> = OnceLock::new();
    static CLOSE_RE: OnceLock<Regex> = OnceLock::new();
    let start_re =
        START_RE.get_or_init(|| Regex::new(r#""block_(\d+)"\s*:\s*""#).unwrap());
    let next_re =
        NEXT_RE.get_or_init(|| Regex::new(r#""\s*,\s*"block_(\d+)"\s*:"#).unwrap());
    let close_re = CLOSE_RE.get_or_init(|| Regex::new(r#""\s*\}"#).unwrap());
    let mut out = HashMap::new();
    let mut pos = 0usize;
    while pos < text.len() {
        let m = match start_re.find_at(text, pos) {
            Some(m) => m,
            None => break,
        };
        let caps = start_re.captures(&text[m.start()..m.end()]).unwrap();
        let idx: String = caps[1].to_string();
        let value_start = m.end();
        let remaining = &text[value_start..];
        let next_pos = next_re.find(remaining).map(|mm| mm.start());
        let close_pos = close_re.find(remaining).map(|mm| mm.start());
        let value_end = match (next_pos, close_pos) {
            (Some(n), Some(c)) => value_start + n.min(c),
            (Some(n), None) => value_start + n,
            (None, Some(c)) => value_start + c,
            (None, None) => text.len(),
        };
        let raw = &text[value_start..value_end.max(value_start)];
        out.insert(format!("block_{}", idx), unescape_json_string(raw));
        if value_end <= pos {
            break;
        }
        pos = value_end.max(m.end());
        if pos >= text.len() {
            break;
        }
    }
    out
}

fn recover_blocks_with_regex(text: &str) -> HashMap<String, String> {
    // Port of BLOCK_LINE_PATTERN without look-ahead (unsupported by `regex` crate):
    // header = "?block_N"? \s* [:=] ; value = slice fino al prossimo header o alla '}' finale.
    static HEAD: OnceLock<Regex> = OnceLock::new();
    let head = HEAD.get_or_init(|| {
        Regex::new(r#"(?i)"?block_(\d+)"?\s*[:=]"#).unwrap()
    });
    let matches: Vec<(usize, usize, String)> = head
        .captures_iter(text)
        .map(|c| {
            let m = c.get(0).unwrap();
            (m.start(), m.end(), c[1].to_string())
        })
        .collect();
    let mut out = HashMap::new();
    for (idx, (s, e, num)) in matches.iter().enumerate() {
        let value_start = *e;
        let value_end = if idx + 1 < matches.len() {
            matches[idx + 1].0
        } else {
            // fino alla '}' finale se presente, altrimenti fine testo
            match text[value_start..].rfind('}') {
                Some(rel) => value_start + rel,
                None => text.len(),
            }
        };
        if value_end < value_start {
            continue;
        }
        let raw = text[value_start..value_end].trim().trim_end_matches(',').trim();
        // ripulisci eventuale coda "} / ``` rimasto dall'rfind mancato
        let raw = raw.trim_end_matches('}').trim();
        if raw.is_empty() {
            continue;
        }
        out.insert(format!("block_{}", num), clean_regex_value(raw));
        let _ = s;
    }
    out
}

// ---------------------------------------------------------------------------
// Normalization (port of normalize_translation_payload)
// ---------------------------------------------------------------------------

fn normalize_block_key(raw: &str) -> Option<String> {
    let key = raw.trim().trim_matches('"').trim_matches('\'');
    if key.chars().all(|c| c.is_ascii_digit()) && !key.is_empty() {
        return Some(format!("block_{}", key));
    }
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"(?i)block_(\d+)").unwrap());
    re.captures(key).map(|c| format!("block_{}", &c[1]))
}

fn normalize_value(v: &Value) -> String {
    match v {
        Value::Null => String::new(),
        Value::String(s) => s.trim().to_string(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Object(map) => {
            for k in ["it", "translation", "target", "text", "fr", "source"] {
                if let Some(inner) = map.get(k) {
                    return normalize_value(inner);
                }
            }
            serde_json::to_string(v).unwrap_or_default()
        }
        Value::Array(_) => serde_json::to_string(v).unwrap_or_default(),
    }
}

fn pick_translation_value(map: &serde_json::Map<String, Value>) -> String {
    for k in ["it", "translation", "target", "text", "fr", "source"] {
        if let Some(v) = map.get(k) {
            return normalize_value(v);
        }
    }
    String::new()
}

fn normalize_payload(data: &Value) -> HashMap<String, String> {
    match data {
        Value::Object(map) => {
            // nested payload
            for k in ["translation", "translations", "result", "results", "data"] {
                if let Some(inner) = map.get(k) {
                    if inner.is_object() || inner.is_array() {
                        return normalize_payload(inner);
                    }
                }
            }
            let mut out = HashMap::new();
            for (k, v) in map {
                if let Some(bk) = normalize_block_key(k) {
                    out.insert(bk, normalize_value(v));
                }
            }
            out
        }
        Value::Array(arr) => {
            let mut out = HashMap::new();
            for item in arr {
                if let Value::Object(map) = item {
                    let id_val = map
                        .get("id")
                        .or_else(|| map.get("block_id"))
                        .or_else(|| map.get("block"));
                    let bk = match id_val {
                        Some(Value::Number(n)) => Some(format!("block_{}", n)),
                        Some(Value::String(s)) => normalize_block_key(s),
                        _ => None,
                    };
                    if let Some(bk) = bk {
                        out.insert(bk, pick_translation_value(map));
                    }
                }
            }
            out
        }
        _ => HashMap::new(),
    }
}

// ---------------------------------------------------------------------------
// Validation report (port of validate_translation_integrity)
// ---------------------------------------------------------------------------

fn build_report(
    py: Python,
    payload: &HashMap<String, String>,
    expected: usize,
    source: &str,
) -> PyResult<Py<PyDict>> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"(?i)block_(\d+)").unwrap());
    let mut found: HashMap<usize, &String> = HashMap::new();
    for (k, v) in payload {
        if let Some(c) = re.captures(k) {
            if let Ok(idx) = c[1].parse::<usize>() {
                found.insert(idx, v);
            }
        }
    }
    let is_one_based = !found.contains_key(&0) && found.contains_key(&expected) && expected > 0;
    let (start, end) = if is_one_based {
        (1usize, expected + 1)
    } else {
        (0usize, expected)
    };
    let mut missing = Vec::new();
    let mut empty = Vec::new();
    for i in start..end {
        match found.get(&i) {
            None => missing.push(format!("block_{}", i)),
            Some(v) => {
                let t = v.trim().to_lowercase();
                if t.is_empty() || t == "null" || t == "none" || t == "n/a" {
                    empty.push(format!("block_{}", i));
                }
            }
        }
    }
    let is_valid = missing.is_empty() && empty.is_empty();
    let d = PyDict::new_bound(py);
    d.set_item("is_valid", is_valid)?;
    d.set_item("missing_blocks", &missing)?;
    d.set_item("empty_blocks", &empty)?;
    d.set_item("total_found", found.len())?;
    d.set_item("expected", expected)?;
    d.set_item("error", py.None())?;
    d.set_item("source", source)?;
    Ok(d.unbind())
}

#[pyfunction]
fn parse_translation_payload_rs(
    py: Python,
    raw_text: &str,
    expected_count: usize,
) -> PyResult<(HashMap<String, String>, Py<PyDict>)> {
    let text = raw_text.trim();
    if text.is_empty() {
        let d = PyDict::new_bound(py);
        d.set_item("is_valid", false)?;
        d.set_item("missing_blocks", Vec::<String>::new())?;
        d.set_item("empty_blocks", Vec::<String>::new())?;
        d.set_item("total_found", 0)?;
        d.set_item("expected", expected_count)?;
        d.set_item("error", "Risposta vuota.")?;
        d.set_item("source", "empty")?;
        return Ok((HashMap::new(), d.unbind()));
    }
    // candidates: text + extracted
    let mut candidates: Vec<String> = vec![text.to_string()];
    if let Some(ex) = extract_json_object(text) {
        if ex != text {
            candidates.push(ex);
        }
    }
    for cand in &candidates {
        if let Ok(v) = serde_json::from_str::<Value>(cand) {
            let norm = normalize_payload(&v);
            if !norm.is_empty() {
                let rep = build_report(py, &norm, expected_count, "json")?;
                return Ok((norm, rep));
            }
        }
    }
    // bare keys repair
    let quoted = quote_bare_block_keys(text);
    if quoted != text {
        let mut cands = vec![quoted.clone()];
        if let Some(ex) = extract_json_object(&quoted) {
            if ex != quoted {
                cands.push(ex);
            }
        }
        for cand in &cands {
            if cand.is_empty() {
                continue;
            }
            if let Ok(v) = serde_json::from_str::<Value>(cand) {
                let norm = normalize_payload(&v);
                if !norm.is_empty() {
                    let rep = build_report(py, &norm, expected_count, "repair")?;
                    return Ok((norm, rep));
                }
            }
        }
    }
    // truncated repair
    let repaired = repair_truncated_json(text);
    if !repaired.is_empty() {
        let rep = build_report(py, &repaired, expected_count, "repair")?;
        return Ok((repaired, rep));
    }
    // regex fallback
    let via_regex = recover_blocks_with_regex(text);
    if !via_regex.is_empty() {
        let rep = build_report(py, &via_regex, expected_count, "regex")?;
        return Ok((via_regex, rep));
    }
    let d = PyDict::new_bound(py);
    d.set_item("is_valid", false)?;
    d.set_item("missing_blocks", Vec::<String>::new())?;
    d.set_item("empty_blocks", Vec::<String>::new())?;
    d.set_item("total_found", 0)?;
    d.set_item("expected", expected_count)?;
    d.set_item(
        "error",
        "Impossibile ricostruire un payload di traduzione valido.",
    )?;
    d.set_item("source", "unrecoverable")?;
    Ok((HashMap::new(), d.unbind()))
}

#[pymodule]
fn komic_core_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_json_object_rs, m)?)?;
    m.add_function(wrap_pyfunction!(quote_bare_block_keys_rs, m)?)?;
    m.add_function(wrap_pyfunction!(parse_translation_payload_rs, m)?)?;
    m.add_function(wrap_pyfunction!(bbox_polygon_overlap_ratio_rs, m)?)?;
    m.add_function(wrap_pyfunction!(filter_bboxes_by_polygon_rs, m)?)?;
    m.add_function(wrap_pyfunction!(simplify_outer_border_polygon_rs, m)?)?;
    m.add_function(wrap_pyfunction!(is_point_in_ellipse_rs, m)?)?;
    m.add_function(wrap_pyfunction!(span_at_y_rs, m)?)?;
    m.add_function(wrap_pyfunction!(hyphen_wrap_rs, m)?)?;
    m.add_function(wrap_pyfunction!(hyphen_fill_rs, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_iou_rs, m)?)?;
    m.add_function(wrap_pyfunction!(do_rectangles_overlap_rs, m)?)?;
    m.add_function(wrap_pyfunction!(does_rectangle_fit_rs, m)?)?;
    m.add_function(wrap_pyfunction!(is_mostly_contained_rs, m)?)?;
    m.add_function(wrap_pyfunction!(match_bubble_index_rs, m)?)?;
    m.add_function(wrap_pyfunction!(merge_bounding_boxes_rs, m)?)?;
    m.add_function(wrap_pyfunction!(edge_support_ratio_rs, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Geometria poligoni / ellissi (port di utils/polygon_region.py,
// utils/ellipse_mask.py::is_point_in_ellipse, rendering/polygon_text_layout::_span_at_y)
// Senza opencv: raster scanline per l'overlap, matematica pura per il resto.
// ---------------------------------------------------------------------------

fn to_pts_i32(polygon: &[Vec<i32>]) -> Option<Vec<[i32; 2]>> {
    let mut pts = Vec::with_capacity(polygon.len());
    for p in polygon {
        if p.len() != 2 {
            return None;
        }
        pts.push([p[0], p[1]]);
    }
    if pts.len() < 3 {
        return None;
    }
    Some(pts)
}

fn poly_spans_at_y(poly: &[[f64; 2]], y: f64) -> Vec<(f64, f64)> {
    let mut xs: Vec<f64> = Vec::new();
    let n = poly.len();
    for i in 0..n {
        let (x1, y1) = (poly[i][0], poly[i][1]);
        let (x2, y2) = (poly[(i + 1) % n][0], poly[(i + 1) % n][1]);
        if y1 == y2 {
            continue;
        }
        if (y1 <= y && y < y2) || (y2 <= y && y < y1) {
            let ratio = (y - y1) / (y2 - y1);
            xs.push(x1 + ratio * (x2 - x1));
        }
    }
    xs.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let mut spans = Vec::new();
    let mut k = 0usize;
    while k + 1 < xs.len() {
        spans.push((xs[k], xs[k + 1]));
        k += 2;
    }
    spans
}

fn overlap_ratio_scanline(bbox: &[i32; 4], poly: &[[i32; 2]]) -> f64 {
    let (x1, y1, x2, y2) = (bbox[0], bbox[1], bbox[2], bbox[3]);
    if x1 >= x2 || y1 >= y2 {
        return 0.0;
    }
    let pf: Vec<[f64; 2]> = poly.iter().map(|p| [p[0] as f64, p[1] as f64]).collect();
    let rect_area = ((x2 - x1 + 1) as f64) * ((y2 - y1 + 1) as f64);
    if rect_area <= 0.0 {
        return 0.0;
    }
    let rx0 = x1 as f64;
    let rx1 = x2 as f64 + 1.0;
    let mut overlap = 0.0;
    for y in y1..=y2 {
        let spans = poly_spans_at_y(&pf, y as f64);
        for (a, b) in spans {
            let lo = a.max(rx0);
            let hi = b.min(rx1);
            if hi > lo {
                overlap += hi - lo;
            }
        }
    }
    (overlap / rect_area).clamp(0.0, 1.0)
}

#[pyfunction]
#[pyo3(signature = (text, width, initial_indent="", subsequent_indent="", expand_tabs=true, replace_whitespace=true, fix_sentence_endings=false, break_long_words=true, drop_whitespace=true, break_on_hyphens=true, hyphenate_broken_words=true, tabsize=8, max_lines=None, placeholder=" [...]"))]
fn hyphen_wrap_rs(
    text: &str,
    width: usize,
    initial_indent: &str,
    subsequent_indent: &str,
    expand_tabs: bool,
    replace_whitespace: bool,
    fix_sentence_endings: bool,
    break_long_words: bool,
    drop_whitespace: bool,
    break_on_hyphens: bool,
    hyphenate_broken_words: bool,
    tabsize: usize,
    max_lines: Option<usize>,
    placeholder: &str,
) -> PyResult<Vec<String>> {
    wrap_impl(
        text,
        width,
        initial_indent,
        subsequent_indent,
        expand_tabs,
        replace_whitespace,
        fix_sentence_endings,
        break_long_words,
        drop_whitespace,
        break_on_hyphens,
        hyphenate_broken_words,
        tabsize,
        max_lines,
        placeholder,
    )
    .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
}

#[pyfunction]
#[pyo3(signature = (text, width, initial_indent="", subsequent_indent="", expand_tabs=true, replace_whitespace=true, fix_sentence_endings=false, break_long_words=true, drop_whitespace=true, break_on_hyphens=true, hyphenate_broken_words=true, tabsize=8, max_lines=None, placeholder=" [...]"))]
fn hyphen_fill_rs(
    text: &str,
    width: usize,
    initial_indent: &str,
    subsequent_indent: &str,
    expand_tabs: bool,
    replace_whitespace: bool,
    fix_sentence_endings: bool,
    break_long_words: bool,
    drop_whitespace: bool,
    break_on_hyphens: bool,
    hyphenate_broken_words: bool,
    tabsize: usize,
    max_lines: Option<usize>,
    placeholder: &str,
) -> PyResult<String> {
    wrap_impl(
        text,
        width,
        initial_indent,
        subsequent_indent,
        expand_tabs,
        replace_whitespace,
        fix_sentence_endings,
        break_long_words,
        drop_whitespace,
        break_on_hyphens,
        hyphenate_broken_words,
        tabsize,
        max_lines,
        placeholder,
    )
    .map(|lines| lines.join("\n"))
    .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
}

// Port of modules/rendering/hyphen_textwrap.py (CPython textwrap + hyphenate).
// Char counts (not bytes) mirror Python len(str).
fn char_len(s: &str) -> usize {
    s.chars().count()
}

fn is_ws(c: char) -> bool {
    matches!(c, '\t' | '\n' | '\x0B' | '\x0C' | '\r' | ' ')
}

fn expand_tabs(s: &str, tabsize: usize) -> String {
    if tabsize == 0 {
        return s.replace('\t', "");
    }
    let mut out = String::with_capacity(s.len());
    let mut col: usize = 0;
    for c in s.chars() {
        if c == '\t' {
            let n = tabsize - (col % tabsize);
            for _ in 0..n {
                out.push(' ');
            }
            col += n;
        } else if c == '\n' || c == '\r' {
            out.push(c);
            col = 0;
        } else {
            out.push(c);
            col += 1;
        }
    }
    out
}

fn munge_whitespace(text: &str, expand: bool, replace: bool, tabsize: usize) -> String {
    let mut s = if expand {
        expand_tabs(text, tabsize)
    } else {
        text.to_string()
    };
    if replace {
        s = s
            .chars()
            .map(|c| if is_ws(c) { ' ' } else { c })
            .collect();
    }
    s
}

fn split_simple(text: &str) -> Vec<String> {
    let mut chunks = Vec::new();
    let mut cur = String::new();
    let mut cur_ws: Option<bool> = None;
    for c in text.chars() {
        let w = is_ws(c);
        match cur_ws {
            None => {
                cur.push(c);
                cur_ws = Some(w);
            }
            Some(prev) if prev == w => cur.push(c),
            _ => {
                chunks.push(std::mem::take(&mut cur));
                cur.push(c);
                cur_ws = Some(w);
            }
        }
    }
    if !cur.is_empty() {
        chunks.push(cur);
    }
    chunks.into_iter().filter(|c| !c.is_empty()).collect()
}

fn split_hyphen_approx(text: &str) -> Vec<String> {
    // Best-effort per break_on_hyphens=True (CPython usa look-around,
    // non esprimibile con `regex` crate). I chiamanti interni usano False.
    let mut out = Vec::new();
    for chunk in split_simple(text) {
        if chunk.chars().all(is_ws) || !chunk.contains('-') {
            out.push(chunk);
            continue;
        }
        let chars: Vec<char> = chunk.chars().collect();
        let mut start = 0usize;
        let mut i = 0usize;
        while i < chars.len() {
            if chars[i] == '-' {
                let mut j = i + 1;
                while j < chars.len() && chars[j] == '-' {
                    j += 1;
                }
                let next_is_word = j < chars.len() && !is_ws(chars[j]);
                let prev_not_dash = i > start && chars[i - 1] != '-';
                if next_is_word && (prev_not_dash || j - i >= 2 && i == start) {
                    // em-dash "--" a inizio chunk resta unito; "-" singolo spezza
                    if !(j - i >= 2 && i == start) {
                        let part: String = chars[start..j].iter().collect();
                        out.push(part);
                        start = j;
                    }
                }
                i = j;
            } else {
                i += 1;
            }
        }
        if start < chars.len() {
            out.push(chars[start..].iter().collect());
        } else if start == 0 {
            out.push(chunk);
        }
    }
    out.into_iter().filter(|c: &String| !c.is_empty()).collect()
}

fn is_sentence_end(chunk: &str) -> bool {
    // sentence_end_re = [a-z][.!?]["']?\Z
    let mut cs: Vec<char> = chunk.chars().collect();
    if cs.is_empty() {
        return false;
    }
    if *cs.last().unwrap() == '"' || *cs.last().unwrap() == '\'' {
        cs.pop();
        if cs.is_empty() {
            return false;
        }
    }
    if cs.len() < 2 {
        return false;
    }
    let last = cs[cs.len() - 1];
    let prev = cs[cs.len() - 2];
    matches!(last, '.' | '!' | '?') && prev.is_ascii_lowercase()
}

fn fix_sentence_endings(chunks: &mut [String]) {
    if chunks.len() < 2 {
        return;
    }
    let mut i = 0usize;
    while i + 1 < chunks.len() {
        if chunks[i + 1] == " " && is_sentence_end(&chunks[i]) {
            chunks[i + 1] = "  ".to_string();
            i += 2;
        } else {
            i += 1;
        }
    }
}

fn take_chars(s: &str, n: usize) -> &str {
    if char_len(s) <= n {
        return s;
    }
    let idx = s
        .char_indices()
        .nth(n)
        .map(|(i, _)| i)
        .unwrap_or(s.len());
    &s[..idx]
}

fn drop_chars(s: &str, n: usize) -> &str {
    let idx = s
        .char_indices()
        .nth(n)
        .map(|(i, _)| i)
        .unwrap_or(s.len());
    &s[idx..]
}

fn rfind_char_before(s: &str, target: char, end_chars: usize) -> Option<usize> {
    // come str.rfind(target, 0, end_chars): indice in code-point
    let mut res = None;
    for (i, c) in s.chars().enumerate() {
        if i >= end_chars {
            break;
        }
        if c == target {
            res = Some(i);
        }
    }
    res
}

struct WrapCfg<'a> {
    initial_indent: &'a str,
    subsequent_indent: &'a str,
    fix_sentence_endings: bool,
    break_long_words: bool,
    drop_whitespace: bool,
    break_on_hyphens: bool,
    hyphenate_broken_words: bool,
    max_lines: Option<usize>,
    placeholder: &'a str,
}

fn handle_long_word(
    chunks: &mut Vec<String>,
    cur_line: &mut Vec<String>,
    cur_len: usize,
    width: usize,
    cfg: &WrapCfg,
) {
    let space_left = if width < 1 { 1 } else { width.saturating_sub(cur_len) };
    if cfg.break_long_words {
        let last = chunks.len() - 1;
        let chunk = chunks[last].clone();
        let chunk_len = char_len(&chunk);
        let mut end = space_left;
        if cfg.break_on_hyphens && chunk_len > space_left {
            if let Some(hyphen) = rfind_char_before(&chunk, '-', space_left) {
                if hyphen > 0 {
                    let before: String = chunk.chars().take(hyphen).collect();
                    if before.chars().any(|c| c != '-') {
                        end = hyphen + 1;
                    }
                }
            }
        }
        let head = take_chars(&chunk, end);
        if !head.is_empty() {
            cur_line.push(head.to_string());
            let last_c = head.chars().last().unwrap();
            if cfg.hyphenate_broken_words && !matches!(last_c, '-' | '.' | ',') {
                cur_line.push("-".to_string());
            }
        }
        chunks[last] = drop_chars(&chunk, end).to_string();
    } else if cur_line.is_empty() {
        let popped = chunks.pop().unwrap();
        cur_line.push(popped);
    }
}

fn wrap_chunks(mut chunks: Vec<String>, width: usize, cfg: &WrapCfg) -> Result<Vec<String>, String> {
    if width == 0 {
        return Err(format!("invalid width {:?} (must be > 0)", width));
    }
    if let Some(max_lines) = cfg.max_lines {
        let indent = if max_lines > 1 {
            cfg.subsequent_indent
        } else {
            cfg.initial_indent
        };
        if char_len(indent) + char_len(cfg.placeholder.trim_start()) > width {
            return Err("placeholder too large for max width".to_string());
        }
    }
    chunks.reverse();
    let mut lines: Vec<String> = Vec::new();
    while !chunks.is_empty() {
        let mut cur_line: Vec<String> = Vec::new();
        let mut cur_len: usize = 0;
        let indent = if lines.is_empty() {
            cfg.initial_indent
        } else {
            cfg.subsequent_indent
        };
        let line_width = width.saturating_sub(char_len(indent));
        if cfg.drop_whitespace
            && !lines.is_empty()
            && chunks.last().map(|c| c.trim().is_empty()).unwrap_or(false)
            && chunks.last().map(|c| !c.is_empty()).unwrap_or(false)
        {
            chunks.pop();
        }
        while let Some(last) = chunks.last() {
            let l = char_len(last);
            if cur_len + l <= line_width {
                let popped = chunks.pop().unwrap();
                cur_len += char_len(&popped);
                cur_line.push(popped);
            } else {
                break;
            }
        }
        if chunks
            .last()
            .map(|c| char_len(c) > line_width)
            .unwrap_or(false)
        {
            handle_long_word(&mut chunks, &mut cur_line, cur_len, line_width, cfg);
            cur_len = cur_line.iter().map(|s| char_len(s)).sum();
        }
        if cfg.drop_whitespace
            && cur_line.last().map(|c| c.trim().is_empty()).unwrap_or(false)
        {
            let dropped = cur_line.pop().unwrap();
            cur_len = cur_len.saturating_sub(char_len(&dropped));
        }
        if !cur_line.is_empty() {
            let dominated = match cfg.max_lines {
                None => true,
                Some(max) => {
                    if lines.len() + 1 < max {
                        true
                    } else if chunks.is_empty() {
                        true
                    } else if cfg.drop_whitespace
                        && chunks.len() == 1
                        && chunks[0].trim().is_empty()
                        && cur_len <= line_width
                    {
                        true
                    } else {
                        false
                    }
                }
            };
            if dominated {
                lines.push(format!("{}{}", indent, cur_line.concat()));
            } else {
                let mut placed = false;
                while let Some(last) = cur_line.last().cloned() {
                    if !last.trim().is_empty()
                        && cur_len + char_len(cfg.placeholder) <= line_width
                    {
                        cur_line.push(cfg.placeholder.to_string());
                        lines.push(format!("{}{}", indent, cur_line.concat()));
                        placed = true;
                        break;
                    }
                    cur_len = cur_len.saturating_sub(char_len(&last));
                    cur_line.pop();
                }
                if !placed {
                    if !lines.is_empty() {
                        let prev = lines.last().cloned().unwrap();
                        let rstripped = prev.trim_end().to_string();
                        if char_len(&rstripped) + char_len(cfg.placeholder) <= width {
                            *lines.last_mut().unwrap() =
                                format!("{}{}", rstripped, cfg.placeholder);
                            break;
                        }
                    }
                    lines.push(format!(
                        "{}{}",
                        indent,
                        cfg.placeholder.trim_start()
                    ));
                    break;
                } else {
                    break;
                }
            }
        }
    }
    Ok(lines)
}

fn wrap_impl(
    text: &str,
    width: usize,
    initial_indent: &str,
    subsequent_indent: &str,
    expand_tabs: bool,
    replace_whitespace: bool,
    fix_sentence_endings_flag: bool,
    break_long_words: bool,
    drop_whitespace: bool,
    break_on_hyphens: bool,
    hyphenate_broken_words: bool,
    tabsize: usize,
    max_lines: Option<usize>,
    placeholder: &str,
) -> Result<Vec<String>, String> {
    let cfg = WrapCfg {
        initial_indent,
        subsequent_indent,
        fix_sentence_endings: fix_sentence_endings_flag,
        break_long_words,
        drop_whitespace,
        break_on_hyphens,
        hyphenate_broken_words,
        max_lines,
        placeholder,
    };
    let munged = munge_whitespace(text, expand_tabs, replace_whitespace, tabsize);
    let mut chunks = if break_on_hyphens {
        split_hyphen_approx(&munged)
    } else {
        split_simple(&munged)
    };
    if cfg.fix_sentence_endings {
        fix_sentence_endings(&mut chunks);
    }
    wrap_chunks(chunks, width, &cfg)
}

#[pyfunction]
fn bbox_polygon_overlap_ratio_rs(bbox: Vec<i32>, polygon: Vec<Vec<i32>>) -> f64 {
    if bbox.len() != 4 {
        return 0.0;
    }
    let b = [bbox[0], bbox[1], bbox[2], bbox[3]];
    match to_pts_i32(&polygon) {
        Some(pts) => overlap_ratio_scanline(&b, &pts),
        None => 0.0,
    }
}

#[pyfunction]
fn filter_bboxes_by_polygon_rs(
    bboxes: Vec<Vec<i32>>,
    polygon: Vec<Vec<i32>>,
    min_overlap: f64,
) -> Vec<Vec<i32>> {
    let pts = match to_pts_i32(&polygon) {
        Some(p) => p,
        None => return bboxes,
    };
    let mut out = Vec::new();
    for b in &bboxes {
        if b.len() != 4 {
            continue;
        }
        let bb = [b[0], b[1], b[2], b[3]];
        if overlap_ratio_scanline(&bb, &pts) >= min_overlap {
            out.push(b.clone());
        }
    }
    out
}

#[pyfunction]
fn simplify_outer_border_polygon_rs(
    points: Vec<Vec<i32>>,
    tolerance_px: f64,
) -> Vec<Vec<i32>> {
    let mut pts: Vec<[f64; 2]> = points
        .iter()
        .filter(|p| p.len() == 2)
        .map(|p| [p[0] as f64, p[1] as f64])
        .collect();
    if pts.len() <= 3 {
        return points;
    }
    loop {
        if pts.len() <= 3 {
            break;
        }
        let count = pts.len();
        let mut next: Vec<[f64; 2]> = Vec::with_capacity(count);
        let mut changed = false;
        for index in 0..count {
            let prev = pts[(index + count - 1) % count];
            let curr = pts[index];
            let nxt = pts[(index + 1) % count];
            let lx = nxt[0] - prev[0];
            let ly = nxt[1] - prev[1];
            let norm = (lx * lx + ly * ly).sqrt();
            if norm == 0.0 {
                changed = true;
                continue;
            }
            let rx = curr[0] - prev[0];
            let ry = curr[1] - prev[1];
            let area_twice = lx * ry - ly * rx;
            let dist = area_twice.abs() / norm;
            if dist <= tolerance_px {
                changed = true;
                continue;
            }
            next.push(curr);
        }
        if next.len() < 3 {
            break;
        }
        pts = next;
        if !changed {
            break;
        }
    }
    pts.iter()
        .map(|p| vec![p[0].round() as i32, p[1].round() as i32])
        .collect()
}

#[pyfunction]
fn is_point_in_ellipse_rs(
    point: Vec<f64>,
    center: Vec<f64>,
    axes: Vec<f64>,
    angle: f64,
    exponent: f64,
    scale: f64,
) -> bool {
    if point.len() != 2 || center.len() != 2 || axes.len() != 2 {
        return false;
    }
    let rx = axes[0] * scale;
    let ry = axes[1] * scale;
    if rx <= 0.0 || ry <= 0.0 {
        return false;
    }
    let rad = angle.to_radians();
    let (cos_a, sin_a) = (rad.cos(), rad.sin());
    let dx = point[0] - center[0];
    let dy = point[1] - center[1];
    let x_rot = cos_a * dx + sin_a * dy;
    let y_rot = -sin_a * dx + cos_a * dy;
    let dist = (x_rot.abs() / rx).powf(exponent) + (y_rot.abs() / ry).powf(exponent);
    dist <= 1.0
}

#[pyfunction]
fn span_at_y_rs(polygon: Vec<Vec<f64>>, y_value: f64) -> Option<(f64, f64)> {
    let mut pts: Vec<[f64; 2]> = Vec::with_capacity(polygon.len());
    for p in &polygon {
        if p.len() != 2 {
            return None;
        }
        pts.push([p[0], p[1]]);
    }
    if pts.len() < 3 {
        return None;
    }
    let spans = poly_spans_at_y(&pts, y_value);
    if spans.is_empty() {
        return None;
    }
    spans
        .into_iter()
        .max_by(|a, b| {
            (a.1 - a.0)
                .partial_cmp(&(b.1 - b.0))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
}

// ---------------------------------------------------------------------------
// Detection box math (port di modules/detection.py, sottoinsieme esatto).
// Solo interi + walk su matrice distanze: nessuna dipendenza opencv.
// ---------------------------------------------------------------------------

fn iou64(a: &[i64; 4], b: &[i64; 4]) -> f64 {
    let x1 = a[0].max(b[0]);
    let y1 = a[1].max(b[1]);
    let x2 = a[2].min(b[2]);
    let y2 = a[3].min(b[3]);
    let inter = (0i64.max(x2 - x1)) as f64 * (0i64.max(y2 - y1)) as f64;
    let a_area = (a[2] - a[0]) as f64 * (a[3] - a[1]) as f64;
    let b_area = (b[2] - b[0]) as f64 * (b[3] - b[1]) as f64;
    let union = a_area + b_area - inter;
    if union != 0.0 {
        inter / union
    } else {
        0.0
    }
}

fn rect_fit64(big: &[i64; 4], small: &[i64; 4]) -> bool {
    let (l1, t1, r1, b1) = (
        big[0].min(big[2]),
        big[1].min(big[3]),
        big[0].max(big[2]),
        big[1].max(big[3]),
    );
    let (l2, t2, r2, b2) = (
        small[0].min(small[2]),
        small[1].min(small[3]),
        small[0].max(small[2]),
        small[1].max(small[3]),
    );
    l1 <= l2 && r1 >= r2 && t1 <= t2 && b1 >= b2
}

fn merge_two64(a: &[i64; 4], b: &[i64; 4]) -> [i64; 4] {
    [a[0].min(b[0]), a[1].min(b[1]), a[2].max(b[2]), a[3].max(b[3])]
}

fn compat_idx(a: Option<usize>, b: Option<usize>) -> bool {
    a.is_none() || b.is_none() || a == b
}

fn to_box64(v: &[i64]) -> Option<[i64; 4]> {
    if v.len() != 4 {
        return None;
    }
    Some([v[0], v[1], v[2], v[3]])
}

#[pyfunction]
fn calculate_iou_rs(rect1: Vec<i64>, rect2: Vec<i64>) -> f64 {
    match (to_box64(&rect1), to_box64(&rect2)) {
        (Some(a), Some(b)) => iou64(&a, &b),
        _ => 0.0,
    }
}

#[pyfunction]
fn do_rectangles_overlap_rs(rect1: Vec<i64>, rect2: Vec<i64>, iou_threshold: f64) -> bool {
    match (to_box64(&rect1), to_box64(&rect2)) {
        (Some(a), Some(b)) => iou64(&a, &b) >= iou_threshold,
        _ => false,
    }
}

#[pyfunction]
fn does_rectangle_fit_rs(bigger_rect: Vec<i64>, smaller_rect: Vec<i64>) -> bool {
    match (to_box64(&bigger_rect), to_box64(&smaller_rect)) {
        (Some(a), Some(b)) => rect_fit64(&a, &b),
        _ => false,
    }
}

#[pyfunction]
fn is_mostly_contained_rs(outer_box: Vec<i64>, inner_box: Vec<i64>, threshold: f64) -> bool {
    let (o, i) = match (to_box64(&outer_box), to_box64(&inner_box)) {
        (Some(o), Some(i)) => (o, i),
        _ => return false,
    };
    let inner_area = (i[2] - i[0]) as f64 * (i[3] - i[1]) as f64;
    let outer_area = (o[2] - o[0]) as f64 * (o[3] - o[1]) as f64;
    if outer_area < inner_area || inner_area == 0.0 {
        return false;
    }
    let inter = (0i64.max(i[2].min(o[2]) - i[0].max(o[0]))) as f64
        * (0i64.max(i[3].min(o[3]) - i[1].max(o[1]))) as f64;
    inter / inner_area >= threshold
}

#[pyfunction]
fn match_bubble_index_rs(txt_box: Vec<i64>, bubble_boxes: Vec<Vec<i64>>) -> Option<usize> {
    let t = to_box64(&txt_box)?;
    if bubble_boxes.is_empty() {
        return None;
    }
    let mut best_fit: Option<usize> = None;
    let mut best_area: Option<i64> = None;
    for (idx, b) in bubble_boxes.iter().enumerate() {
        let bb = to_box64(b)?;
        if rect_fit64(&bb, &t) {
            let area = (bb[2] - bb[0]) * (bb[3] - bb[1]);
            if best_area.is_none_or(|a| area < a) {
                best_fit = Some(idx);
                best_area = Some(area);
            }
        }
    }
    if best_fit.is_some() {
        return best_fit;
    }
    let mut best_overlap: Option<usize> = None;
    let mut best_iou = 0.2f64;
    for (idx, b) in bubble_boxes.iter().enumerate() {
        let bb = to_box64(b)?;
        let v = iou64(&bb, &t);
        if v >= 0.2 && v > best_iou {
            best_overlap = Some(idx);
            best_iou = v;
        }
    }
    best_overlap
}

#[pyfunction]
fn merge_bounding_boxes_rs(
    seg_boxes: Vec<Vec<i64>>,
    seg_idx: Vec<Option<usize>>,
    detect_boxes: Vec<Vec<i64>>,
    detect_idx: Vec<Option<usize>>,
) -> Vec<(Vec<i64>, Option<usize>)> {
    let seg: Vec<[i64; 4]> = seg_boxes.iter().filter_map(|b| to_box64(b)).collect();
    let det: Vec<[i64; 4]> = detect_boxes.iter().filter_map(|b| to_box64(b)).collect();
    let get = |v: &[Option<usize>], i: usize| {
        if i < v.len() {
            v[i]
        } else {
            None
        }
    };
    // Step 1: ogni seg assorbe i detect compatibili.
    let mut merged: Vec<([i64; 4], Option<usize>)> = Vec::with_capacity(seg.len());
    for (spos, sbox) in seg.iter().enumerate() {
        let mut running = *sbox;
        let mut ridx = get(&seg_idx, spos);
        for (dpos, dbox) in det.iter().enumerate() {
            let didx = get(&detect_idx, dpos);
            if !compat_idx(ridx, didx) {
                continue;
            }
            if rect_fit64(&running, dbox) {
                if ridx.is_none() {
                    ridx = didx;
                }
                continue;
            }
            if iou64(&running, dbox) >= 0.02 {
                running = merge_two64(&running, dbox);
                if ridx.is_none() {
                    ridx = didx;
                }
            }
        }
        merged.push((running, ridx));
    }
    // Step 2: detect mai fusi.
    for (dpos, dbox) in det.iter().enumerate() {
        let didx = get(&detect_idx, dpos);
        let mut add = true;
        for (mbox, midx) in &merged {
            if !compat_idx(didx, *midx) {
                continue;
            }
            if iou64(dbox, mbox) >= 0.1 || rect_fit64(mbox, dbox) {
                add = false;
                break;
            }
        }
        if add {
            merged.push((*dbox, didx));
        }
    }
    // Step 3: seconda passata O(N^2).
    let mut final_pairs: Vec<([i64; 4], Option<usize>)> = Vec::with_capacity(merged.len());
    for (i, (b, bi)) in merged.iter().enumerate() {
        let mut running = *b;
        let mut ridx = *bi;
        for (j, (o, oi)) in merged.iter().enumerate() {
            if i == j {
                continue;
            }
            if !compat_idx(ridx, *oi) {
                continue;
            }
            if iou64(&running, o) >= 0.1 && !rect_fit64(&running, o) {
                running = merge_two64(&running, o);
                if ridx.is_none() {
                    ridx = *oi;
                }
            }
        }
        final_pairs.push((running, ridx));
    }
    // Dedup: uguali o overlap >= 0.6.
    let mut unique: Vec<([i64; 4], Option<usize>)> = Vec::new();
    let mut seen: Vec<[i64; 4]> = Vec::new();
    for (b, bi) in final_pairs {
        let mut dup = false;
        for s in &seen {
            if *s == b || iou64(&b, s) >= 0.6 {
                dup = true;
                break;
            }
        }
        if !dup {
            unique.push((b, bi));
            seen.push(b);
        }
    }
    unique
        .into_iter()
        .map(|(b, bi)| (vec![b[0], b[1], b[2], b[3]], bi))
        .collect()
}

/// Round-half-even come Python round(): i .5 esatti vanno al pari.
fn py_round_half_even(x: f64) -> i64 {
    let f = x.floor();
    let d = x - f;
    if d < 0.5 {
        f as i64
    } else if d > 0.5 {
        (f + 1.0) as i64
    } else if (f as i64) % 2 == 0 {
        f as i64
    } else {
        (f + 1.0) as i64
    }
}

#[pyfunction]
fn edge_support_ratio_rs(dist: Vec<f32>, width: usize, height: usize, poly: Vec<Vec<f32>>) -> f64 {
    let mut pts: Vec<[f64; 2]> = Vec::with_capacity(poly.len());
    for p in &poly {
        if p.len() != 2 {
            return 0.0;
        }
        pts.push([p[0] as f64, p[1] as f64]);
    }
    if pts.len() < 3 || dist.len() != width * height {
        return 0.0;
    }
    let (w, h) = (width as i64, height as i64);
    let mut ok: i64 = 0;
    let mut tot: i64 = 0;
    let n = pts.len();
    for i in 0..n {
        let (p0, p1) = (pts[i], pts[(i + 1) % n]);
        let steps = (p1[0] - p0[0]).abs().max((p1[1] - p0[1]).abs()) as i64 + 1;
        let steps_f = steps as f64;
        for k in 0..steps {
            let kf = k as f64;
            let x = py_round_half_even(p0[0] + (p1[0] - p0[0]) * kf / steps_f);
            let y = py_round_half_even(p0[1] + (p1[1] - p0[1]) * kf / steps_f);
            if x >= 0 && x < w && y >= 0 && y < h {
                tot += 1;
                if dist[(y as usize) * width + (x as usize)] <= 3.0 {
                    ok += 1;
                }
            }
        }
    }
    ok as f64 / (tot.max(1) as f64)
}
