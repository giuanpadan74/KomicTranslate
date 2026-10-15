from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .rectangle import MoveableEllipseItem, MoveableRectItem
from .text_item import TextBlockItem


class DragHandler:
    def __init__(self, viewer: QtWidgets.QGraphicsView):
        self._viewer = viewer
        self._dragged_item: Optional[QtWidgets.QGraphicsItem] = None
        self._last_scene_pos: Optional[QtCore.QPointF] = None

    @property
    def is_dragging(self) -> bool:
        return self._dragged_item is not None

    def capture_if_item_started_drag(
        self,
        clicked_item: Optional[QtWidgets.QGraphicsItem],
        scene_pos: QtCore.QPointF,
    ) -> None:
        if clicked_item is None:
            return

        if isinstance(clicked_item, TextBlockItem):
            if getattr(clicked_item, "_is_dragging", False):
                self._dragged_item = clicked_item
                self._last_scene_pos = scene_pos
            return

        if isinstance(clicked_item, (MoveableRectItem, MoveableEllipseItem)):
            if getattr(clicked_item, "dragging", False):
                self._dragged_item = clicked_item
                self._last_scene_pos = scene_pos

    def handle_mouse_move(self, scene_pos: QtCore.QPointF) -> bool:
        if self._dragged_item is None:
            return False

        sel_item = self._dragged_item
        last_scene_pos = self._last_scene_pos if self._last_scene_pos is not None else scene_pos

        local_pos = sel_item.mapFromScene(scene_pos)
        last_local_pos = sel_item.mapFromScene(last_scene_pos)

        if isinstance(sel_item, TextBlockItem):
            sel_item.move_item(local_pos, last_local_pos)
        elif isinstance(sel_item, (MoveableRectItem, MoveableEllipseItem)):
            sel_item.move_rectangle(local_pos, last_local_pos)
        elif hasattr(sel_item, "move_item"):
            sel_item.move_item(local_pos, last_local_pos)
        else:
            return False

        self._last_scene_pos = scene_pos
        return True

    def end_drag(self) -> None:
        self._dragged_item = None
        self._last_scene_pos = None

