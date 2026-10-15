from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsItem
from PySide6.QtGui import QFont, QColor, QPen, QBrush, QFontMetrics
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF
from .z_layers import MARKER_LAYER_DEFAULT


class TextBoxMarker(QGraphicsEllipseItem):
    """Temporary numbered marker for text boxes.

    The marker is anchored EXTERNALLY to the top-left corner of the parent
    (text box / rectangle): the center of the red circle is placed on the
    top-left corner, so most of the badge extends OUTSIDE the box and the
    text inside the box remains fully readable.

    Marker dimensions are derived from the **pixel size of the loaded page**
    (see ``SIZE_RATIO``), NOT from the translation font size. This avoids
    the "growing marker" bug that occurred when ``TextBlockItem`` repeatedly
    auto-scaled the text to fit the box: each resize used to call
    ``marker.set_font_size(new_font_size)`` and the marker diameter would
    inflate on every iteration.

    The marker is added to the **scene** (not parented to the text_item /
    rect_item) so its size is completely independent of the parent item's
    scale / rotation. The view's zoom is still respected because the
    marker is a regular top-level scene item. ``ItemPositionHasChanged``
    on the tracked text_item updates the marker's scene position via
    ``update_position_relative_to_item``.
    """

    # Diameter of the circle = a fixed fraction of the page's smaller
    # dimension (in pixels). This makes the badge size predictable and
    # proportional to the loaded image, and independent of font size.
    SIZE_RATIO = 0.035  # ~3.5% of the shorter page side

    # Default diameter used when no page size is supplied (e.g. very early
    # during initialization). Kept small on purpose as a safe fallback.
    DEFAULT_DIAMETER = 30.0

    def __init__(self, number, page_size=None, parent=None):
        """Create a marker.

        Parameters
        ----------
        number : int
            Number displayed inside the badge.
        page_size : QSizeF or tuple, optional
            Pixel size of the loaded page. The marker's diameter is
            computed from this value and never changes afterwards (until
            ``set_page_size`` is called again).
        parent : QGraphicsItem, optional
            Tracked item (typically the text_item or rect_item the marker
            is anchored to). The marker is NOT parented to it (stays as
            a top-level scene item) but uses it to sync position.
        """
        super().__init__(None)  # Intentionally NOT parented

        self.number = number
        # QSizeF (width, height) of the loaded page in pixels. May be None
        # if the marker is created before the page is loaded.
        self._page_size = self._normalize_page_size(page_size)
        # Will be set by _update_size; keeps a single value used everywhere
        self._marker_size = 0.0
        # Reference to the item we are tracking for positioning
        self._tracked_item = parent

        self.setZValue(MARKER_LAYER_DEFAULT)
        self.setPen(QPen(Qt.white, 1))
        self.setBrush(QBrush(QColor(255, 0, 0)))  # Red background

        # NOTE: the marker is intentionally NOT parented to the text_item
        # / rect_item. Parenting it caused the marker to inherit the
        # parent's transform (scale, rotation) and grow on every auto-
        # resize of the text. As a top-level scene item the marker's
        # size is fully decoupled from the tracked item's transform.
        # The caller (image_viewer) is responsible for adding the marker
        # to the scene.

        # Text item for the number
        self.text_item = QGraphicsTextItem(str(number), self)
        self.text_item.setDefaultTextColor(Qt.white)
        # Remove document margin for better centering
        self.text_item.document().setDocumentMargin(0)

        # Font + size + position are all derived from the same value
        self._update_size()

        # Anchor the marker externally on the top-left corner of the tracked item
        if parent is not None:
            self.update_position_relative_to_item(parent)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_page_size(self, page_size):
        """Update the page size and recompute the marker diameter.

        Call this when the user navigates to a page with different
        dimensions so the badge keeps the correct relative size.
        """
        self._page_size = self._normalize_page_size(page_size)
        self._update_size()
        if self._tracked_item is not None:
            self.update_position_relative_to_item(self._tracked_item)

    def set_number(self, number):
        """Update the marker number and keep dimensions/position consistent."""
        self.number = number
        self.text_item.setPlainText(str(number))
        self._update_size()
        # Re-anchor so the new size stays centered on the corner
        if self._tracked_item is not None:
            self.update_position_relative_to_item(self._tracked_item)

    def set_font_size(self, font_size):
        """Backward-compat shim. Marker size is now driven by the page
        pixel size, not by the translation font size. The argument is
        ignored: we just refresh the marker with the current page size.
        """
        # Kept so callers like TextBlockItem.resize() can still call it
        # without changes; the marker size no longer depends on font_size.
        self._update_size()
        if self._tracked_item is not None:
            self.update_position_relative_to_item(self._tracked_item)

    def refresh_from_parent(self):
        """Refresh the marker's size (page-relative) and reposition it."""
        self._update_size()
        if self._tracked_item is not None:
            self.update_position_relative_to_item(self._tracked_item)

    def update_position_relative_to_item(self, item):
        """Anchor the marker EXTERNALLY on the top-left corner of ``item``.

        The marker is a top-level scene item, so its ``setPos`` is in
        scene coordinates. We always use ``item.mapToScene(0, 0)`` which
        is the scene position of the item's local (0, 0) point -- i.e.
        the visual top-left corner of the text box, including any of
        the item's own transform (scale, rotation, ...). This keeps the
        badge glued to the top-left of the box regardless of any
        transform applied to the tracked item.
        """
        if not item:
            return
        self._tracked_item = item  # Update tracked item
        top_left_scene = item.mapToScene(0, 0)
        self._apply_external_anchor(top_left_scene)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_page_size(page_size):
        """Accept QSizeF, (w, h) tuples, or None and return a QSizeF."""
        if page_size is None:
            return None
        if isinstance(page_size, QSizeF):
            return page_size
        # tuple / list (width, height)
        try:
            w, h = float(page_size[0]), float(page_size[1])
            return QSizeF(w, h)
        except (TypeError, ValueError, IndexError):
            return None

    def _update_size(self):
        """Compute the marker's diameter from the page size (single source
        of truth) and re-apply it consistently to rect, font and text pos.
        """
        # Diameter = a fixed fraction of the page's smaller dimension.
        if (self._page_size is not None
                and self._page_size.width() > 0
                and self._page_size.height() > 0):
            base = min(self._page_size.width(), self._page_size.height())
            self._marker_size = max(8.0, base * self.SIZE_RATIO)
        else:
            # Safe fallback when page size is unknown (shouldn't normally
            # happen because the image_viewer passes it in, but defensive).
            self._marker_size = self.DEFAULT_DIAMETER

        self.setRect(0, 0, self._marker_size, self._marker_size)

        # Number font sized to ~45% of the circle diameter so the digit
        # fills the badge nicely without overflowing.
        number_pt_size = max(6, int(self._marker_size / 2.2))
        number_font = QFont("Arial", number_pt_size, QFont.Bold)
        self.text_item.setFont(number_font)

        # Center the number inside the circle
        text_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self._marker_size - text_rect.width()) / 2,
            (self._marker_size - text_rect.height()) / 2,
        )

    def _apply_external_anchor(self, anchor_scene_pos=None):
        """Place the marker so its center is on the top-left corner.

        With the rect drawn from (0,0) to (size,size) in the marker's local
        coordinates, setting ``setPos(-size/2, -size/2)`` puts the circle's
        center exactly on (0,0) of the parent. The badge therefore extends
        outward (upper-left) and never covers the text inside the box.
        """
        offset = self._marker_size / 2
        if anchor_scene_pos is not None:
            self.setPos(anchor_scene_pos.x() - offset,
                        anchor_scene_pos.y() - offset)
        else:
            self.setPos(-offset, -offset)
