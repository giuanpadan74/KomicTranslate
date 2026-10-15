from typing import Any, Mapping


def outline_enabled_from_data(item_data: Mapping[str, Any]) -> bool:
    """Restituisce lo stato outline persistente con fallback compatibile."""
    if "outline" in item_data:
        return bool(item_data.get("outline"))

    outline_color = item_data.get("outline_color")
    if outline_color in (None, "", False):
        return False

    try:
        return float(item_data.get("outline_width") or 0) > 0
    except (TypeError, ValueError):
        return bool(outline_color)


def outline_color_for_loading(
    item_data: Mapping[str, Any],
    default_color: Any,
) -> Any:
    """Restituisce il colore outline solo quando il contorno e' attivo."""
    if not outline_enabled_from_data(item_data):
        return None
    return item_data.get("outline_color", default_color)
