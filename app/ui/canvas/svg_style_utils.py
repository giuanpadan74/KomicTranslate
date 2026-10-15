def svg_content_uses_complex_styling(svg_content):
    """Rileva costrutti SVG che il rendering nativo semplificato non gestisce bene."""
    if not svg_content:
        return False

    lowered = svg_content.lower()
    markers = ("<style", "style=", "opacity=", "filter=", "class=")
    return any(marker in lowered for marker in markers)


def svg_root_has_single_native_shape(svg_root):
    """Rileva se l'SVG contiene una sola forma semplice senza altri nodi renderizzabili."""
    if svg_root is None:
        return False, None

    root_tag = svg_root.tag.split("}")[-1] if "}" in svg_root.tag else svg_root.tag
    if root_tag != "svg":
        return False, None

    ignored_tags = {"defs", "title", "desc", "metadata"}
    native_tags = {"rect", "circle", "ellipse"}
    renderable_children = []

    for child in svg_root:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag in ignored_tags:
            continue
        renderable_children.append((tag, child))

    if len(renderable_children) != 1:
        return False, None

    tag, element = renderable_children[0]
    if tag not in native_tags:
        return False, None

    return True, (tag, element)
