"""Test per il resolver del cache immagini progetto."""
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.controllers.project_image_cache import (
    find_matching_cache_key,
    normalize_image_cache_key,
    resolve_cached_image,
)


def test_normalize_image_cache_key_unc_and_slashes():
    raw = "//kif/usbshare1/folder/image.jpg"
    normalized = normalize_image_cache_key(raw)

    assert normalized.endswith("\\kif\\usbshare1\\folder\\image.jpg")


def test_find_matching_cache_key_matches_unc_variants():
    cache = {
        r"\\kif\usbshare1\folder\image.jpg": object(),
    }

    matched = find_matching_cache_key(cache, "//kif/usbshare1/folder/image.jpg")

    assert matched == r"\\kif\usbshare1\folder\image.jpg"


def test_resolve_cached_image_reload_fills_missing_entry():
    image = object()
    cache = {}

    resolved, matched_key, source = resolve_cached_image(
        "//kif/usbshare1/folder/image.jpg",
        cache,
        image_loader=lambda _: image,
        cache_setter=lambda key, value: cache.__setitem__(key, value),
    )

    assert resolved is image
    assert matched_key == "//kif/usbshare1/folder/image.jpg"
    assert source == "loader"
    assert cache["//kif/usbshare1/folder/image.jpg"] is image
