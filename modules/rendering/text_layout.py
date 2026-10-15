from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor, QTextDocument, QTextOption

from .hyphen_textwrap import wrap as hyphen_wrap
from .polygon_text_layout import build_polygon_text_layout
from ..utils.textblock import TextBlock
def pyside_word_wrap(text: str, font_input: str, roi_width: int, roi_height: int,
                     line_spacing, outline_width, bold, italic, underline,
                     alignment, direction, init_font_size: int,
                     min_font_size: int = 10) -> Tuple[str, int]:
    """Adatta il testo al rettangolo riducendo il font e inserendo ritorni a capo."""
    def prepare_font(font_size):
        font = QFont(font_input, font_size)
        font.setBold(bold)
        font.setItalic(italic)
        font.setUnderline(underline)
        return font
    def eval_metrics(txt: str, font_sz: float) -> Tuple[float, float]:
        doc = QTextDocument()
        doc.setDefaultFont(prepare_font(font_sz))
        doc.setPlainText(txt)
        text_option = QTextOption()
        text_option.setTextDirection(direction)
        doc.setDefaultTextOption(text_option)
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(
            line_spacing * 100,
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
        block_format.setAlignment(alignment)
        cursor.mergeBlockFormat(block_format)

        size = doc.size()
        width, height = size.width(), size.height()
        if outline_width > 0:
            width += 2 * outline_width
            height += 2 * outline_width
        return width, height
    mutable_message = text
    font_size = init_font_size
    while font_size > min_font_size:
        width, height = eval_metrics(mutable_message, font_size)
        if height > roi_height:
            font_size -= 1
            mutable_message = text
        elif width > roi_width:
            columns = len(mutable_message)
            while columns > 0:
                columns -= 1
                if columns == 0:
                    break
                mutable_message = "\n".join(
                    hyphen_wrap(
                        text,
                        columns,
                        break_on_hyphens=False,
                        break_long_words=False,
                        hyphenate_broken_words=True,
                    )
                )
                wrapped_width, _ = eval_metrics(mutable_message, font_size)
                if wrapped_width <= roi_width:
                    break
            if columns < 1:
                font_size -= 1
                mutable_message = text
        else:
            break
    if font_size <= min_font_size:
        font_size = min_font_size
        mutable_message = text
        min_cost = 1e9
        min_text = text
        for columns in range(1, len(text)):
            wrapped_text = "\n".join(
                hyphen_wrap(
                    text,
                    columns,
                    break_on_hyphens=False,
                    break_long_words=False,
                    hyphenate_broken_words=True,
                )
            )
            wrapped_width, wrapped_height = eval_metrics(wrapped_text, font_size)
            cost = (wrapped_width - roi_width) ** 2 + (wrapped_height - roi_height) ** 2
            if cost < min_cost:
                min_cost = cost
                min_text = wrapped_text
        mutable_message = min_text
    # Calcola le dimensioni effettive del testo renderizzato
    render_w, render_h = eval_metrics(mutable_message, font_size)
    render_w = min(render_w, roi_width)
    render_h = min(render_h, roi_height)
    return mutable_message, font_size, render_w, render_h

def build_text_layout(blk: TextBlock, text: str, font_family: str, line_spacing,
                      outline_width, bold, italic, underline, alignment,
                      direction, init_font_size: int, min_font_size: int = 10,
                      use_polygon_layout: bool = False):
    if blk is None:
        return None
    polygon_points = getattr(blk, "polygon_points", None)
    if use_polygon_layout and polygon_points is not None:
        layout = build_polygon_text_layout(
            text=text,
            polygon_points=polygon_points,
            font_family=font_family,
            line_spacing=line_spacing,
            outline_width=outline_width,
            bold=bold,
            italic=italic,
            underline=underline,
            alignment=alignment,
            direction=direction,
            init_font_size=init_font_size,
            min_font_size=min_font_size,
        )
        if layout is not None:
            return layout
    x1, y1, width, height = blk.xywh
    wrapped_text, font_size, render_w, render_h = pyside_word_wrap(
        text=text or "",
        font_input=font_family,
        roi_width=width,
        roi_height=height,
        line_spacing=line_spacing,
        outline_width=outline_width,
        bold=bold,
        italic=italic,
        underline=underline,
        alignment=alignment,
        direction=direction,
        init_font_size=init_font_size,
        min_font_size=min_font_size,
    )
    center_x = x1 + width / 2
    center_y = y1 + height / 2
    pos_x = center_x - render_w / 2
    pos_y = center_y - render_h / 2
    return {
        "text": wrapped_text,
        "plain_text": wrapped_text,
        "font_size": int(font_size),
        "position": (float(pos_x), float(pos_y)),
        "width": float(width),
        "polygon_layout": False,
    }
def manual_wrap(main_page, blk_list: List[TextBlock], font_family: str,
                line_spacing, outline_width, bold, italic, underline,
                alignment, direction, init_font_size: int = 40,
                min_font_size: int = 10):
    for blk in blk_list:
        _, _, width, height = blk.xywh
        translation = blk.translation or ""
        if len(translation) > 1:
            translation, font_size, _, _ = pyside_word_wrap(
                translation,
                font_family,
                width,
                height,
                line_spacing,
                outline_width,
                bold,
                italic,
                underline,
                alignment,
                direction,
                init_font_size,
                min_font_size,
            )
        else:
            font_size = init_font_size
        main_page.blk_rendered.emit(translation, font_size, blk)
