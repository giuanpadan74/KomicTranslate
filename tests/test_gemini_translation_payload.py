"""Test per il parser robusto dei payload Gemini."""
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.gemini_translation_payload import parse_translation_payload


def test_parse_valid_keyed_json():
    raw = """
    {
      "block_1": "OH, HAI RAGIONE,",
      "block_2": "VA BENE."
    }
    """

    payload, report = parse_translation_payload(raw, expected_count=2)

    assert report["is_valid"] is True
    assert payload == {
        "block_1": "OH, HAI RAGIONE,",
        "block_2": "VA BENE.",
    }


def test_parse_array_payload_normalizes_to_keyed_dict():
    raw = """
    [
      {"id": "block_1", "fr": "OH, YOU'RE RIGHT,", "it": "OH, HAI RAGIONE,"},
      {"id": "block_2", "fr": "OK.", "it": "VA BENE."}
    ]
    """

    payload, report = parse_translation_payload(raw, expected_count=2)

    assert report["is_valid"] is True
    assert payload["block_1"] == "OH, HAI RAGIONE,"
    assert payload["block_2"] == "VA BENE."


def test_parse_repairs_malformed_block_key_syntax():
    raw = """
    {
      "block_1": "CIAO",
      block_11: "OH, HAI RAGIONE,",
      "block_15": "andiamo"
    }
    """

    payload, report = parse_translation_payload(raw, expected_count=0)

    assert payload["block_1"] == "CIAO"
    assert payload["block_11"] == "OH, HAI RAGIONE,"
    assert payload["block_15"] == "andiamo"
    assert report["source"] in {"regex", "repair", "json"}


def test_parse_reports_missing_blocks_without_returning_empty_result():
    raw = """
    {
      "block_1": "UNO",
      "block_3": "TRE"
    }
    """

    payload, report = parse_translation_payload(raw, expected_count=3)

    assert payload["block_1"] == "UNO"
    assert payload["block_3"] == "TRE"
    assert report["is_valid"] is False
    assert "block_2" in report["missing_blocks"]
