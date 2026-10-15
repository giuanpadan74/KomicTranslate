"""Parita RS vs Python per il payload di traduzione (non-regression)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.gemini_translation_payload import (
    parse_translation_payload as py_path,  # noqa: F401  (ora con fast-path RS)
)
import modules.utils.translator_utils as tu
import komic_core_rs
import pytest

HAS_RS = True

CASES = [
    ('{"block_1": "OH, HAI RAGIONE,", "block_2": "VA BENE."}', 2),
    ('[{"id": "block_1", "it": "CIAO"}, {"id": "block_2", "it": "MONDO"}]', 2),
    ('{"block_1": "CIAO", block_11: "OH, HAI RAGIONE,", "block_15": "andiamo"}', 0),
    ('{"block_1": "UNO", "block_3": "TRE"}', 3),
    ('```json {"block_0": "A", "block_1": "B"} ```', 2),
    ('{"block_0": "Troncato senza chiusura...', 1),
    ('{"translation": {"block_0": "NESTED"}}', 1),
]


def _py_no_rs(raw, exp):
    """Esegue il percorso Python puro bypassando il bridge (env)."""
    import os
    os.environ["KOMICTRANSLATE_NO_RS"] = "1"
    try:
        # ricarica logica: chiama direttamente i passaggi Python senza bridge
        text = (raw or "").strip()
        if not text:
            return {}, {"is_valid": False, "source": "empty"}
        from modules.gemini_translation_payload import (
            _try_json_load, normalize_translation_payload,
            _validation_report, _quote_bare_block_keys,
            _recover_blocks_with_regex,
        )
        candidates = [text]
        extracted = tu._extract_json_object(text)
        if extracted and extracted not in candidates:
            candidates.append(extracted)
        for cand in candidates:
            parsed = _try_json_load(cand)
            if parsed is None:
                continue
            norm = normalize_translation_payload(parsed)
            if norm:
                return norm, _validation_report(norm, exp, "json")
        quoted = _quote_bare_block_keys(text)
        if quoted != text:
            for cand in (quoted, tu._extract_json_object(quoted) or ""):
                if not cand:
                    continue
                parsed = _try_json_load(cand)
                if parsed is None:
                    continue
                norm = normalize_translation_payload(parsed)
                if norm:
                    return norm, _validation_report(norm, exp, "repair")
        rep = tu._repair_truncated_json(text) or {}
        if rep:
            return rep, _validation_report(rep, exp, "repair")
        rx = _recover_blocks_with_regex(text)
        if rx:
            return rx, _validation_report(rx, exp, "regex")
        return {}, {"is_valid": False, "source": "unrecoverable"}
    finally:
        os.environ.pop("KOMICTRANSLATE_NO_RS", None)


@pytest.mark.skipif(not HAS_RS, reason="komic_core_rs non installato")
def test_rs_matches_python_on_core_cases():
    for raw, exp in CASES:
        py_p, py_r = _py_no_rs(raw, exp)
        rs_p, rs_r = komic_core_rs.parse_translation_payload_rs(raw, exp)
        assert dict(rs_p) == dict(py_p)
        assert rs_r["is_valid"] == py_r["is_valid"]
        assert rs_r["source"] == py_r["source"]
        assert list(rs_r["missing_blocks"]) == list(py_r.get("missing_blocks", []))
