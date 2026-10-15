from __future__ import annotations

from typing import Any, Optional


def _is_nonempty_text(value: Any) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


def pick_block_for_text_edits(blk_list: list, curr_tblock: Any | None) -> Any | None:
    if not blk_list:
        return None

    if curr_tblock is not None and curr_tblock in blk_list:
        return curr_tblock

    for blk in blk_list:
        if blk is None:
            continue
        translation = getattr(blk, "translation", None)
        if _is_nonempty_text(translation):
            return blk

    return blk_list[0]


def refresh_text_edits_for_current_block(main: Any) -> None:
    s_edit = getattr(main, "s_text_edit", None)
    t_edit = getattr(main, "t_text_edit", None)
    if s_edit is None or t_edit is None:
        return

    blk_list = getattr(main, "blk_list", None) or []
    curr_tblock = getattr(main, "curr_tblock", None)
    target_blk = pick_block_for_text_edits(blk_list, curr_tblock)

    if target_blk is None:
        for edit in (s_edit, t_edit):
            try:
                edit.blockSignals(True)
                edit.clear()
            finally:
                edit.blockSignals(False)
        setattr(main, "curr_tblock", None)
        setattr(main, "curr_tblock_item", None)
        try:
            if hasattr(main, "refresh_polygon_text_button_state"):
                main.refresh_polygon_text_button_state()
            if hasattr(main, "refresh_polygon_inpaint_button_state"):
                main.refresh_polygon_inpaint_button_state()
        except Exception:
            pass
        return

    s_text = getattr(target_blk, "text", "") or ""
    t_text = getattr(target_blk, "translation", "") or ""

    s_edit.blockSignals(True)
    t_edit.blockSignals(True)
    s_edit.setPlainText(s_text)
    t_edit.setPlainText(t_text)
    s_edit.blockSignals(False)
    t_edit.blockSignals(False)

    setattr(main, "curr_tblock", target_blk)

    try:
        if hasattr(main, "refresh_polygon_text_button_state"):
            main.refresh_polygon_text_button_state()
        if hasattr(main, "refresh_polygon_inpaint_button_state"):
            main.refresh_polygon_inpaint_button_state()
    except Exception:
        pass
