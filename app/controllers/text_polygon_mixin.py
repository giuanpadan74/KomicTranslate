import numpy as np

from modules.rendering.render import build_text_layout
from modules.utils.polygon_region import polygon_to_bbox
from modules.detection import extract_bubble_polygon


def _is_polygon_mode(blk):
    return bool(
        blk is not None
        and getattr(blk, "use_polygon_layout", False)
        and getattr(blk, "polygon_points", None) is not None
    )


def _build_simple_rectangle_points(xyxy):
    if xyxy is None or len(xyxy) != 4:
        return None
    x1, y1, x2, y2 = [int(v) for v in xyxy]
    points = np.array(
        [
            [x1, y1],
            [x2, y1],
            [x2, y2],
            [x1, y2],
        ],
        dtype=np.int32,
    )
    return points


def _cache_rect_layout(blk, text_item):
    if blk is None or text_item is None or hasattr(blk, "_rect_layout_cache"):
        return
    blk._rect_layout_cache = {
        "text": text_item.toHtml(),
        "width": float(max(1.0, text_item.boundingRect().width())),
        "position": (float(text_item.pos().x()), float(text_item.pos().y())),
        "font_size": int(getattr(text_item, "font_size", 12)),
    }


def _apply_layout_to_text_item(text_item, layout):
    if text_item is None or layout is None:
        return False
    text_item.font_size = int(layout["font_size"])
    text_item.set_text(layout["text"], layout["width"])
    pos_x, pos_y = layout["position"]
    text_item.setPos(pos_x, pos_y)
    text_item.update()
    return True


def _build_layout_for_text_item(text_item, blk, use_polygon_layout):
    plain_text = text_item.toPlainText()
    return build_text_layout(
        blk=blk,
        text=plain_text,
        font_family=text_item.font_family,
        line_spacing=text_item.line_spacing,
        outline_width=text_item.outline_width,
        bold=text_item.bold,
        italic=text_item.italic,
        underline=text_item.underline,
        alignment=text_item.alignment,
        direction=text_item.direction,
        init_font_size=max(4, int(text_item.font_size)),
        min_font_size=4,
        use_polygon_layout=use_polygon_layout,
    )


class TextPolygonMixin:
    def refresh_polygon_text_button_state(self):
        button = getattr(self, "polygon_text_button", None)
        if button is None:
            return
        text_item = getattr(self, "curr_tblock_item", None)
        blk = getattr(self, "curr_tblock", None)
        visible = bool(
            text_item is not None
            and hasattr(self, "image_viewer")
            and text_item in self.image_viewer._scene.items()
        )
        button.blockSignals(True)
        button.setVisible(visible)
        button.setEnabled(visible and blk is not None)
        button.setChecked(_is_polygon_mode(blk))
        button.blockSignals(False)

    def toggle_selected_text_polygon_mode(self, checked):
        text_item = getattr(self, "curr_tblock_item", None)
        blk = getattr(self, "curr_tblock", None)
        if text_item is None or blk is None:
            self.refresh_polygon_text_button_state()
            return

        if checked:
            _cache_rect_layout(blk, text_item)
            if getattr(blk, "polygon_points", None) is None:
                xyxy = getattr(blk, "xyxy", None)
                polygon_points = None
                if xyxy is not None and hasattr(self, "image_viewer"):
                    image = self.image_viewer.get_cv2_image()
                    polygon_points = extract_bubble_polygon(image, xyxy)
                if polygon_points is None:
                    polygon_points = _build_simple_rectangle_points(xyxy)
                if polygon_points is None:
                    self.refresh_polygon_text_button_state()
                    return
                blk.polygon_points = polygon_points
                blk.segm_pts = polygon_points
            bbox = polygon_to_bbox(blk.polygon_points)
            if bbox is not None:
                blk.bubble_xyxy = bbox
            layout = _build_layout_for_text_item(text_item, blk, use_polygon_layout=True)
            if layout is None:
                self.refresh_polygon_text_button_state()
                return
            blk.use_polygon_layout = True
            _apply_layout_to_text_item(text_item, layout)
        else:
            blk.use_polygon_layout = False
            cached_layout = getattr(blk, "_rect_layout_cache", None)
            if cached_layout is None:
                cached_layout = _build_layout_for_text_item(
                    text_item, blk, use_polygon_layout=False
                )
            if cached_layout is None:
                self.refresh_polygon_text_button_state()
                return
            _apply_layout_to_text_item(text_item, cached_layout)

        self._refresh_polygon_overlay_for_block(blk)
        if hasattr(self, "_schedule_save_current_image_state"):
            self._schedule_save_current_image_state(100)
        self.refresh_polygon_text_button_state()

    def _refresh_polygon_overlay_for_block(self, blk):
        if blk is None or not hasattr(self, "image_viewer"):
            return
        for rect_item in getattr(self.image_viewer, "rectangles", []):
            if getattr(rect_item, "text_block", None) is not blk:
                continue
            if _is_polygon_mode(blk):
                self._attach_polygon_overlay(rect_item)
                overlay = getattr(rect_item, "polygon_overlay", None)
                if overlay is not None:
                    overlay.refresh_from_block()
                    if not getattr(self.image_viewer, 'polygons_visible', True):
                        overlay.setVisible(False)
                    overlay.set_selected(True)
            else:
                overlay = getattr(rect_item, "polygon_overlay", None)
                if overlay is not None:
                    overlay.set_selected(False)
            break
