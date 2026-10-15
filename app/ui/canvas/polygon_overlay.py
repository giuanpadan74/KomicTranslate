import numpy as np

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPolygonItem,
)

from modules.utils.polygon_region import normalize_polygon_points, polygon_to_bbox
from .z_layers import POLYGON_HANDLE_LAYER_DEFAULT, POLYGON_OVERLAY_Z


class PolygonOverlaySignals(QObject):
    polygon_changed = Signal(object, object)


class PolygonHandleItem(QGraphicsEllipseItem):
    def __init__(self, index, parent=None):
        super().__init__(-5, -5, 10, 10, parent)
        self.index = index
        self._base_brush = QBrush(QColor(0, 220, 255, 220))
        self._selected_brush = QBrush(QColor(255, 20, 20, 255))
        self.setBrush(self._base_brush)
        self.setPen(QPen(Qt.white, 1))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(POLYGON_HANDLE_LAYER_DEFAULT)

    def set_selected(self, selected):
        self.setBrush(self._selected_brush if selected else self._base_brush)

    def mousePressEvent(self, event):
        overlay = self.parentItem()
        if overlay is not None:
            overlay.select_vertex(self.index)
        event.accept()

    def mouseMoveEvent(self, event):
        overlay = self.parentItem()
        if overlay is not None:
            overlay.update_vertex(self.index, overlay.mapFromScene(event.scenePos()))
        event.accept()

    def mouseReleaseEvent(self, event):
        overlay = self.parentItem()
        if overlay is not None:
            overlay.finish_edit()
        event.accept()


class EditablePolygonOverlay(QGraphicsPolygonItem):
    def __init__(self, rect_item, text_block, parent=None):
        super().__init__(parent)
        self.rect_item = rect_item
        self.text_block = text_block
        self.signals = PolygonOverlaySignals()
        self.handles = []
        self.selected_vertex = None
        self.setBrush(QBrush(QColor(0, 180, 255, 40)))
        self._base_pen = QPen(QColor(0, 220, 255, 190), 2, Qt.DashLine)
        self._selected_pen = QPen(QColor(255, 255, 0, 230), 3, Qt.SolidLine)
        self.setPen(self._base_pen)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setZValue(POLYGON_OVERLAY_Z)
        self.refresh_from_block()
        self.set_selected(False)

    def refresh_from_block(self):
        self.selected_vertex = None
        if hasattr(self.text_block, "get_active_inpaint_polygon"):
            points = normalize_polygon_points(self.text_block.get_active_inpaint_polygon())
        else:
            points = normalize_polygon_points(getattr(self.text_block, "polygon_points", None))
        if points is None:
            self.hide()
            return False
        self.setPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in points]))
        self._sync_handles()
        self.show()
        return True

    def set_selected(self, selected):
        polygon_mode = bool(getattr(self.text_block, "use_polygon_inpaint", True))
        self.setPen(self._selected_pen if selected else self._base_pen)
        if not selected:
            self.selected_vertex = None
        for handle in self.handles:
            handle.setVisible(selected and polygon_mode)
            handle.set_selected(False)

    def _sync_handles(self):
        points = self.polygon()
        while len(self.handles) < len(points):
            handle = PolygonHandleItem(len(self.handles), self)
            self.handles.append(handle)
        for index, handle in enumerate(self.handles):
            visible = index < len(points)
            handle.setVisible(visible)
            if visible:
                handle.index = index
                handle.setPos(points[index])
                handle.set_selected(self.selected_vertex == index)

    def select_vertex(self, index):
        old_selected = self.selected_vertex
        self.selected_vertex = index
        for handle in self.handles:
            if handle.index == old_selected:
                handle.set_selected(False)
            if handle.index == index:
                handle.set_selected(True)

    def update_vertex(self, index, point):
        if not getattr(self.text_block, "use_polygon_inpaint", True):
            return
        polygon = self.polygon()
        if index < 0 or index >= len(polygon):
            return
        # Create new list with updated point
        new_points = [polygon[i] for i in range(len(polygon))]
        new_points[index] = QPointF(point.x(), point.y())
        new_polygon = QPolygonF(new_points)
        self.setPolygon(new_polygon)
        self._sync_handles()
        self._sync_block(emit_signal=False)

    def delete_selected_vertex(self):
        if not getattr(self.text_block, "use_polygon_inpaint", True):
            return
        if self.selected_vertex is None:
            return
        polygon = self.polygon()
        if len(polygon) <= 3:
            return  # Don't delete last 3 vertices to keep polygon valid
        # Remove the selected vertex by creating a new list without it
        new_points = [polygon[i] for i in range(len(polygon)) if i != self.selected_vertex]
        new_polygon = QPolygonF(new_points)
        self.selected_vertex = None
        self.setPolygon(new_polygon)
        self._sync_handles()
        self._sync_block(emit_signal=True)

    def add_vertex_after_selected(self):
        if not getattr(self.text_block, "use_polygon_inpaint", True):
            return
        if self.selected_vertex is None:
            return
        polygon = self.polygon()
        current_index = self.selected_vertex
        next_index = current_index + 1
        if next_index >= len(polygon):
            return  # Selected vertex is last, no next vertex
        # Calculate midpoint
        p1 = polygon[current_index]
        p2 = polygon[next_index]
        midpoint = QPointF(
            (p1.x() + p2.x()) / 2,
            (p1.y() + p2.y()) / 2
        )
        # Insert new vertex by creating new list
        new_points = []
        for i in range(len(polygon)):
            new_points.append(polygon[i])
            if i == current_index:
                new_points.append(midpoint)
        new_polygon = QPolygonF(new_points)
        self.setPolygon(new_polygon)
        self.selected_vertex = next_index  # Select the new vertex
        self._sync_handles()
        self._sync_block(emit_signal=True)

    def finish_edit(self):
        self._sync_block(emit_signal=True)

    def _sync_block(self, emit_signal):
        points = np.array(
            [[int(round(point.x())), int(round(point.y()))] for point in self.polygon()],
            dtype=np.int32,
        )
        points = normalize_polygon_points(points)
        if points is None:
            return
        self.text_block.polygon_points = points
        self.text_block.segm_pts = points
        bbox = polygon_to_bbox(points)
        if bbox is not None:
            self.text_block.bubble_xyxy = bbox
        self.text_block.filter_inpaint_bboxes()
        if emit_signal:
            self.signals.polygon_changed.emit(self.rect_item, points)

    def mousePressEvent(self, event):
        if not getattr(self.text_block, "use_polygon_inpaint", True):
            event.ignore()
            return
        if self.rect_item is not None:
            self.rect_item.selected = True
        # Deselect vertex if clicking on the polygon background
        if self.selected_vertex is not None:
            self.select_vertex(None)
        super().mousePressEvent(event)


def remove_polygon_overlay(rect_item, viewer):
    overlay = getattr(rect_item, "polygon_overlay", None)
    if overlay is None:
        return
    try:
        if overlay.scene() is not None:
            overlay.scene().removeItem(overlay)
    except RuntimeError:
        pass
    if hasattr(viewer, "polygon_overlays") and overlay in viewer.polygon_overlays:
        viewer.polygon_overlays.remove(overlay)
    rect_item.polygon_overlay = None
