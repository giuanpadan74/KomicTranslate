import math
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtCore import Signal, QObject, QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QBrush, QCursor, QPen
from PySide6 import QtCore, QtGui  # QtGui usato in MoveableRectItem/MoveableEllipseItem.from_dict
from dataclasses import dataclass
from ..dayu_widgets.menu import MMenu
from .z_layers import HANDLE_LAYER_DEFAULT

@dataclass
class RectState:
    rect: tuple  # (x1, y1, x2, y2)
    rotation: float
    transform_origin: QPointF

    @classmethod
    def from_item(cls, item):
        """Create TextBlockState from a TextBlockItem"""
        rect = QRectF(item.pos(), item.boundingRect().size()).getCoords()
        return cls(
            rect=rect,
            rotation=item.rotation(),
            transform_origin=item.transformOriginPoint()
        )

class RectSignals(QObject):
    rectangle_changed = Signal(QRectF, float, tuple, QRectF)  # scene_rect, angle, tr_origin, local_rect
    change_undo = Signal(RectState, RectState)
    ocr_block = Signal()
    translate_block = Signal()

class MoveableRectItem(QGraphicsRectItem):
    shape_type = 'rectangle'

    def __init__(self, rect=None, parent=None, text_block=None):
        super().__init__(rect, parent)
        # 'signals' era un'attributo di CLASSE: un unico RectSignals condiviso da
        # tutte le istanze. Collegando N rettangoli allo stesso QObject, ogni
        # modifica di uno faceva scattare handle_rectangle_change (e i lambda
        # ocr_block/translate_block) N volte, con N chiamate heavy per evento.
        # Ora e' un'istanza per oggetto (il nome pubblico 'signals' e' invariato).
        self.signals = RectSignals()
        self.text_block = text_block
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setBrush(QBrush(QColor(255, 192, 203, 125)))  # Transparent pink
        self.setTransformOriginPoint(self.boundingRect().center())
        self.handle_size = 20
        self.resize_handle = None
        self.resize_start = None
        self.dragging = False
        self.drag_start = None
        self.drag_offset = None
        self.selected = False

        # Rotation properties
        self.rot_handle = None
        self.rotating = True
        self.last_rotation_angle = 0
        self.rotation_smoothing = 1.0 # rotation sensitivity
        self.center_scene_pos = None

        self.old_state = None

        # Numbered marker
        self.marker = None

        # Move handle
        self.move_handle = QGraphicsEllipseItem(-10, -10, 20, 20, self)
        self.move_handle.setBrush(QBrush(QColor(100, 255, 100, 200)))  # Green semi-transparent
        self.move_handle.setPen(QPen(Qt.GlobalColor.white, 2))
        self.move_handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.move_handle.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self.move_handle.setZValue(HANDLE_LAYER_DEFAULT)
        self.move_handle.hide()
        self._update_handle_position()

    def set_marker(self, marker):
        """Set the numbered marker for this rect box."""
        from shiboken6 import isValid

        # If there's an existing marker, remove it
        if self.marker and isValid(self.marker):
            try:
                if self.marker.scene():
                    self.marker.scene().removeItem(self.marker)
                try:
                    self.marker.setParentItem(None)
                except Exception:
                    pass
            except RuntimeError:
                pass

        if marker is not None and not isValid(marker):
            self.marker = None
            return

        self.marker = marker
        if self.marker:
            self.update_marker_position()

    def update_marker_position(self):
        """Update the marker's position relative to this rect box."""
        from shiboken6 import isValid
        try:
            marker = getattr(self, "marker", None)
            if not marker or not isValid(marker) or not self.scene():
                return
            marker.update_position_relative_to_item(self)
        except RuntimeError:
            self.marker = None

    def _update_handle_position(self):
        rect = self.rect()
        self.move_handle.setPos(rect.width() / 2, -15)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            # Salta gestione marker durante rimozione batch (delete)
            scene = self.scene()
            if scene is not None and getattr(scene, '_batch_removing', False):
                return super().itemChange(change, value)
            # Move marker to the new scene
            marker = getattr(self, "marker", None)
            if marker is not None:
                try:
                    from shiboken6 import isValid
                    if isValid(marker):
                        old_scene = marker.scene()
                        if old_scene is not None and old_scene is not value:
                            old_scene.removeItem(marker)
                        if value is not None:
                            value.addItem(marker)
                except RuntimeError:
                    pass
            self.update_marker_position()
        elif change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                        QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged):
            # Salta update marker durante drag per migliorare fluidità
            if not getattr(self, 'dragging', False):
                self.update_marker_position()
        return super().itemChange(change, value)

    def setRect(self, *args):
        super().setRect(*args)
        self._update_handle_position()

    def show_move_handle(self, show=True):
        self.move_handle.setVisible(show)

    def hoverMoveEvent(self, event):
        if self.selected:
            self.update_cursor(event.pos())
        else:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def focusOutEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.selected = False
        self.show_move_handle(False)
        self.update()
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        local_pos = event.pos()

        if event.button() == Qt.LeftButton:
            # Rimossa la gestione interna della selezione per lasciare che sia ImageViewer a gestirla
            self.show_move_handle(True)
            self.old_state = RectState.from_item(self)
            self.resize_handle = self.get_handle_at_position(local_pos, self.rect())
            if self.resize_handle:
                self.resize_start = scene_pos
            else:
                # Se non stiamo ridimensionando, iniziamo il trascinamento
                self.dragging = True
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
                self.drag_start = scene_pos
                self.drag_offset = scene_pos - self.mapToScene(self.rect().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resize_handle:
            self.resize_rectangle(event.pos())
        elif self.dragging:
            scene_pos = event.scenePos()
            local_pos = self.mapFromScene(scene_pos)
            local_last_scene = self.mapFromScene(event.lastScenePos())
            self.move_rectangle(local_pos, local_last_scene)

    def mouseReleaseEvent(self, event):
        if self.old_state:
            new_state = RectState.from_item(self)
            if self.old_state.rect != new_state.rect:
                self.signals.change_undo.emit(self.old_state, new_state)

        self.dragging = False
        self.drag_offset = None
        self.resize_handle = None
        self.resize_start = None
        self.rotating = False
        self.center_scene_pos = None
        # Aggiorna marker solo alla fine del drag (non durante)
        self.update_marker_position()
        self.update_cursor(event.pos())
        #self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        # Get the global position for the context menu
        scene_pos = event.scenePos()  # Position in the scene
        views = self.scene().views()  # Get all views associated with the scene

        if views:
            view = views[0]
            global_pos = view.mapToGlobal(view.mapFromScene(scene_pos))

            menu = MMenu(parent=view)
            ocr = menu.addAction(view.tr('OCR'))
            translate = menu.addAction(view.tr('Translate'))

            ocr.triggered.connect(self.signals.ocr_block.emit)
            translate.triggered.connect(self.signals.translate_block.emit)

            menu.exec_(global_pos)

            super().contextMenuEvent(event)

    def update_cursor(self, pos):
        cursor = self.get_cursor_for_position(pos)
        self.setCursor(QCursor(cursor))

    def get_cursor_for_position(self, pos):
        rect = self.boundingRect()
        handle = self.get_handle_at_position(pos, rect)
        
        cursors = {
            'top_left': Qt.CursorShape.SizeFDiagCursor,
            'top_right': Qt.CursorShape.SizeBDiagCursor,
            'bottom_left': Qt.CursorShape.SizeBDiagCursor,
            'bottom_right': Qt.CursorShape.SizeFDiagCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
        }
        
        if handle:
            cursor = cursors.get(handle, Qt.CursorShape.ArrowCursor)
            # Adjust cursor based on rotation
            rotation = self.rotation() % 360
            if 22.5 <= rotation < 67.5:
                cursor = self.rotate_cursor(cursor, 1)
            elif 67.5 <= rotation < 112.5:
                cursor = self.rotate_cursor(cursor, 2)
            elif 112.5 <= rotation < 157.5:
                cursor = self.rotate_cursor(cursor, 3)
            elif 157.5 <= rotation < 202.5:
                cursor = self.rotate_cursor(cursor, 4)
            elif 202.5 <= rotation < 247.5:
                cursor = self.rotate_cursor(cursor, 5)
            elif 247.5 <= rotation < 292.5:
                cursor = self.rotate_cursor(cursor, 6)
            elif 292.5 <= rotation < 337.5:
                cursor = self.rotate_cursor(cursor, 7)
            return cursor
        elif rect.contains(pos):
            # Se la casella è molto piccola o siamo lontani dai bordi, usa sempre SizeAll
            return Qt.CursorShape.SizeAllCursor
        else:
            return Qt.CursorShape.PointingHandCursor
            
    def rotate_cursor(self, cursor, steps):
        cursor_map = {
            Qt.SizeVerCursor: [Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor, Qt.SizeFDiagCursor] * 2,
            Qt.SizeHorCursor: [Qt.SizeHorCursor, Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor] * 2,
            Qt.SizeFDiagCursor: [Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor] * 2,
            Qt.SizeBDiagCursor: [Qt.SizeBDiagCursor, Qt.SizeHorCursor, Qt.SizeFDiagCursor, Qt.SizeVerCursor] * 2
        }
        return cursor_map.get(cursor, [cursor] * 8)[steps]

    def get_handle_at_position(self, pos, rect):
        handle_size = self.handle_size
        
        # Se la casella è molto piccola, riduciamo la dimensione effettiva delle maniglie
        # per lasciare spazio allo spostamento centrale
        min_dim = min(rect.width(), rect.height())
        effective_handle_size = handle_size
        if min_dim < handle_size * 1.5:
            effective_handle_size = min_dim / 3

        rect_rect = rect.toRect()
        top_left = rect_rect.topLeft()
        bottom_right = rect_rect.bottomRight()

        handles = {
            'top_left': QRectF(top_left.x() - effective_handle_size/2, top_left.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'top_right': QRectF(bottom_right.x() - effective_handle_size/2, top_left.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'bottom_left': QRectF(top_left.x() - effective_handle_size/2, bottom_right.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'bottom_right': QRectF(bottom_right.x() - effective_handle_size/2, bottom_right.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'top': QRectF(top_left.x(), top_left.y() - effective_handle_size/2, rect_rect.width(), effective_handle_size),
            'bottom': QRectF(top_left.x(), bottom_right.y() - effective_handle_size/2, rect_rect.width(), effective_handle_size),
            'left': QRectF(top_left.x() - effective_handle_size/2, top_left.y(), effective_handle_size, rect_rect.height()),
            'right': QRectF(bottom_right.x() - effective_handle_size/2, top_left.y(), effective_handle_size, rect_rect.height()),
        }

        # Solo se siamo vicini ai bordi permettiamo il ridimensionamento
        for handle, handle_rect in handles.items():
            if handle_rect.contains(pos):
                return handle

        return None
    
    def move_rectangle(self, local_pos: QtCore.QPointF, last_scene_pos: QtCore.QPointF):
        delta = self.mapToParent(local_pos) - self.mapToParent(last_scene_pos)
        new_pos = self.pos() + delta
        
        # Calculate the bounding rect of the rotated rectangle in scene coordinates
        scene_rect = self.mapToScene(self.boundingRect())
        bounding_rect = scene_rect.boundingRect()
        
        parent_rect = self.parentItem().boundingRect()
        
        # Constrain the movement
        if bounding_rect.left() + delta.x() < 0:
            new_pos.setX(self.pos().x() - bounding_rect.left())
        elif bounding_rect.right() + delta.x() > parent_rect.width():
            new_pos.setX(self.pos().x() + parent_rect.width() - bounding_rect.right())
        
        if bounding_rect.top() + delta.y() < 0:
            new_pos.setY(self.pos().y() - bounding_rect.top())
        elif bounding_rect.bottom() + delta.y() > parent_rect.height():
            new_pos.setY(self.pos().y() + parent_rect.height() - bounding_rect.bottom())
        
        self.setPos(new_pos)
        
        # Update Textblock
        new_rect = QRectF(new_pos, self.boundingRect().size())
        self.signals.rectangle_changed.emit(new_rect, self.rotation(), 
                                            (self.transformOriginPoint().x(), self.transformOriginPoint().y()),
                                            self.rect())



    def init_rotation(self, scene_pos):
        self.rotating = True
        center = self.boundingRect().center()
        self.center_scene_pos = self.mapToScene(center)
        self.last_rotation_angle = math.degrees(math.atan2(
            scene_pos.y() - self.center_scene_pos.y(),
            scene_pos.x() - self.center_scene_pos.x()
        ))

    def rotate_item(self, scene_pos):
        self.setTransformOriginPoint(self.boundingRect().center())
        current_angle = math.degrees(math.atan2(
            scene_pos.y() - self.center_scene_pos.y(),
            scene_pos.x() - self.center_scene_pos.x()
        ))
        
        angle_diff = current_angle - self.last_rotation_angle
        
        if angle_diff > 180:
            angle_diff -= 360
        elif angle_diff < -180:
            angle_diff += 360
        
        smoothed_angle = angle_diff / self.rotation_smoothing
        
        new_rotation = self.rotation() + smoothed_angle
        self.setRotation(new_rotation)
        self.last_rotation_angle = current_angle

        # Emit signal for rectangle change
        rect = QRectF(self.pos(), self.boundingRect().size())
        self.signals.rectangle_changed.emit(rect, self.rotation(), 
                                            (self.transformOriginPoint().x(), self.transformOriginPoint().y()),
                                            self.rect())

    def resize_rectangle(self, pos: QtCore.QPointF):
        if not self.resize_start:
            return
            
        # Convert positions to scene coordinates
        scene_pos = self.mapToScene(pos)

        # Get the current rectangle in local coordinates
        current_rect = self.rect()
        new_rect = QRectF(current_rect)

        # Rect Calcs
        # Map scene position back to item coordinates, taking rotation into account
        local_pos = self.mapFromScene(scene_pos)
        
        # Handle different resize handles
        if self.resize_handle == 'top_left':
            new_rect.setTopLeft(local_pos)
        elif self.resize_handle == 'top_right':
            new_rect.setTopRight(local_pos)
        elif self.resize_handle == 'bottom_left':
            new_rect.setBottomLeft(local_pos)
        elif self.resize_handle == 'bottom_right':
            new_rect.setBottomRight(local_pos)
        elif self.resize_handle == 'top':
            new_rect.setTop(local_pos.y())
        elif self.resize_handle == 'bottom':
            new_rect.setBottom(local_pos.y())
        elif self.resize_handle == 'left':
            new_rect.setLeft(local_pos.x())
        elif self.resize_handle == 'right':
            new_rect.setRight(local_pos.x())

        # Ensure minimum size
        min_size = 20
        if new_rect.width() < min_size:
            if 'right' in self.resize_handle:
                new_rect.setRight(new_rect.left() + min_size)
            else:
                new_rect.setLeft(new_rect.right() - min_size)
        
        if new_rect.height() < min_size:
            if 'bottom' in self.resize_handle:
                new_rect.setBottom(new_rect.top() + min_size)
            else:
                new_rect.setTop(new_rect.bottom() - min_size)

        # Calculate the change in position in scene coordinates
        old_pos = self.mapToScene(current_rect.topLeft())
        new_pos = self.mapToScene(new_rect.topLeft())
        pos_delta = new_pos - old_pos
        act_pos = self.pos() + pos_delta
        
        # Convert the new rectangle to scene coordinates to check bounds
        scene_rect = self.mapRectToScene(new_rect)
        parent_rect = self.parentItem().boundingRect()
        
        # Ensure the rectangle stays within parent bounds
        if (scene_rect.left() >= 0 and 
            scene_rect.right() <= parent_rect.right() and
            scene_rect.top() >= 0 and 
            scene_rect.bottom() <= parent_rect.bottom()):
            
            # Update the rectangle
            self.setPos(act_pos)
            self.setRect(0, 0, new_rect.width(), new_rect.height())

            # Update marker position after resize
            self.update_marker_position()

            # Emit signal for rectangle change
            rect = QRectF(act_pos, self.boundingRect().size())
            self.signals.rectangle_changed.emit(rect, self.rotation(),
                                                 (self.transformOriginPoint().x(), self.transformOriginPoint().y()),
                                                 self.rect())
    
    def to_dict(self):
        """Converte l'elemento in un dizionario per la serializzazione"""
        brush = self.brush()
        color = brush.color()
        
        # Ottieni il rettangolo in coordinate locali
        rect = self.rect()
        
        # Ottieni il punto di origine della trasformazione
        origin = self.transformOriginPoint()
        
        return {
            '__class__': 'MoveableRectItem',
            'rect': {
                'x': float(rect.x()),
                'y': float(rect.y()),
                'width': float(rect.width()),
                'height': float(rect.height())
            },
            'position': {
                'x': float(self.pos().x()),
                'y': float(self.pos().y())
            },
            'color': {
                'r': color.red(),
                'g': color.green(),
                'b': color.blue(),
                'a': color.alpha()
            },
            'transform_origin': {
                'x': float(origin.x()),
                'y': float(origin.y())
            },
            'rotation': float(self.rotation()),
            'handle_size': self.handle_size,
            'rotation_smoothing': self.rotation_smoothing,
            'is_visible': self.isVisible(),
            'is_enabled': self.isEnabled(),
            'z_value': float(self.zValue())
        }
    
    @classmethod
    def from_dict(cls, data):
        """Crea un'istanza dell'elemento a partire da un dizionario"""
        # Estrai i dati del rettangolo
        rect_data = data.get('rect', {})
        pos_data = data.get('position', {'x': 0, 'y': 0})
        color_data = data.get('color', {'r': 255, 'g': 192, 'b': 203, 'a': 125})
        origin_data = data.get('transform_origin', {'x': 0, 'y': 0})
        
        # Crea l'istanza
        rect = QtCore.QRectF(
            rect_data.get('x', 0),
            rect_data.get('y', 0),
            rect_data.get('width', 100),
            rect_data.get('height', 50)
        )
        
        item = cls(rect)
        
        # Imposta la posizione
        item.setPos(pos_data.get('x', 0), pos_data.get('y', 0))
        
        # Imposta il colore del pennello
        color = QtGui.QColor(
            color_data.get('r', 255),
            color_data.get('g', 192),
            color_data.get('b', 203),
            color_data.get('a', 125)
        )
        item.setBrush(QtGui.QBrush(color))
        
        # Imposta il punto di origine della trasformazione
        origin = QtCore.QPointF(
            origin_data.get('x', 0),
            origin_data.get('y', 0)
        )
        item.setTransformOriginPoint(origin)
        
        # Imposta la rotazione
        item.setRotation(data.get('rotation', 0))
        
        # Imposta le altre proprietà
        item.handle_size = data.get('handle_size', 20)
        item.rotation_smoothing = data.get('rotation_smoothing', 1.0)
        item.setVisible(data.get('is_visible', True))
        item.setEnabled(data.get('is_enabled', True))
        item.setZValue(data.get('z_value', 0))

        return item


class MoveableEllipseItem(QGraphicsEllipseItem):
    shape_type = 'ellipse'

    def __init__(self, rect=None, parent=None, text_block=None):
        super().__init__(rect, parent)
        # Vedi MoveableRectItem.__init__: istanza per oggetto, non attributo di classe.
        self.signals = RectSignals()
        self.text_block = text_block
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setBrush(QBrush(QColor(255, 192, 203, 125)))
        self.setTransformOriginPoint(self.boundingRect().center())
        self.handle_size = 20
        self.resize_handle = None
        self.resize_start = None
        self.dragging = False
        self.drag_start = None
        self.drag_offset = None
        self.selected = False

        self.rot_handle = None
        self.rotating = True
        self.last_rotation_angle = 0
        self.rotation_smoothing = 1.0
        self.center_scene_pos = None

        self.old_state = None

        # Numbered marker
        self.marker = None

        self.move_handle = QGraphicsEllipseItem(-10, -10, 20, 20, self)
        self.move_handle.setBrush(QBrush(QColor(100, 255, 100, 200)))
        self.move_handle.setPen(QPen(Qt.GlobalColor.white, 2))
        self.move_handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.move_handle.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self.move_handle.setZValue(HANDLE_LAYER_DEFAULT)
        self.move_handle.hide()
        self._update_handle_position()

    def set_marker(self, marker):
        """Set the numbered marker for this ellipse box."""
        from shiboken6 import isValid

        # If there's an existing marker, remove it
        if self.marker and isValid(self.marker):
            try:
                if self.marker.scene():
                    self.marker.scene().removeItem(self.marker)
                try:
                    self.marker.setParentItem(None)
                except Exception:
                    pass
            except RuntimeError:
                pass

        if marker is not None and not isValid(marker):
            self.marker = None
            return

        self.marker = marker
        if self.marker:
            self.update_marker_position()

    def update_marker_position(self):
        """Update the marker's position relative to this ellipse box."""
        from shiboken6 import isValid
        try:
            marker = getattr(self, "marker", None)
            if not marker or not isValid(marker) or not self.scene():
                return
            marker.update_position_relative_to_item(self)
        except RuntimeError:
            self.marker = None

    def _update_handle_position(self):
        rect = self.rect()
        self.move_handle.setPos(rect.width() / 2, -15)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            # Salta gestione marker durante rimozione batch (delete)
            scene = self.scene()
            if scene is not None and getattr(scene, '_batch_removing', False):
                return super().itemChange(change, value)
            # Move marker to the new scene
            marker = getattr(self, "marker", None)
            if marker is not None:
                try:
                    from shiboken6 import isValid
                    if isValid(marker):
                        old_scene = marker.scene()
                        if old_scene is not None and old_scene is not value:
                            old_scene.removeItem(marker)
                        if value is not None:
                            value.addItem(marker)
                except RuntimeError:
                    pass
            self.update_marker_position()
        elif change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                        QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged):
            # Salta update marker durante drag per migliorare fluidità
            if not getattr(self, 'dragging', False):
                self.update_marker_position()
        return super().itemChange(change, value)

    def setRect(self, *args):
        super().setRect(*args)
        self._update_handle_position()

    def show_move_handle(self, show=True):
        self.move_handle.setVisible(show)

    def hoverMoveEvent(self, event):
        if self.selected:
            self.update_cursor(event.pos())
        else:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def focusOutEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.selected = False
        self.show_move_handle(False)
        self.update()
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        local_pos = event.pos()

        if event.button() == Qt.LeftButton:
            # Rimossa la gestione interna della selezione per lasciare che sia ImageViewer a gestirla
            self.show_move_handle(True)
            self.old_state = RectState.from_item(self)
            self.resize_handle = self.get_handle_at_position(local_pos, self.rect())
            if self.resize_handle:
                self.resize_start = scene_pos
            else:
                self.dragging = True
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
                self.drag_start = scene_pos
                self.drag_offset = scene_pos - self.mapToScene(self.rect().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resize_handle:
            self.resize_ellipse(event.pos())
        elif self.dragging:
            scene_pos = event.scenePos()
            local_pos = self.mapFromScene(scene_pos)
            local_last_scene = self.mapFromScene(event.lastScenePos())
            self.move_ellipse(local_pos, local_last_scene)

    def mouseReleaseEvent(self, event):
        if self.old_state:
            new_state = RectState.from_item(self)
            if self.old_state.rect != new_state.rect:
                self.signals.change_undo.emit(self.old_state, new_state)

        self.dragging = False
        self.drag_offset = None
        self.resize_handle = None
        self.resize_start = None
        self.rotating = False
        self.center_scene_pos = None
        # Aggiorna marker solo alla fine del drag (non durante)
        self.update_marker_position()
        self.update_cursor(event.pos())
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        scene_pos = self.scenePos()
        views = self.scene().views()

        if views:
            view = views[0]
            global_pos = view.mapToGlobal(view.mapFromScene(scene_pos))

            menu = MMenu(parent=view)
            ocr = menu.addAction(view.tr('OCR'))
            translate = menu.addAction(view.tr('Translate'))

            ocr.triggered.connect(self.signals.ocr_block.emit)
            translate.triggered.connect(self.signals.translate_block.emit)

            menu.exec_(global_pos)

            super().contextMenuEvent(event)

    def update_cursor(self, pos):
        cursor = self.get_cursor_for_position(pos)
        self.setCursor(QCursor(cursor))

    def get_cursor_for_position(self, pos):
        rect = self.boundingRect()
        handle = self.get_handle_at_position(pos, rect)

        cursors = {
            'top_left': Qt.CursorShape.SizeFDiagCursor,
            'top_right': Qt.CursorShape.SizeBDiagCursor,
            'bottom_left': Qt.CursorShape.SizeBDiagCursor,
            'bottom_right': Qt.CursorShape.SizeFDiagCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
        }

        if handle:
            cursor = cursors.get(handle, Qt.CursorShape.ArrowCursor)
            rotation = self.rotation() % 360
            if 22.5 <= rotation < 67.5:
                cursor = self.rotate_cursor(cursor, 1)
            elif 67.5 <= rotation < 112.5:
                cursor = self.rotate_cursor(cursor, 2)
            elif 112.5 <= rotation < 157.5:
                cursor = self.rotate_cursor(cursor, 3)
            elif 157.5 <= rotation < 202.5:
                cursor = self.rotate_cursor(cursor, 4)
            elif 202.5 <= rotation < 247.5:
                cursor = self.rotate_cursor(cursor, 5)
            elif 247.5 <= rotation < 292.5:
                cursor = self.rotate_cursor(cursor, 6)
            elif 292.5 <= rotation < 337.5:
                cursor = self.rotate_cursor(cursor, 7)
            return cursor
        elif rect.contains(pos):
            return Qt.CursorShape.SizeAllCursor
        else:
            return Qt.CursorShape.PointingHandCursor

    def rotate_cursor(self, cursor, steps):
        cursor_map = {
            Qt.SizeVerCursor: [Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor, Qt.SizeFDiagCursor] * 2,
            Qt.SizeHorCursor: [Qt.SizeHorCursor, Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor] * 2,
            Qt.SizeFDiagCursor: [Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor] * 2,
            Qt.SizeBDiagCursor: [Qt.SizeBDiagCursor, Qt.SizeHorCursor, Qt.SizeFDiagCursor, Qt.SizeVerCursor] * 2
        }
        return cursor_map.get(cursor, [cursor] * 8)[steps]

    def get_handle_at_position(self, pos, rect):
        handle_size = self.handle_size

        min_dim = min(rect.width(), rect.height())
        effective_handle_size = handle_size
        if min_dim < handle_size * 1.5:
            effective_handle_size = min_dim / 3

        rect_rect = rect.toRect()
        top_left = rect_rect.topLeft()
        bottom_right = rect_rect.bottomRight()

        handles = {
            'top_left': QRectF(top_left.x() - effective_handle_size/2, top_left.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'top_right': QRectF(bottom_right.x() - effective_handle_size/2, top_left.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'bottom_left': QRectF(top_left.x() - effective_handle_size/2, bottom_right.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'bottom_right': QRectF(bottom_right.x() - effective_handle_size/2, bottom_right.y() - effective_handle_size/2, effective_handle_size, effective_handle_size),
            'top': QRectF(top_left.x(), top_left.y() - effective_handle_size/2, rect_rect.width(), effective_handle_size),
            'bottom': QRectF(top_left.x(), bottom_right.y() - effective_handle_size/2, rect_rect.width(), effective_handle_size),
            'left': QRectF(top_left.x() - effective_handle_size/2, top_left.y(), effective_handle_size, rect_rect.height()),
            'right': QRectF(bottom_right.x() - effective_handle_size/2, top_left.y(), effective_handle_size, rect_rect.height()),
        }

        for handle, handle_rect in handles.items():
            if handle_rect.contains(pos):
                return handle

        return None

    def move_ellipse(self, local_pos: QtCore.QPointF, last_scene_pos: QtCore.QPointF):
        delta = self.mapToParent(local_pos) - self.mapToParent(last_scene_pos)
        new_pos = self.pos() + delta

        scene_rect = self.mapToScene(self.boundingRect())
        bounding_rect = scene_rect.boundingRect()

        parent_rect = self.parentItem().boundingRect()

        if bounding_rect.left() + delta.x() < 0:
            new_pos.setX(self.pos().x() - bounding_rect.left())
        elif bounding_rect.right() + delta.x() > parent_rect.width():
            new_pos.setX(self.pos().x() + parent_rect.width() - bounding_rect.right())

        if bounding_rect.top() + delta.y() < 0:
            new_pos.setY(self.pos().y() - bounding_rect.top())
        elif bounding_rect.bottom() + delta.y() > parent_rect.height():
            new_pos.setY(self.pos().y() + parent_rect.height() - bounding_rect.bottom())

        self.setPos(new_pos)

        new_rect = QRectF(new_pos, self.boundingRect().size())
        self.signals.rectangle_changed.emit(new_rect, self.rotation(),
                                            (self.transformOriginPoint().x(), self.transformOriginPoint().y()),
                                            self.rect())

    def init_rotation(self, scene_pos):
        self.rotating = True
        center = self.boundingRect().center()
        self.center_scene_pos = self.mapToScene(center)
        self.last_rotation_angle = math.degrees(math.atan2(
            scene_pos.y() - self.center_scene_pos.y(),
            scene_pos.x() - self.center_scene_pos.x()
        ))

    def rotate_item(self, scene_pos):
        self.setTransformOriginPoint(self.boundingRect().center())
        current_angle = math.degrees(math.atan2(
            scene_pos.y() - self.center_scene_pos.y(),
            scene_pos.x() - self.center_scene_pos.x()
        ))

        angle_diff = current_angle - self.last_rotation_angle

        if angle_diff > 180:
            angle_diff -= 360
        elif angle_diff < -180:
            angle_diff += 360

        smoothed_angle = angle_diff / self.rotation_smoothing

        new_rotation = self.rotation() + smoothed_angle
        self.setRotation(new_rotation)
        self.last_rotation_angle = current_angle

        rect = QRectF(self.pos(), self.boundingRect().size())
        self.signals.rectangle_changed.emit(rect, self.rotation(),
                                            (self.transformOriginPoint().x(), self.transformOriginPoint().y()),
                                            self.rect())

    def resize_ellipse(self, pos: QtCore.QPointF):
        if not self.resize_start:
            return

        scene_pos = self.mapToScene(pos)
        current_rect = self.rect()
        new_rect = QRectF(current_rect)

        local_pos = self.mapFromScene(scene_pos)

        if self.resize_handle == 'top_left':
            new_rect.setTopLeft(local_pos)
        elif self.resize_handle == 'top_right':
            new_rect.setTopRight(local_pos)
        elif self.resize_handle == 'bottom_left':
            new_rect.setBottomLeft(local_pos)
        elif self.resize_handle == 'bottom_right':
            new_rect.setBottomRight(local_pos)
        elif self.resize_handle == 'top':
            new_rect.setTop(local_pos.y())
        elif self.resize_handle == 'bottom':
            new_rect.setBottom(local_pos.y())
        elif self.resize_handle == 'left':
            new_rect.setLeft(local_pos.x())
        elif self.resize_handle == 'right':
            new_rect.setRight(local_pos.x())

        min_size = 20
        if new_rect.width() < min_size:
            if 'right' in self.resize_handle:
                new_rect.setRight(new_rect.left() + min_size)
            else:
                new_rect.setLeft(new_rect.right() - min_size)

        if new_rect.height() < min_size:
            if 'bottom' in self.resize_handle:
                new_rect.setBottom(new_rect.top() + min_size)
            else:
                new_rect.setTop(new_rect.bottom() - min_size)

        old_pos = self.mapToScene(current_rect.topLeft())
        new_pos = self.mapToScene(new_rect.topLeft())
        pos_delta = new_pos - old_pos
        act_pos = self.pos() + pos_delta

        scene_rect = self.mapRectToScene(new_rect)
        parent_rect = self.parentItem().boundingRect()

        if (scene_rect.left() >= 0 and
            scene_rect.right() <= parent_rect.right() and
            scene_rect.top() >= 0 and
            scene_rect.bottom() <= parent_rect.bottom()):

            self.setPos(act_pos)
            self.setRect(0, 0, new_rect.width(), new_rect.height())

            # Update marker position after resize
            self.update_marker_position()

            rect = QRectF(act_pos, self.boundingRect().size())
            self.signals.rectangle_changed.emit(rect, self.rotation(),
                                                (self.transformOriginPoint().x(), self.transformOriginPoint().y()),
                                                self.rect())

    def to_dict(self):
        brush = self.brush()
        color = brush.color()
        rect = self.rect()
        origin = self.transformOriginPoint()

        return {
            '__class__': 'MoveableEllipseItem',
            'rect': {
                'x': float(rect.x()),
                'y': float(rect.y()),
                'width': float(rect.width()),
                'height': float(rect.height())
            },
            'position': {
                'x': float(self.pos().x()),
                'y': float(self.pos().y())
            },
            'color': {
                'r': color.red(),
                'g': color.green(),
                'b': color.blue(),
                'a': color.alpha()
            },
            'transform_origin': {
                'x': float(origin.x()),
                'y': float(origin.y())
            },
            'rotation': float(self.rotation()),
            'handle_size': self.handle_size,
            'rotation_smoothing': self.rotation_smoothing,
            'is_visible': self.isVisible(),
            'is_enabled': self.isEnabled(),
            'z_value': float(self.zValue())
        }

    @classmethod
    def from_dict(cls, data):
        rect_data = data.get('rect', {})
        pos_data = data.get('position', {'x': 0, 'y': 0})
        color_data = data.get('color', {'r': 255, 'g': 192, 'b': 203, 'a': 125})
        origin_data = data.get('transform_origin', {'x': 0, 'y': 0})

        rect = QtCore.QRectF(
            rect_data.get('x', 0),
            rect_data.get('y', 0),
            rect_data.get('width', 100),
            rect_data.get('height', 50)
        )

        item = cls(rect)

        item.setPos(pos_data.get('x', 0), pos_data.get('y', 0))

        color = QtGui.QColor(
            color_data.get('r', 255),
            color_data.get('g', 192),
            color_data.get('b', 203),
            color_data.get('a', 125)
        )
        item.setBrush(QtGui.QBrush(color))

        origin = QtCore.QPointF(
            origin_data.get('x', 0),
            origin_data.get('y', 0)
        )
        item.setTransformOriginPoint(origin)

        item.setRotation(data.get('rotation', 0))

        item.handle_size = data.get('handle_size', 20)
        item.rotation_smoothing = data.get('rotation_smoothing', 1.0)
        item.setVisible(data.get('is_visible', True))
        item.setEnabled(data.get('is_enabled', True))
        item.setZValue(data.get('z_value', 0))

        return item
