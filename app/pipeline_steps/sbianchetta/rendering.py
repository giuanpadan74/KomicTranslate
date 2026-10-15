"""
Generazione text_items_state (spazi vuoti) per il processo di sbianchetta.
"""
from PySide6.QtGui import QColor

from modules.rendering.render import get_best_render_area, pyside_word_wrap
from modules.utils.translator_utils import format_translations

from app.ui.canvas.text_item import OutlineInfo, OutlineType


def render_text_items(blk_list, image, inpaint_input_img,
                      main_page, trg_lng_cd) -> list:
    """Genera text_items_state vuoti (spazi) per ogni blocco."""
    render_settings = main_page.render_settings()
    font = render_settings.font_family
    font_color = QColor(render_settings.color)
    outline_color = QColor(render_settings.outline_color)
    outline = render_settings.outline
    max_font_size = render_settings.max_font_size
    min_font_size = render_settings.min_font_size
    line_spacing = float(render_settings.line_spacing)
    outline_width = float(render_settings.outline_width)
    bold = render_settings.bold
    italic = render_settings.italic
    underline = render_settings.underline
    alignment_id = render_settings.alignment_id
    alignment = main_page.button_to_alignment[alignment_id]
    direction = render_settings.direction
    upper_case = render_settings.upper_case

    format_translations(blk_list, trg_lng_cd, upper_case=upper_case)
    get_best_render_area(blk_list, image, inpaint_input_img)

    text_items_state = []
    for blk in blk_list:
        x1, y1, width, height = blk.xywh
        translation = blk.translation
        if not translation:
            continue

        translation, font_size, render_w, render_h = pyside_word_wrap(
            translation, font, width, height, line_spacing, outline_width,
            bold, italic, underline, alignment, direction,
            max_font_size, min_font_size,
        )

        center_x = x1 + width / 2
        center_y = y1 + height / 2
        pos_x = center_x - render_w / 2
        pos_y = center_y - render_h / 2

        text_items_state.append({
            "text": translation,
            "font_family": font,
            "font_size": font_size,
            "text_color": font_color,
            "alignment": alignment,
            "line_spacing": line_spacing,
            "outline_color": outline_color,
            "outline_width": outline_width,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "position": (pos_x, pos_y),
            "rotation": blk.angle,
            "scale": 1.0,
            "transform_origin": blk.tr_origin_point,
            "width": width,
            "direction": direction,
            "selection_outlines": [
                OutlineInfo(0, len(translation), outline_color,
                            outline_width, OutlineType.Full_Document)
            ] if outline else [],
        })
    return text_items_state