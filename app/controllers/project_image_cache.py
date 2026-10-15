import logging
import os
from typing import Any, Callable, Mapping


logger = logging.getLogger(__name__)


def normalize_image_cache_key(file_path: str) -> str:
    """Normalizza i path immagine per confronti robusti tra slash/UNC."""
    normalized = str(file_path or "").strip()
    if not normalized:
        return ""
    normalized = normalized.replace("/", "\\")
    return os.path.normcase(os.path.normpath(normalized))


def find_matching_cache_key(mapping: Mapping[str, Any], file_path: str) -> str | None:
    """Trova una chiave equivalente nel cache immagini anche se il path varia."""
    if file_path in mapping:
        return file_path

    target_key = normalize_image_cache_key(file_path)
    if not target_key:
        return None

    for existing_key in mapping.keys():
        if normalize_image_cache_key(existing_key) == target_key:
            return existing_key
    return None


def resolve_cached_image(
    file_path: str,
    image_data: Mapping[str, Any],
    image_loader: Callable[[str], Any],
    cache_setter: Callable[[str, Any], None] | None = None,
) -> tuple[Any, str | None, str]:
    """
    Recupera un'immagine dal cache o la ricarica da disco/history.

    Returns:
        (image, matched_key, source) dove source e' uno tra:
        - cache_direct
        - cache_alias
        - loader
        - missing
    """
    matched_key = find_matching_cache_key(image_data, file_path)
    if matched_key is not None:
        image = image_data[matched_key]
        if matched_key != file_path and cache_setter is not None:
            cache_setter(file_path, image)
            logger.info(
                "[IMAGE_CACHE] Alias creato per path equivalente: %s -> %s",
                file_path,
                matched_key,
            )
            return image, matched_key, "cache_alias"
        return image, matched_key, "cache_direct"

    image = image_loader(file_path)
    if image is not None and cache_setter is not None:
        cache_setter(file_path, image)
        logger.info("[IMAGE_CACHE] Immagine ricaricata fuori cache: %s", file_path)
        return image, file_path, "loader"

    logger.warning("[IMAGE_CACHE] Immagine non trovata nel cache ne' ricaricabile: %s", file_path)
    return None, None, "missing"
