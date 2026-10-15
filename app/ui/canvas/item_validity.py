from shiboken6 import isValid


def is_live_graphics_item(item, scene=None):
    """Ritorna True solo per item Qt ancora validi e opzionalmente nella scena."""
    try:
        if not item or not isValid(item):
            return False
        item_scene = item.scene()
    except RuntimeError:
        return False

    if item_scene is None:
        return False
    if scene is not None and item_scene is not scene:
        return False
    return True


def prune_graphics_items(items, scene=None):
    """Filtra gli item non piu validi restituendo lista valida e numero rimossi."""
    valid_items = []
    removed = 0
    for item in list(items or []):
        if is_live_graphics_item(item, scene=scene):
            valid_items.append(item)
        else:
            removed += 1
    return valid_items, removed
