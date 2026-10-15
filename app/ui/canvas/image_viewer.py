import cv2
import numpy as np
from typing import List, Dict, Optional
import math

from PySide6 import QtWidgets
from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtCore import  Signal, QEvent, QLineF
from PySide6.QtGui import QTransform, QEventPoint

from .text_item import TextBlockItem, TextBlockState
from .text_outline_utils import outline_color_for_loading, outline_enabled_from_data
from .text_box_marker import TextBoxMarker
from .polygon_overlay import remove_polygon_overlay
from .rectangle import MoveableRectItem, MoveableEllipseItem, RectState
from .rotate_cursor import RotateHandleCursors
from .drag_handler import DragHandler
from .brush_layer_rules import apply_brush_stroke_layer, apply_text_box_layer, ensure_text_items_layer
from .item_validity import is_live_graphics_item, prune_graphics_items
from .pixmap_state import sync_viewer_photo_to_image_data

from ..commands.brush import BrushStrokeCommand, ClearBrushStrokesCommand, \
                            SegmentBoxesCommand, EraseUndoCommand
from ..commands.bucket import BucketFillCommand
from ..commands.box import ClearRectsCommand
from ..commands.base import PathCommandBase as pcb
from ..commands.async_bucket import BucketFillUIController
from .layer_manager import LayerManager, LayerType, LayerGroup
from .z_layers import (
    BRUSH_STROKE_Z,
    MARKER_LAYER_DEFAULT,
    IMPORTED_SHAPE_LAYER_DEFAULT,
    IMPORTED_SHAPE_LAYER_MAX,
    IMPORTED_SHAPE_LAYER_MIN,
    TEXT_BOX_Z,
    WORK_SELECTION_Z,
    clamp_imported_shape_z,
)

class ImageViewer(QtWidgets.QGraphicsView):
    rectangle_created = Signal(MoveableRectItem)
    rectangle_selected = Signal(QtCore.QRectF)
    rectangle_deleted = Signal(QtCore.QRectF)
    command_emitted = Signal(QtGui.QUndoCommand)
    connect_rect_item = Signal(MoveableRectItem)
    connect_text_item =  Signal(TextBlockItem)

    eyedropperColorPicked = Signal(QtGui.QColor)  # Segnale per l'eyedropper del pennello avanzato

    def __init__(self, parent):
        super().__init__(parent)
        self.zoom = 0
        self.empty = True
        self._scene = QtWidgets.QGraphicsScene(self)
        self.photo = QtWidgets.QGraphicsPixmapItem()
        self.rotate_cursors = RotateHandleCursors()
        self.photo.setShapeMode(QtWidgets.QGraphicsPixmapItem.BoundingRectShape)
        self._scene.addItem(self.photo)
        self.setScene(self._scene)
        # Pixel size (W, H) of the currently loaded page. Stored here so
        # the text-box markers can size themselves as a fixed fraction of
        # the page, instead of being derived from the (auto-scaled) font
        # size -- which caused markers to grow on every resize.
        self._current_page_size = QtCore.QSizeF()
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(30, 30, 30)))
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.viewport().grabGesture(QtCore.Qt.GestureType.PanGesture)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.current_tool = None
        self.box_mode = False
        # fit_mode: 0=fit to height (default), 1=fit to width, 2=fit to page
        self.fit_mode = 0
        self.start_point = None
        self.current_rect = None
        self.rectangles = []
        self.polygon_overlays = []
        self.text_items = []
        self.text_item_markers = []
        self.rect_item_markers = []
        self._original_overlay = None
        self.markers_visible = True
        self.polygons_visible = True
        self.rect_boxes_visible = True
        self.text_boxes_hidden = False
        self.selected_rect = None
        self.selected_rects = []  # Lista per selezione multipla
        self._scene._batch_removing = False
        self.panning = False
        self.pan_start_pos = None
        self.drag_handler = DragHandler(self)
        # Cache per sel_rot_item durante drag - evita iterare su tutti gli item ad ogni mousemove
        self._cached_sel_rot_item = (None, None)
        self._sel_rot_item_cache_valid = False

        # Gerarchia layer centralizzata in z_layers.py
        self.layer_manager = LayerManager(self._scene)



        # Proprietà pennello inpainting (sempre rosso)
        self.inpaint_brush_color = QtGui.QColor(255, 0, 0, 100)
        self.brush_size = 25
        self.brush_scaled_size = 25  # Dimensione scalata effettiva per il disegno
        self.drawing_path = None
        self.eraser_size = 25
        self.eraser_scaled_size = 25  # Dimensione scalata effettiva per la gomma
        
        # Proprietà painting (Penna e Secchiello)
        self.painting_color = QtGui.QColor(0, 0, 0, 255) # Nero opaco di default
        self.pen_size = 5
        self.pen_scaled_size = 5
        
        self.eyedropper_mode = False
        self.eyedropper_cursor = QtGui.QCursor(QtCore.Qt.CrossCursor)
        
        # Proprietà secchiello (bucket fill)
        self.bucket_fill_tolerance = 32  # Tolleranza flood fill (0-100)

        self.brush_cursor = self.create_inpaint_cursor('brush', self.brush_size)
        self.eraser_cursor = self.create_inpaint_cursor('eraser', self.eraser_size)
        self.pen_cursor = self.create_inpaint_cursor('pen', self.pen_size)

        self.current_path = None
        self.current_path_item = None

        self.before_erase = []
        self.after_erase = []

        self.last_pan_pos = QtCore.QPoint()
        self.total_scale_factor = 0.2

        self._border_color = QtGui.QColor(255, 0, 0)
        self._fill_color = QtGui.QColor(255, 255, 255)
        self._border_width = 2  # Spessore bordo predefinito
        
        # Variabili per il trascinamento degli handle del corno
        self._tail_handle_being_dragged = None
        self._tail_drag_start_pos = None
        self._tail_item_being_dragged = None
        
        # selected_shape rimosso - ora si utilizzano solo SVG
        
        # Attributi per il trascinamento degli handle del corno
        self.dragging_tail_handle = False
        self.tail_handle_name = None

        # Controller per bucket fill asincrono
        self._bucket_controller: Optional[BucketFillUIController] = None

    def hasPhoto(self):
        return not self.empty
    
    def _find_settings_page(self):
        """Trova la pagina delle impostazioni dalla gerarchia della finestra."""
        from app.ui.settings.settings_page import SettingsPage
        window = self.window()
        if window and hasattr(window, 'settings_page'):
            return window.settings_page
        if window:
            for child in window.children():
                if isinstance(child, SettingsPage):
                    return child
        return None

    def viewportEvent(self, event):
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            touch_points = event.points()

            if len(touch_points) == 2:
                # Multi-finger touch: implement scaling logic
                touchPoint0 = touch_points[0]
                touchPoint1 = touch_points[1]
                current_scale_factor = (
                    QLineF(touchPoint0.pos(), touchPoint1.pos()).length() /
                    QLineF(touchPoint0.startPos(), touchPoint1.startPos()).length()
                )
                if any(tp.state() == QEventPoint.State.Released for tp in touch_points):
                    self.total_scale_factor *= current_scale_factor
                    current_scale_factor = 1.0
                scale_factor = self.total_scale_factor * current_scale_factor
                self.setTransform(QTransform.fromScale(scale_factor, scale_factor))
                return True

        if event.type() == QtCore.QEvent.Type.Gesture:
            return self.gestureEvent(event)

        return super().viewportEvent(event)

    def gestureEvent(self, event):
        pan = event.gesture(QtCore.Qt.GestureType.PanGesture)
        pinch = event.gesture(QtCore.Qt.GestureType.PinchGesture)
        
        if pan:
            return self.handlePanGesture(pan)
        elif pinch:
            return self.handlePinchGesture(pinch)
        return False

    def handlePanGesture(self, gesture):
        delta = gesture.delta()
        new_pos = self.last_pan_pos + delta.toPoint()
        
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - (new_pos.x() - self.last_pan_pos.x())
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - (new_pos.y() - self.last_pan_pos.y())
        )
        
        self.last_pan_pos = new_pos
        return True

    def handlePinchGesture(self, gesture):
        scale_factor = gesture.scaleFactor()
        center = gesture.centerPoint()
        
        if gesture.state() == QtCore.Qt.GestureState.GestureStarted:
            self._pinch_center = self.mapToScene(center.toPoint())
        
        if scale_factor != 1:
            self.scale(scale_factor, scale_factor)
            self.zoom += (scale_factor - 1)
        
        if gesture.state() == QtCore.Qt.GestureState.GestureFinished:
            self._pinch_center = QtCore.QPointF()
        
        return True

    def wheelEvent(self, event):
        if self.hasPhoto():
            if event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
                # Zoom with Ctrl + Wheel
                factor = 1.25
                if event.angleDelta().y() > 0:
                    self.scale(factor, factor)
                    self.zoom += 1
                else:
                    self.scale(1 / factor, 1 / factor)
                    self.zoom -= 1
            else:
                # Scroll without Ctrl
                super().wheelEvent(event)

    def fitInView(self):
        try:
            # Verifica che l'oggetto photo e il suo pixmap esistano
            if not hasattr(self, 'photo') or not self.photo or not self.photo.pixmap():
                return
                
            # Ottieni il rettangolo del pixmap in modo sicuro
            pixmap = self.photo.pixmap()
            if not pixmap or pixmap.isNull():
                print("Warning: Invalid pixmap in fitInView")
                return
                
            rect = QtCore.QRectF(pixmap.rect())
            if rect.isNull():
                return
                
            self.setSceneRect(rect)
            if self.hasPhoto():
                unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
                if unity.width() > 0 and unity.height() > 0:
                    self.scale(1 / unity.width(), 1 / unity.height())
                    viewrect = self.viewport().rect()
                    scenerect = self.transform().mapRect(rect)
                    
                    # Evita divisioni per zero
                    if scenerect.width() > 0 and scenerect.height() > 0:
                        factor = min(viewrect.width() / scenerect.width(),
                                   viewrect.height() / scenerect.height())
                        self.scale(factor, factor)
                        self.centerOn(rect.center())
        except Exception as e:
            print(f"Error in fitInView: {str(e)}")

    def fit_to_width(self):
        """Adatta l'immagine alla massima larghezza possibile."""
        try:
            if not self.hasPhoto():
                return
            pixmap = self.photo.pixmap()
            rect = QtCore.QRectF(pixmap.rect())
            self.setSceneRect(rect)
            
            unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
            if unity.width() > 0 and unity.height() > 0:
                self.scale(1 / unity.width(), 1 / unity.height())
                viewrect = self.viewport().rect()
                scenerect = self.transform().mapRect(rect)
                
                if scenerect.width() > 0:
                    factor = viewrect.width() / scenerect.width()
                    self.scale(factor, factor)
                    self.centerOn(rect.center())
        except Exception as e:
            print(f"Error in fit_to_width: {str(e)}")

    def fit_to_height(self):
        """Adatta l'immagine alla massima altezza possibile."""
        try:
            if not self.hasPhoto():
                return
            pixmap = self.photo.pixmap()
            rect = QtCore.QRectF(pixmap.rect())
            self.setSceneRect(rect)
            
            unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
            if unity.width() > 0 and unity.height() > 0:
                self.scale(1 / unity.width(), 1 / unity.height())
                viewrect = self.viewport().rect()
                scenerect = self.transform().mapRect(rect)
                
                if scenerect.height() > 0:
                    factor = viewrect.height() / scenerect.height()
                    self.scale(factor, factor)
                    self.centerOn(rect.center())
        except Exception as e:
            print(f"Error in fit_to_height: {str(e)}")

    def scroll_up(self):
        """Scorre l'immagine verso l'alto."""
        step = self.viewport().height() // 4
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - step)

    def scroll_down(self):
        """Scorre l'immagine verso il basso."""
        step = self.viewport().height() // 4
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + step)

    def smartFit(self):
        """Adatta l'immagine in base alle impostazioni (altezza, larghezza o vista completa)."""
        if self.fit_mode == 1:
            self.fit_to_width()
        elif self.fit_mode == 2:
            self.fitInView()
        else:
            self.fit_to_height()

    def set_tool(self, tool: str):
        self.current_tool = tool
        self.eyedropper_mode = False  # Reset eyedropper quando si cambia strumento
        
        # Determina se le caselle di testo devono essere bloccate
        # Quando si usano strumenti di painting (pennello, penna, secchiello)
        # le caselle di testo non devono essere modificabili
        painting_tools = ['brush', 'pen', 'bucket']
        lock_text_boxes = tool in painting_tools
        self._set_text_items_locked(lock_text_boxes)
        
        if tool == 'pan':
            self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        elif tool == 'box':
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self.setCursor(QtCore.Qt.CrossCursor)
        elif tool == 'brush':
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            # Sync size before setting cursor
            if self.brush_scaled_size != self.brush_size:
                self.set_br_er_size(self.brush_size, self.brush_size, tool_type='brush')
            self.setCursor(self.brush_cursor)
        elif tool == 'eraser':
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            # Sync size before setting cursor
            if self.eraser_scaled_size != self.eraser_size:
                self.set_br_er_size(self.eraser_size, self.eraser_size, tool_type='eraser')
            self.setCursor(self.eraser_cursor)
        elif tool == 'pen':
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            # Sync size before setting cursor
            if self.pen_scaled_size != self.pen_size:
                self.set_br_er_size(self.pen_size, self.pen_size, tool_type='pen')
            self.setCursor(self.pen_cursor)
        elif tool == 'eyedropper':
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self.eyedropper_mode = True
            self.setCursor(self.eyedropper_cursor)
        elif tool == 'bucket':
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self.setCursor(QtCore.Qt.CrossCursor)
        elif tool == 'svg':
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self.setCursor(QtCore.Qt.CrossCursor)
        else:
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            # Reset cursor to cross or arrow by default?
            self.setCursor(QtCore.Qt.ArrowCursor)

    def _set_text_items_locked(self, locked: bool):
        """
        Blocca o sblocca l'interazione con le caselle di testo.
        Quando locked=True, le caselle di testo non possono essere
        ridimensionate, spostate o editate (utile per i tool di painting).
        
        Args:
            locked: True per bloccare, False per sbloccare
        """
        from PySide6.QtWidgets import QGraphicsItem
        
        for text_item in self.text_items:
            if text_item is None:
                continue
            try:
                if locked:
                    # Disabilita flag di interazione
                    text_item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False
                    )
                    text_item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False
                    )
                    # Esci dalla modalità editing se attiva
                    if hasattr(text_item, 'editing_mode') and text_item.editing_mode:
                        text_item.exit_editing_mode()
                    # Nascondi handle di move
                    if hasattr(text_item, 'show_move_handle'):
                        text_item.show_move_handle(False)
                else:
                    # Riabilita flag di interazione
                    text_item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True
                    )
                    text_item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True
                    )
            except RuntimeError:
                # L'oggetto C++ potrebbe essere stato eliminato
                pass

    def delete_selected_rectangle(self):
        if self.selected_rect:
            rect = self.selected_rect.mapRectToScene(self.selected_rect.rect())
            self.rectangle_deleted.emit(rect)
            self._scene.removeItem(self.selected_rect)
            self.rectangles.remove(self.selected_rect)
            self.selected_rect = None
            # Update markers after deletion
            try:
                from controller import ComicTranslate
                ct = self.parent()
                while ct and not isinstance(ct, ComicTranslate):
                    ct = ct.parent()
                if ct and hasattr(ct, 'font_size_dropdown'):
                    from app.ui.font_size_utils import parse_font_size as _pfs
                    font_size = _pfs(ct.font_size_dropdown.currentText())
                    self.update_all_markers(font_size=font_size)
            except Exception as e:
                print(f"[WARNING] Errore aggiornamento marcatori: {str(e)}")

    def toggle_shape(self, use_rectangle: bool = None):
        """
        Alterna ciclicamente tra Rettangolo ed Ellisse per gli elementi selezionati.
        
        Args:
            use_rectangle: Se specificato, forza la forma desiderata. 
                          Se None (default), inverte la forma attuale.
        """
        selected_items = self.get_selected_rectangles()
        if not selected_items:
            return

        from .shape_detector import ShapeDetector
        
        for item in selected_items:
            current_shape = ShapeDetector.detect_shape_from_item(item)
            
            if use_rectangle is None:
                should_be_rectangle = (current_shape != 'rectangle')
            else:
                should_be_rectangle = use_rectangle
            
            if (should_be_rectangle and current_shape == 'rectangle') or \
               (not should_be_rectangle and current_shape == 'ellipse'):
                continue

            # Preservazione proprietà originali per transizione fluida
            local_rect = item.rect()
            w, h = local_rect.width(), local_rect.height()
            pos = item.pos()
            rotation = item.rotation()
            tr_origin = item.transformOriginPoint()
            brush = item.brush()
            z_value = item.zValue()
            text_block = getattr(item, 'text_block', None)
            
            # Creazione del nuovo item con la forma opposta
            if should_be_rectangle:
                new_item = MoveableRectItem(QtCore.QRectF(0, 0, w, h), self.photo, text_block=text_block)
                if text_block:
                    text_block.shape_type = 'rectangle'
                    text_block.filter_inpaint_bboxes()
            else:
                new_item = MoveableEllipseItem(QtCore.QRectF(0, 0, w, h), self.photo, text_block=text_block)
                if text_block:
                    text_block.shape_type = 'ellipse'
                    text_block.filter_inpaint_bboxes()
            
            new_item.setPos(pos)
            new_item.setRotation(rotation)
            new_item.setTransformOriginPoint(tr_origin)
            new_item.setBrush(brush)
            new_item.setZValue(z_value)
            
            idx = self.rectangles.index(item)
            self.rectangles[idx] = new_item
            remove_polygon_overlay(item, self)
            self._scene.removeItem(item)
            self.connect_rect_item.emit(new_item)
            
            # Mantieni lo stato di selezione
            new_item.selected = True
        
        self.update()

    def find_rect_at_pos(self, pos):
        """Trova un MoveableRectItem o MoveableEllipseItem alla posizione data,
           considerando figli e elementi sovrapposti."""
        clicked_item = self.itemAt(pos)
        
        def get_main_item(item):
            current = item
            while current is not None:
                if current == self.photo:
                    return None
                if isinstance(current, (MoveableRectItem, MoveableEllipseItem)):
                    return current
                linked_rect = getattr(current, 'rect_item', None)
                if isinstance(linked_rect, (MoveableRectItem, MoveableEllipseItem)):
                    return linked_rect
                current = current.parentItem()
            return None

        # Controlla prima l'elemento in cima
        main_item = get_main_item(clicked_item)
        if main_item:
            return main_item
            
        # Se l'elemento in cima non è un rettangolo, controlla tutti gli elementi in quella posizione
        # (per esempio se c'è del testo sopra)
        items = self.items(pos)
        for item in items:
            main_item = get_main_item(item)
            if main_item:
                return main_item
        return None

    def mousePressEvent(self, event):
        pos = event.pos()
        clicked_item = self.itemAt(pos)
        scene_pos = self.mapToScene(pos)
        
        # Gestione selezione multipla con tasti modificatori
        modifiers = event.modifiers()
        add_to_selection = bool(modifiers & (QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier))

        # Cerca se c'è un rettangolo/ellisse, anche se coperto da testo o altro
        rect_at_pos = self.find_rect_at_pos(pos)
        
        # Se abbiamo cliccato un rettangolo/ellisse, usiamo quello come clicked_item principale
        if rect_at_pos:
            clicked_item = rect_at_pos
        elif clicked_item == self.photo:
            clicked_item = None
        elif clicked_item and clicked_item.parentItem() == self.photo:
            pass # È già l'item principale
        elif clicked_item and clicked_item.parentItem() and clicked_item.parentItem().parentItem() == self.photo:
            clicked_item = clicked_item.parentItem()

        # Se siamo in modalità move e il click è vuoto, proviamo a selezionare un TextBlock vicino
        if self.current_tool == 'move' and clicked_item is None:
            for item in self._scene.items():
                if isinstance(item, TextBlockItem):
                    if item.boundingRect().contains(item.mapFromScene(scene_pos)):
                        clicked_item = item
                        item.setSelected(True)
                        break

        # Handle rotation and selection for existing items
        if event.button() == QtCore.Qt.LeftButton:
            blk_item, rect_item = self.sel_rot_item()
            if blk_item or rect_item:
                sel_item = blk_item if blk_item else rect_item
                local_pos = sel_item.mapFromScene(scene_pos)
                buffer = 25     
                angle = sel_item.rotation()
                inner_rect = sel_item.boundingRect()
                outer_rect = inner_rect.adjusted(-buffer, -buffer, buffer, buffer)
                sel_item.rot_handle = self.get_rotate_handle(outer_rect, local_pos, angle)

                if sel_item.rot_handle: 
                    if isinstance(sel_item, (MoveableRectItem, MoveableEllipseItem)):
                        sel_item.old_state = RectState.from_item(sel_item)
                    else:
                        sel_item.old_state = TextBlockState.from_item(sel_item)
                    sel_item.init_rotation(scene_pos)
                    event.accept()
                    return  # Exit early if handling rotation

        # Rimossa gestione balloon - funzionalità eliminata

        # Handle deselection
        if clicked_item is None:
            if not add_to_selection:
                self.deselect_all()
        else:
            if not add_to_selection:
                # Se non c'è il tasto Shift/Ctrl, deseleziona tutto tranne quello cliccato
                for item in self._scene.items():
                    if isinstance(item, (TextBlockItem, MoveableRectItem, MoveableEllipseItem)) and item != clicked_item:
                        if isinstance(item, TextBlockItem):
                            item.handleDeselection()
                        else:
                            self.deselect_rect(item)
            
            # Gestione selezione forme tradizionali rimossa - ora si utilizzano solo SVG

        # Handle panning
        if event.button() == QtCore.Qt.MiddleButton and self.current_tool == 'pan':
            self.panning = True
            self.pan_start_pos = event.position()
            self.viewport().setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # Handle eyedropper
        if self.eyedropper_mode and self.hasPhoto():
            if self.photo.contains(scene_pos):
                picked_color = self.pick_color_at_position(scene_pos)
                self.set_painting_color(picked_color)
                # Torna allo strumento precedente o default
                self.eyedropper_mode = False
                if self.current_tool == 'pen':
                    self.setCursor(self.pen_cursor)
                elif self.current_tool == 'bucket':
                    self.setCursor(QtCore.Qt.CrossCursor)
                else:
                    self.setCursor(QtCore.Qt.ArrowCursor)
                event.accept()
                return
        # Handle drawing tools
        if self.current_tool in ['brush', 'eraser', 'pen'] and self.hasPhoto() and not self.eyedropper_mode:
            if self.photo.contains(scene_pos):
                self.drawing_path = QtGui.QPainterPath()
                self.drawing_path.moveTo(scene_pos)
                self.current_path = QtGui.QPainterPath()
                self.current_path.moveTo(scene_pos)
                
                if self.current_tool == 'brush':
                    color = self.inpaint_brush_color
                    size = self.brush_scaled_size
                elif self.current_tool == 'eraser':
                    color = self.inpaint_brush_color # Color doesn't matter for eraser logic, but we need a pen
                    size = self.eraser_scaled_size
                else: # pen
                    color = self.painting_color
                    size = self.pen_scaled_size
                
                self.current_path_item = self._scene.addPath(
                    self.current_path, 
                    QtGui.QPen(color, size, 
                            QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, 
                            QtCore.Qt.RoundJoin)
                )
                apply_brush_stroke_layer(self.current_path_item)
                ensure_text_items_layer(self.text_items)
                
                # Il brush resta nel layer contenuto basso definito in z_layers.py
                if hasattr(self, 'layer_manager') and self.layer_manager:
                    from .layer_manager import LayerType
                    self.layer_manager.add_layer(
                        self.current_path_item,
                        LayerType.BRUSH_STROKE,
                        z_index=BRUSH_STROKE_Z,
                        name=f"brush_stroke_{id(self.current_path_item)}"
                    )

                if self.current_tool == 'eraser':
                    self.before_erase = [pcb.save_path_properties(item) for item in 
                                         self._scene.items() if isinstance(item, QGraphicsPathItem)]

        # Handle rectangle selection (in pan and move modes only, not box mode)
        if self.hasPhoto() and isinstance(clicked_item, (MoveableRectItem, MoveableEllipseItem)) and self.current_tool != 'box':
            self.select_rectangle(clicked_item, add_to_selection=add_to_selection)

        # Handle box tool (selection and creation of rectangles)
        if self.current_tool == 'box' and self.hasPhoto():
            if self.photo.contains(scene_pos):
                if isinstance(clicked_item, (MoveableRectItem, MoveableEllipseItem)):
                    self.select_rectangle(clicked_item, add_to_selection=add_to_selection)
                    super().mousePressEvent(event)
                else:
                    self.box_mode = True
                    self.start_point = scene_pos
                    rect = QtCore.QRectF(0, 0, 0, 0)
                    
                    # Usa la preferenza utente per la forma iniziale
                    use_rectangle = False
                    settings_page = self._find_settings_page()
                    if settings_page:
                        use_rectangle = settings_page.is_rectangle_enabled()
                    
                    if use_rectangle:
                        self.current_rect = MoveableRectItem(rect, self.photo)
                    else:
                        self.current_rect = MoveableEllipseItem(rect, self.photo)
                    
                    self.current_rect.setPos(scene_pos)
                    self.current_rect.setZValue(WORK_SELECTION_Z)
        
        # Handle bucket fill tool
        if self.current_tool == 'bucket' and self.hasPhoto():
            if self.photo.contains(scene_pos):
                self.flood_fill_at(scene_pos)

        # Handle SVG tool
        if self.current_tool == 'svg' and self.hasPhoto():
            if self.photo.contains(scene_pos) and hasattr(self, 'svg_tool') and self.svg_tool:
                self.svg_tool.handle_click(scene_pos)

        # Handle pan tool, move tool and text block interaction
        scroll = self.dragMode() == QtWidgets.QGraphicsView.DragMode.ScrollHandDrag
        if self.current_tool in ['pan', 'move'] or isinstance(clicked_item, (TextBlockItem, MoveableRectItem, MoveableEllipseItem)) or scroll:
            if self.current_tool == 'move':
                if isinstance(clicked_item, TextBlockItem):
                    if not clicked_item.editing_mode:
                        clicked_item.setSelected(True)
                        clicked_item.selected = True
                elif isinstance(clicked_item, (MoveableRectItem, MoveableEllipseItem)):
                    self.select_rectangle(clicked_item, add_to_selection=add_to_selection)
            super().mousePressEvent(event)
            self.drag_handler.capture_if_item_started_drag(clicked_item, scene_pos)
            # Invalida cache quando cambia la selezione
            self.invalidate_sel_rot_cache()



    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if self.drag_handler.is_dragging:
            if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
                # Attiva cache durante drag per evitare iterazioni costose
                self._sel_rot_item_cache_valid = True
                if self.drag_handler.handle_mouse_move(scene_pos):
                    event.accept()
                    return
            else:
                self.drag_handler.end_drag()

        super().mouseMoveEvent(event)
        blk_item, rect_item = self.sel_rot_item()

        if blk_item or rect_item:
            sel_item = blk_item if blk_item else rect_item
            local_pos = sel_item.mapFromScene(scene_pos)
            if sel_item.rotating and sel_item.center_scene_pos:
                sel_item.rotate_item(scene_pos)
                event.accept()
            else:
                buffer = 25
                angle = sel_item.rotation()
                inner_rect = sel_item.boundingRect()
                outer_rect = inner_rect.adjusted(-buffer, -buffer, buffer, buffer)
                cursor = self.get_rotation_cursor(outer_rect, local_pos, angle)
                if cursor:
                    self.viewport().setCursor(cursor)
        
        # Rimossa gestione trascinamento balloon - funzionalità eliminata
            
        if self.panning:
            new_pos = event.position()
            delta = new_pos - self.pan_start_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self.pan_start_pos = new_pos
            event.accept()
            return
        
        if self.current_tool in ['brush', 'eraser', 'pen'] and self.current_path:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self.photo.contains(scene_pos):
                self.current_path.lineTo(scene_pos)
                if self.current_tool in ['brush', 'pen']:
                    self.current_path_item.setPath(self.current_path)
                elif self.current_tool == 'eraser':
                    self.erase_at(scene_pos)

        if self.current_tool == 'box':
            scene_pos = self.mapToScene(event.position().toPoint())
            if self.box_mode:
                end_point = self.constrain_point(scene_pos)
                width = end_point.x() - self.start_point.x()
                height = end_point.y() - self.start_point.y()
                
                # Handle negative dimensions when dragging from right to left or bottom to top
                pos_x = self.start_point.x()
                pos_y = self.start_point.y()
                
                if width < 0:
                    pos_x = end_point.x()
                    width = abs(width)
                    
                if height < 0:
                    pos_y = end_point.y() 
                    height = abs(height)
                    
                # Update rectangle position and dimensions
                self.current_rect.setPos(QtCore.QPointF(pos_x, pos_y))
                self.current_rect.setRect(QtCore.QRectF(0, 0, width, height))

    def mouseReleaseEvent(self, event):
        was_dragging = self.drag_handler.is_dragging
        if was_dragging:
            super().mouseReleaseEvent(event)
        self.drag_handler.end_drag()
        # Invalida cache al rilascio del mouse
        self.invalidate_sel_rot_cache()

        if event.button() == QtCore.Qt.LeftButton:
            # Rimossa gestione balloon - funzionalità eliminata
            
            blk_item, rect_item = self.sel_rot_item()
            sel_item = blk_item if blk_item else rect_item
            if sel_item:
                was_rotating = bool(getattr(sel_item, 'rotating', False)) or bool(getattr(sel_item, 'rot_handle', None))
                sel_item.rotating = False
                sel_item.center_scene_pos = None  
                sel_item.rot_handle = None

                old_state = getattr(sel_item, 'old_state', None)
                if was_rotating and old_state is not None:
                    if isinstance(sel_item, (MoveableRectItem, MoveableEllipseItem)):
                        new_state = RectState.from_item(sel_item)
                        sel_item.signals.change_undo.emit(old_state, new_state)
                    else:
                        new_state = TextBlockState.from_item(sel_item)
                        sel_item.change_undo.emit(old_state, new_state)

        item = self.itemAt(event.pos())
        scroll = self.dragMode() == QtWidgets.QGraphicsView.DragMode.ScrollHandDrag
        if not was_dragging and (self.current_tool == 'pan' or isinstance(item, TextBlockItem) or scroll):
            super().mouseReleaseEvent(event)

        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.panning = False
            self.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        
        if self.current_tool in ['brush', 'eraser', 'pen']:
            if self.current_path_item:
                # Se è la penna, usiamo AdvancedBrushStrokeCommand per salvare le proprietà (o un comando dedicato se cresce)
                if self.current_tool == 'pen':
                    from ..commands.brush import AdvancedBrushStrokeCommand
                    advanced_properties = {
                        'advanced_brush': True, # Lo lasciamo True per riutilizzare la logica di AdvancedBrushStrokeCommand
                        'brush_opacity': self.painting_color.alpha() * 100 // 255,
                        'original_color': self.painting_color.name(QtGui.QColor.HexArgb)
                    }
                    command = AdvancedBrushStrokeCommand(self, self.current_path_item, advanced_properties)
                else:
                    # Usa il comando standard per pennello inpainting e gomma
                    command = BrushStrokeCommand(self, self.current_path_item)
                self.command_emitted.emit(command)
            self.current_path = None
            self.current_path_item = None

            if self.current_tool == 'eraser':
                self.after_erase = [pcb.save_path_properties(item) for item in 
                                         self._scene.items() if isinstance(item, QGraphicsPathItem)]
                command = EraseUndoCommand(self, self.before_erase, self.after_erase)
                self.command_emitted.emit(command)
                self.after_erase = []
                self.before_erase = []

        if self.current_tool == 'box':
            if self.box_mode:
                self.box_mode = False
                if self.current_rect and self.current_rect.rect().width() > 0 and self.current_rect.rect().height() > 0:
                    self.rectangles.append(self.current_rect)
                    self.rectangle_created.emit(self.current_rect)
                else:
                    self._scene.removeItem(self.current_rect)
                self.current_rect = None
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if (
            event.matches(QtGui.QKeySequence.StandardKey.Delete)
            or event.key() in (
                QtCore.Qt.Key.Key_Delete,
                QtCore.Qt.Key.Key_Backspace,
            )
        ):
            parent = self.parent()
            if parent is not None and hasattr(parent, "delete_button") and parent.delete_button.isEnabled():
                parent.delete_button.click()
                event.accept()
                return

        # Gestione frecce per spostare elementi selezionati
        if event.key() in [QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down]:
            step = 1 if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier else 10
            dx = step if event.key() == QtCore.Qt.Key.Key_Right else -step if event.key() == QtCore.Qt.Key.Key_Left else 0
            dy = step if event.key() == QtCore.Qt.Key.Key_Down else -step if event.key() == QtCore.Qt.Key.Key_Up else 0
            delta = QtCore.QPointF(dx, dy)

            # Raccogli tutti gli elementi selezionati: text_items + selected_rect
            items_to_move = [item for item in self.text_items if getattr(item, 'selected', False)]
            if self.selected_rect and self.selected_rect not in items_to_move:
                if isinstance(self.selected_rect, (MoveableRectItem, MoveableEllipseItem)):
                    items_to_move.append(self.selected_rect)

            if items_to_move:
                for item in items_to_move:
                    new_pos = item.pos() + delta

                    # Bounds check rispetto al parent (immagine)
                    if hasattr(item, 'parent_item') and item.parent_item:
                        parent_rect = item.parent_item.boundingRect()
                        bounding_rect = item.mapToScene(item.boundingRect()).boundingRect()

                        if bounding_rect.left() + dx < 0:
                            new_pos.setX(item.pos().x() - bounding_rect.left())
                        elif bounding_rect.right() + dx > parent_rect.width():
                            new_pos.setX(item.pos().x() + parent_rect.width() - bounding_rect.right())

                        if bounding_rect.top() + dy < 0:
                            new_pos.setY(item.pos().y() - bounding_rect.top())
                        elif bounding_rect.bottom() + dy > parent_rect.height():
                            new_pos.setY(item.pos().y() + parent_rect.height() - bounding_rect.bottom())

                    item.setPos(new_pos)

                    # Notifica il cambio per sincronizzare il modello dati
                    if isinstance(item, TextBlockItem):
                        new_rect = QtCore.QRectF(new_pos, item.boundingRect().size())
                        item.item_changed.emit(new_rect, item.rotation(), item.transformOriginPoint())
                        item.update_marker_position()

                event.accept()
                return

        super().keyPressEvent(event)

    def get_rotate_handle(self, rect, pos: QtCore.QPointF, angle):
        handle_size = 30

        # Rotate all four corners
        top_left = rect.topLeft()
        top_right = rect.topRight()
        bottom_left = rect.bottomLeft()
        bottom_right = rect.bottomRight()

        handles = {
            'top_left': QtCore.QRectF(top_left.x() - handle_size/2, top_left.y() - handle_size/2, handle_size, handle_size),
            'top_right': QtCore.QRectF(top_right.x() - handle_size/2, top_right.y() - handle_size/2, handle_size, handle_size),
            'bottom_left': QtCore.QRectF(bottom_left.x() - handle_size/2, bottom_left.y() - handle_size/2, handle_size, handle_size),
            'bottom_right': QtCore.QRectF(bottom_right.x() - handle_size/2, bottom_right.y() - handle_size/2, handle_size, handle_size),
            'top': QtCore.QRectF(top_left.x(), top_left.y() - handle_size/2, rect.width(), handle_size),
            'bottom': QtCore.QRectF(bottom_left.x(), bottom_left.y() - handle_size/2, rect.width(), handle_size),
            'left': QtCore.QRectF(top_left.x() - handle_size/2, top_left.y(), handle_size, rect.height()),
            'right': QtCore.QRectF(top_right.x() - handle_size/2, top_right.y(), handle_size, rect.height()),
        }

        # Check if the pos is within any of the handle rectangles
        for handle, handle_rect in handles.items():
            if handle_rect.contains(pos):
                return handle
        return None

    def get_rotation_cursor(self, outer_rect: QtWidgets.QGraphicsRectItem, pos: QtCore.QPointF, angle):
        handle = self.get_rotate_handle(outer_rect, pos, angle)
        if handle:
            return self.rotate_cursors.get_cursor(handle)
        elif outer_rect.contains(pos):
            return None
        return QtGui.QCursor(QtCore.Qt.ArrowCursor)

    def erase_at(self, pos: QtCore.QPointF):
        erase_path = QtGui.QPainterPath()
        erase_path.addEllipse(pos, self.eraser_scaled_size, self.eraser_scaled_size)

        items = self._scene.items(erase_path)
        for item in items:
            if isinstance(item, QtWidgets.QGraphicsPathItem) and item != self.photo:
                path = item.path()
                new_path = QtGui.QPainterPath()
                element_count = path.elementCount()

                brush_color = QtGui.QColor(item.brush().color().name(QtGui.QColor.HexArgb))
                if brush_color == "#80ff0000":  # generated stroke
                    # Increase precision of eraser path
                    precise_erase_path = QtGui.QPainterPath()
                    for i in range(36):
                        angle = i * 10 * 3.14159 / 180
                        point = QtCore.QPointF(pos.x() + self.eraser_size * math.cos(angle),
                                            pos.y() + self.eraser_size * math.sin(angle))
                        if i == 0:
                            precise_erase_path.moveTo(point)
                        else:
                            precise_erase_path.lineTo(point)
                    precise_erase_path.closeSubpath()

                    items = self._scene.items(erase_path)
                    for item in items:
                        if isinstance(item, QtWidgets.QGraphicsPathItem) and item != self.photo:
                            path = item.path()
                            intersected_path = path.intersected(precise_erase_path)
                            if not intersected_path.isEmpty():
                                new_path = QtGui.QPainterPath(path)
                                new_path = new_path.subtracted(intersected_path)
                                item.setPath(new_path)
                                if new_path.isEmpty():
                                    self._scene.removeItem(item)
                else:
                    # Handle other paths as before
                    i = 0
                    while i < element_count:
                        e = path.elementAt(i)
                        point = QtCore.QPointF(e.x, e.y)
                        element_type = e.type

                        # Check if the point is outside the erase area
                        if not erase_path.contains(point):
                            if element_type == QtGui.QPainterPath.ElementType.MoveToElement:
                                new_path.moveTo(point)
                            elif element_type == QtGui.QPainterPath.ElementType.LineToElement:
                                new_path.lineTo(point)
                            elif element_type == QtGui.QPainterPath.ElementType.CurveToElement:
                                # Handle curves by adding the next two control points
                                if i + 2 < element_count:
                                    c1 = path.elementAt(i + 1)
                                    c2 = path.elementAt(i + 2)
                                    c1_point = QtCore.QPointF(c1.x, c1.y)
                                    c2_point = QtCore.QPointF(c2.x, c2.y)
                                    if not (erase_path.contains(c1_point) or erase_path.contains(c2_point)):
                                        new_path.cubicTo(point, c1_point, c2_point)
                                i += 2  # Skip the control points
                        else:
                            # If the point is within the erase area, start a new subpath if the next point is outside
                            if (i + 1) < element_count:
                                next_element = path.elementAt(i + 1)
                                next_point = QtCore.QPointF(next_element.x, next_element.y)
                                if not erase_path.contains(next_point):
                                    new_path.moveTo(next_point)
                                    if next_element.type == QtGui.QPainterPath.ElementType.CurveToDataElement:
                                        i += 2  # Skip control points
                        i += 1

                    if new_path.isEmpty():
                        self._scene.removeItem(item)
                    else:
                        item.setPath(new_path)

    def save_brush_strokes(self):
        brush_strokes = []
        for item in self._scene.items():
            if isinstance(item, QtWidgets.QGraphicsPathItem):
                brush_strokes.append({
                    'path': item.path(),
                    'pen': item.pen().color().name(QtGui.QColor.HexArgb),  # Save with alpha
                    'brush': item.brush().color().name(QtGui.QColor.HexArgb),  # Save fill color
                    'width': item.pen().width()
                })
        return brush_strokes

    def load_brush_strokes(self, brush_strokes: List[Dict]):
        self.clear_brush_strokes(page_switch=True)
        # Reverse the brush_strokes list
        reversed_brush_strokes = brush_strokes[::-1]
        for stroke in reversed_brush_strokes:
            pen = QtGui.QPen()
            pen.setColor(QtGui.QColor(stroke['pen']))
            pen.setWidth(stroke['width'])
            pen.setStyle(QtCore.Qt.SolidLine)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)

            brush = QtGui.QBrush(QtGui.QColor(stroke['brush']))
            brush_color = QtGui.QColor(stroke['brush'])
            if brush_color == "#80ff0000": # generated 
                path_item = self._scene.addPath(stroke['path'], pen, brush)
            else:
                path_item = self._scene.addPath(stroke['path'], pen)
            apply_brush_stroke_layer(path_item)
        ensure_text_items_layer(self.text_items)

    def clear_brush_strokes(self, page_switch=False):
        if page_switch:
            items_to_remove = []
            for item in self._scene.items():
                if isinstance(item, QtWidgets.QGraphicsPathItem) and item != self.photo:
                    items_to_remove.append(item)
            
            for item in items_to_remove:
                self._scene.removeItem(item)
            self._scene.update()
        else:
            command = ClearBrushStrokesCommand(self)
            self.command_emitted.emit(command)

    def constrain_point(self, point: QtCore.QPointF):
        return QtCore.QPointF(
            max(0, min(point.x(), self.photo.pixmap().width())),
            max(0, min(point.y(), self.photo.pixmap().height()))
        )

    def select_rectangle(self, rect, add_to_selection: bool = False):
        self._prune_invalid_rectangles()
        if not add_to_selection:
            self.deselect_all()
        
        if rect and is_live_graphics_item(rect, self._scene):
            # Se add_to_selection è attivo e il rettangolo è già selezionato, lo deselezioniamo (toggle)
            if add_to_selection and rect.selected:
                self.deselect_rect(rect)
            else:
                rect.selected = True
                rect.setBrush(QtGui.QBrush(QtGui.QColor(255, 0, 0, 100)))  # Rosso trasparente
                if getattr(rect, 'polygon_overlay', None):
                    rect.polygon_overlay.set_selected(True)
                if not add_to_selection:
                    self.selected_rect = rect
                
                srect = rect.mapRectToScene(rect.rect())
                self.rectangle_selected.emit(srect)

    def deselect_rect(self, rect):
        if not is_live_graphics_item(rect, self._scene):
            if self.selected_rect == rect:
                self.selected_rect = None
            return
        rect.setBrush(QtGui.QBrush(QtGui.QColor(255, 192, 203, 125)))  # Rosa trasparente
        rect.selected = False
        if getattr(rect, 'polygon_overlay', None):
            rect.polygon_overlay.set_selected(False)
        if self.selected_rect == rect:
            self.selected_rect = None

    def deselect_all(self):
        self._prune_invalid_rectangles()
        for rect in self.rectangles:
            self.deselect_rect(rect)
        for txt_item in self.text_items:
            txt_item.handleDeselection()
        self.selected_rect = None
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

    def _prune_invalid_rectangles(self):
        valid_rects, removed = prune_graphics_items(self.rectangles, scene=self._scene)
        if removed:
            self.rectangles = valid_rects
        if not is_live_graphics_item(self.selected_rect, self._scene):
            self.selected_rect = None

    def get_cv2_image(self, paint_all=False):
        """Get the currently loaded image as a cv2 image, including text blocks and all scene items."""
        if self.photo.pixmap() is None:
            return None

        if paint_all:
            # Create a high-resolution QImage
            scale_factor = 2  # Increase this for higher resolution
            pixmap = self.photo.pixmap()
            original_size = pixmap.size()
            scaled_size = original_size * scale_factor
            
            qimage = QtGui.QImage(scaled_size, QtGui.QImage.Format_ARGB32)
            qimage.fill(QtCore.Qt.transparent)

            # Create a QPainter with antialiasing
            painter = QtGui.QPainter(qimage)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)

            # Save the current view's transformation
            original_transform = self._scene.views()[0].transform()

            # Reset the transformation to identity (no zoom, no pan)
            self._scene.views()[0].resetTransform()

            # Set the sceneRect to cover the entire image
            self._scene.setSceneRect(0, 0, original_size.width(), original_size.height())

            # Render the scene
            # Hide rectangles and other UI elements before rendering
            hidden_items = []
            overlay = getattr(self, "_original_overlay", None)
            if overlay is not None:
                try:
                    if overlay.scene() is self._scene and overlay.isVisible():
                        overlay.setVisible(False)
                        hidden_items.append(overlay)
                except (RuntimeError, AttributeError):
                    pass
            for item in self.rectangles:
                if item.isVisible():
                    item.setVisible(False)
                    hidden_items.append(item)
            
            if hasattr(self, 'selected_rect') and self.selected_rect and self.selected_rect.isVisible():
                self.selected_rect.setVisible(False)
                hidden_items.append(self.selected_rect)

            self._scene.render(painter)
            painter.end()

            # Restore visibility of hidden items
            for item in hidden_items:
                item.setVisible(True)

            # Scale down the image to the original size
            qimage = qimage.scaled(original_size, 
                                QtCore.Qt.AspectRatioMode.KeepAspectRatio, 
                                QtCore.Qt.TransformationMode.SmoothTransformation)

            # Restore the original transformation
            self._scene.views()[0].setTransform(original_transform)
        else:
            qimage = self.photo.pixmap().toImage()

        # Convert QImage to cv2 image
        qimage = qimage.convertToFormat(QtGui.QImage.Format.Format_RGB888)
        width = qimage.width()
        height = qimage.height()
        bytes_per_line = qimage.bytesPerLine()

        byte_count = qimage.sizeInBytes()
        expected_size = height * bytes_per_line  # bytes per line can include padding

        if byte_count != expected_size:
            print(f"QImage sizeInBytes: {byte_count}, Expected size: {expected_size}")
            print(f"Image dimensions: ({width}, {height}), Format: {qimage.format()}")
            raise ValueError(f"Byte count mismatch: got {byte_count} but expected {expected_size}")

        ptr = qimage.bits()

        # Convert memoryview to a numpy array considering the complete data with padding
        arr = np.array(ptr).reshape((height, bytes_per_line))
        # Exclude the padding bytes, keeping only the relevant image data
        arr = arr[:, :width * 3]
        # Reshape to the correct dimensions without the padding bytes
        arr = arr.reshape((height, width, 3))

        return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    
    def qimage_from_cv2(self, cv2_img: np.ndarray):
        height, width, channel = cv2_img.shape
        bytes_per_line = 3 * width
        qimage = QtGui.QImage(cv2_img.data, width, height, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        return qimage
    
    def display_cv2_image(self, cv2_img: np.ndarray):
        qimage = self.qimage_from_cv2(cv2_img)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self.clear_scene()
        self.setPhoto(pixmap)

    def show_original_overlay(self, cv2_rgb_img: np.ndarray):
        """Mostra l'immagine originale sopra il layer attuale (preview non distruttiva)."""
        self.hide_original_overlay()
        if cv2_rgb_img is None or not self.hasPhoto():
            return False
        try:
            qimage = self.qimage_from_cv2(cv2_rgb_img)
            pixmap = QtGui.QPixmap.fromImage(qimage)
            if pixmap.isNull():
                return False
            self._paint_original_label(pixmap)
            overlay = QtWidgets.QGraphicsPixmapItem()
            overlay.setShapeMode(QtWidgets.QGraphicsPixmapItem.BoundingRectShape)
            overlay.setPixmap(pixmap)
            overlay.setPos(0, 0)
            overlay.setZValue(1000.0)
            overlay.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
            overlay.setAcceptHoverEvents(False)
            overlay.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            overlay.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            overlay.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
            self._scene.addItem(overlay)
            self._original_overlay = overlay
            return True
        except Exception as e:
            print(f"Error in show_original_overlay: {str(e)}")
            return False

    @staticmethod
    def _paint_original_label(pixmap: QtGui.QPixmap):
        """Disegna il tag 'ORIGINAL' in alto a destra sul pixmap di preview."""
        text = "ORIGINAL"
        margin = max(8, int(pixmap.width() * 0.01))
        font_size = max(14, int(pixmap.height() * 0.03))
        font = QtGui.QFont("Arial", font_size, QtGui.QFont.Weight.Bold)
        painter = QtGui.QPainter(pixmap)
        try:
            painter.setFont(font)
            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(text)
            text_h = metrics.height()
            box = QtCore.QRect(
                pixmap.width() - text_w - margin * 3,
                margin,
                text_w + margin * 2,
                text_h + margin,
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(176, 48, 48, 220))
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QtGui.QColor(255, 255, 255))
            painter.drawText(box, QtCore.Qt.AlignmentFlag.AlignCenter, text)
        finally:
            painter.end()

    def hide_original_overlay(self):
        overlay = getattr(self, "_original_overlay", None)
        if overlay is not None:
            try:
                if overlay.scene() is self._scene:
                    self._scene.removeItem(overlay)
            except (RuntimeError, AttributeError):
                pass
            self._original_overlay = None

    def is_showing_original_overlay(self):
        overlay = getattr(self, "_original_overlay", None)
        if overlay is None:
            return False
        try:
            return overlay.scene() is self._scene
        except (RuntimeError, AttributeError):
            self._original_overlay = None
            return False

    def clear_scene(self):
        # _scene.clear() DISTRUGGE anche self.photo. Senza azzerare photo/empty
        # l'attributo Python restava appeso a memoria liberata: hasPhoto()
        # continuava a restituire True e il primo self.photo.pixmap() lanciava
        # "RuntimeError: Internal C++ object ... already deleted".
        self._scene.clear()
        self._original_overlay = None
        self.photo = None
        self.empty = True
        self.selected_rect = None
        self.rectangles = []
        self.polygon_overlays = []
        self.text_items = []
        for attr in ("text_item_markers", "rect_item_markers"):
            try:
                getattr(self, attr).clear()
            except Exception:
                pass

    def clear_rectangles(self, page_switch=False):
        if page_switch:
            for rect in self.rectangles:
                remove_polygon_overlay(rect, self)
                self._scene.removeItem(rect)
            self.rectangles.clear()
            self.selected_rect = None
            self.clear_rect_item_markers()
        else:
            command = ClearRectsCommand(self)
            self.command_emitted.emit(command)

    def clear_text_items(self, delete=True):
        """Pulizia migliorata dei text_items"""
        print(f"[DEBUG] Pulizia {len(self.text_items)} text_items, delete={delete}")
        
        for item in self.text_items:
            if item and item.scene():
                try:
                    if delete:
                        item.scene().removeItem(item)
                        item.deleteLater()
                except Exception as e:
                    print(f"[WARNING] Errore nella rimozione text_item: {str(e)}")
        
        self.text_items.clear()
        self.clear_text_item_markers()
        
        # Pulisci anche il dizionario del controller
        try:
            from controller import ComicTranslate
            controller = self.parent()
            while controller and not isinstance(controller, ComicTranslate):
                controller = controller.parent()
            
            if controller and hasattr(controller, 'text_items'):
                controller.text_items.clear()
                print(f"[DEBUG] Pulito anche dizionario controller.text_items")
        except ImportError:
            pass
    
    def clear_text_item_markers(self):
        """Rimuove tutti i marker dei text item"""
        from shiboken6 import isValid
        for text_item in getattr(self, "text_items", []):
            try:
                if text_item and isValid(text_item):
                    text_item.set_marker(None)
            except RuntimeError:
                pass
        for marker in self.text_item_markers:
            try:
                if not marker or not isValid(marker):
                    continue
                scene = marker.scene()
            except RuntimeError:
                continue
            if scene:
                try:
                    scene.removeItem(marker)
                except Exception as e:
                    print(f"[WARNING] Errore nella rimozione marker: {str(e)}")
        self.text_item_markers.clear()
    
    def update_text_item_markers(self, font_size=10):
        """Aggiorna i marker numerici per tutti i text items.

        Il parametro ``font_size`` è mantenuto per retro-compatibilità
        con i caller esistenti, ma viene ignorato: la dimensione dei
        marker è ora calcolata come frazione fissa della pagina
        caricata (``self._current_page_size``), in modo che non cresca
        ad ogni resize del text block.
        """
        # Pulisci i marker esistenti
        self.clear_text_item_markers()

        page_size = self._current_page_size

        # Crea nuovi marker per ogni text item
        for i, text_item in enumerate(self.text_items):
            try:
                from shiboken6 import isValid
                if not text_item or not isValid(text_item):
                    continue
            except RuntimeError:
                continue

            # I marker stanno in un layer UI dedicato sopra il contenuto.
            marker = TextBoxMarker(i + 1, page_size=page_size)
            marker.setZValue(MARKER_LAYER_DEFAULT)
            self._scene.addItem(marker)
            text_item.set_marker(marker)
            self.text_item_markers.append(marker)

    def clear_rect_item_markers(self):
        """Rimuove tutti i marker dei rect items"""
        from shiboken6 import isValid
        for marker in self.rect_item_markers:
            try:
                if not marker or not isValid(marker):
                    continue
                scene = marker.scene()
            except RuntimeError:
                continue
            if scene:
                try:
                    scene.removeItem(marker)
                except Exception as e:
                    print(f"[WARNING] Errore nella rimozione rect marker: {str(e)}")
        self.rect_item_markers.clear()

    def update_rect_item_markers(self, font_size=10):
        """Aggiorna i marker numerici per tutti i rect items.

        Il parametro ``font_size`` è mantenuto per retro-compatibilità
        con i caller esistenti, ma viene ignorato: la dimensione dei
        marker è ora calcolata come frazione fissa della pagina
        caricata (``self._current_page_size``).
        """
        # Pulisci i marker esistenti
        self.clear_rect_item_markers()

        page_size = self._current_page_size

        # Crea nuovi marker per ogni rect item
        for i, rect_item in enumerate(self.rectangles):
            # I marker stanno in un layer UI dedicato sopra il contenuto.
            marker = TextBoxMarker(i + 1, page_size=page_size)
            marker.setZValue(MARKER_LAYER_DEFAULT)
            self._scene.addItem(marker)
            # Crucial: connect the marker to the rect_item so it updates on move
            rect_item.set_marker(marker)
            self.rect_item_markers.append(marker)

    def update_all_markers(self, font_size=10):
        """Aggiorna tutti i marker (rect items e text items).

        ``font_size`` è mantenuto per retro-compatibilità ma ignorato:
        la dimensione dei marker dipende solo dalla dimensione in pixel
        della pagina caricata (vedi ``self._current_page_size``).
        """
        if not getattr(self, "markers_visible", True):
            self.clear_text_item_markers()
            self.clear_rect_item_markers()
            return

        # Aggiorna entrambi i tipi di marker se presenti
        self.update_text_item_markers(font_size)
        self.update_rect_item_markers(font_size)

    def renumber_incremental_markers(self):
        """Rinumera i marker esistenti SENZA rimuoverli/ricrearli.

        È molto più veloce di ``update_all_markers`` perché chiama solo
        ``set_number()`` sui marker già presenti in scena, evitando
        decine di ``addItem`` / ``removeItem`` che causano repaint.
        """
        if not getattr(self, "markers_visible", True):
            return

        page_size = self._current_page_size

        # -- text item markers --
        # Allinea la lista ai text_items attuali (può averne persi uno)
        valid_tm = [m for m in self.text_item_markers
                    if m is not None and m.scene() is not None]
        self.text_item_markers = valid_tm

        # Se il numero di marker non corrisponde ai text_items,
        # serve un rebuild completo (aggiunto/rimosso un item).
        if len(valid_tm) != len(self.text_items):
            self.update_text_item_markers()
        else:
            for i, marker in enumerate(valid_tm):
                marker.set_number(i + 1)
                # Aggiorna posizione nel caso l'item sia stato spostato
                tracked = getattr(marker, '_tracked_item', None)
                if tracked is not None:
                    try:
                        from shiboken6 import isValid
                        if isValid(tracked):
                            marker.update_position_relative_to_item(tracked)
                    except RuntimeError:
                        pass

        # -- rect item markers --
        valid_rm = [m for m in self.rect_item_markers
                    if m is not None and m.scene() is not None]
        self.rect_item_markers = valid_rm

        if len(valid_rm) != len(self.rectangles):
            self.update_rect_item_markers()
        else:
            for i, marker in enumerate(valid_rm):
                marker.set_number(i + 1)
                tracked = getattr(marker, '_tracked_item', None)
                if tracked is not None:
                    try:
                        from shiboken6 import isValid
                        if isValid(tracked):
                            marker.update_position_relative_to_item(tracked)
                    except RuntimeError:
                        pass

    def set_markers_visible(self, visible: bool, font_size: int = 10):
        self.markers_visible = bool(visible)
        if self.markers_visible:
            self.update_all_markers(font_size=font_size)
        else:
            self.clear_text_item_markers()
            self.clear_rect_item_markers()

    def set_text_boxes_visible(self, visible: bool) -> bool:
        """Mostra/nasconde le caselle di testo create da 'Traduci Tutto'.

        Returns ``True`` se l'operazione ha avuto effetto su almeno un text item,
        ``False`` altrimenti.
        """
        from shiboken6 import isValid
        self.text_boxes_hidden = not bool(visible)
        any_changed = False
        for text_item in getattr(self, "text_items", []):
            try:
                if not text_item or not isValid(text_item):
                    continue
            except RuntimeError:
                continue
            text_item.setVisible(bool(visible))
            any_changed = True
        return any_changed

    def set_polygons_visible(self, visible: bool):
        """Mostra/nasconde gli overlay poligonali. Nascosti = non cliccabili."""
        self.polygons_visible = bool(visible)
        for overlay in list(getattr(self, "polygon_overlays", []) or []):
            try:
                overlay.setVisible(bool(visible))
            except (RuntimeError, AttributeError):
                continue

    def set_rect_boxes_visible(self, visible: bool):
        """Mostra/nasconde le caselle di testo dell'OCR (box rilevamento)."""
        self.rect_boxes_visible = bool(visible)
        for rect in list(getattr(self, "rectangles", []) or []):
            try:
                rect.setVisible(bool(visible))
            except (RuntimeError, AttributeError):
                continue

    def setPhoto(self, pixmap: QtGui.QPixmap = None):
        if pixmap and not pixmap.isNull():
            if self.photo is not None:
                try:
                    if self.photo.scene():
                        self._scene.removeItem(self.photo)
                except RuntimeError:
                    pass
            self.photo = None
            self.photo = QtWidgets.QGraphicsPixmapItem()
            self.photo.setShapeMode(QtWidgets.QGraphicsPixmapItem.BoundingRectShape)
            self._scene.addItem(self.photo)

            self.empty = False
            self.photo.setPixmap(pixmap)
            # Remember the page size in pixels; the text-box markers use
            # this to size themselves as a fraction of the loaded page.
            self._current_page_size = QtCore.QSizeF(
                float(pixmap.width()), float(pixmap.height())
            )
            if self.fit_mode == 1:
                self.fit_to_width()
            elif self.fit_mode == 2:
                self.fitInView()
            else:
                self.fit_to_height()
        else:
            self.empty = True
            self._current_page_size = QtCore.QSizeF()
        self.zoom = 0

    def has_drawn_elements(self):
        for item in self._scene.items():
            if isinstance(item, QtWidgets.QGraphicsPathItem):
                if item != self.photo:
                    return True
        return False

    def generate_mask_from_selections(self):
        if not self.hasPhoto():
            return None

        image_rect = self.photo.boundingRect()
        width = int(image_rect.width())
        height = int(image_rect.height())

        mask = np.zeros((height, width), dtype=np.uint8)

        from modules.utils.ellipse_mask import EllipseMaskGenerator

        for item in self._scene.items():
            if isinstance(item, (MoveableRectItem, MoveableEllipseItem)):
                # Solo le caselle SELEZIONATE: la condizione era
                # 'item.selected or True', che annullava il filtro e metteva
                # nella maschera EVERY casella della pagina, cancellando
                # anche zone di disegno che non andavano toccate.
                if item.selected:
                    scene_rect = item.mapRectToScene(item.rect())
                    x1 = scene_rect.x()
                    y1 = scene_rect.y()
                    x2 = scene_rect.x() + scene_rect.width()
                    y2 = scene_rect.y() + scene_rect.height()

                    rotation = item.rotation()
                    center = ((x1 + x2) / 2, (y1 + y2) / 2)
                    axes = ((x2 - x1) / 2, (y2 - y1) / 2)

                    if isinstance(item, MoveableEllipseItem):
                        mask = EllipseMaskGenerator.add_ellipse_to_mask(
                            mask, center, axes,
                            angle=rotation,
                            value=255,
                            soft_edge=True,
                            border_width=2
                        )
                    else:
                        angle_rad = np.deg2rad(rotation)
                        cos_a = np.cos(angle_rad)
                        sin_a = np.sin(angle_rad)

                        corners = np.array([
                            [x1, y1], [x2, y1], [x2, y2], [x1, y2]
                        ])
                        cx, cy = center
                        for i in range(len(corners)):
                            dx = corners[i][0] - cx
                            dy = corners[i][1] - cy
                            corners[i][0] = cos_a * dx - sin_a * dy + cx
                            corners[i][1] = sin_a * dx + cos_a * dy + cy

                        pts = corners.astype(np.int32)
                        cv2.fillConvexPoly(mask, pts, 255)

        return mask

    def generate_mask_from_strokes(self):
        if not self.hasPhoto():
            return None

        # Get the size of the image
        image_rect = self.photo.boundingRect()
        width = int(image_rect.width())
        height = int(image_rect.height())

        # Create two blank masks
        human_mask = np.zeros((height, width), dtype=np.uint8)
        generated_mask = np.zeros((height, width), dtype=np.uint8)

        # Create two QImages to draw paths separately
        human_qimage = QtGui.QImage(width, height, QtGui.QImage.Format_Grayscale8)
        generated_qimage = QtGui.QImage(width, height, QtGui.QImage.Format_Grayscale8)
        human_qimage.fill(QtGui.QColor(0, 0, 0))
        generated_qimage.fill(QtGui.QColor(0, 0, 0))

        # Create QPainters for both QImages
        human_painter = QtGui.QPainter(human_qimage)
        generated_painter = QtGui.QPainter(generated_qimage)
        
        hum_pen = QtGui.QPen(QtGui.QColor(255, 255, 255), self.brush_size)
        gen_pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 2, QtCore.Qt.SolidLine)

        human_painter.setPen(hum_pen)
        generated_painter.setPen(gen_pen)
        
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        human_painter.setBrush(brush)
        generated_painter.setBrush(brush)

        # Iterate through all items in the scene
        for item in self._scene.items():
            if isinstance(item, QtWidgets.QGraphicsPathItem) and item != self.photo:
                brush_color = QtGui.QColor(item.brush().color().name(QtGui.QColor.HexArgb))
                if brush_color == "#80ff0000":  # generated stroke
                    generated_painter.drawPath(item.path())
                else:  # human-drawn stroke
                    human_painter.drawPath(item.path())

        # End painting
        human_painter.end()
        generated_painter.end()

        # Convert the QImages to numpy arrays, accounting for padding
        bytes_per_line = human_qimage.bytesPerLine()
        human_ptr = human_qimage.constBits()
        generated_ptr = generated_qimage.constBits()
        human_arr = np.array(human_ptr).reshape(height, bytes_per_line)
        generated_arr = np.array(generated_ptr).reshape(height, bytes_per_line)
        
        # Exclude the padding bytes, keeping only the relevant image data
        human_mask = human_arr[:, :width]
        generated_mask = generated_arr[:, :width]

        kernel = np.ones((5,5), np.uint8)
        human_mask = cv2.dilate(human_mask, kernel, iterations=2)
        generated_mask = cv2.dilate(generated_mask, kernel, iterations=3)

        # Combine the masks
        final_mask = cv2.bitwise_or(human_mask, generated_mask)

        return final_mask

    def get_mask_for_inpainting(self):
        cv2_image = self.get_cv2_image()
        if cv2_image is None:
            return None

        height, width = cv2_image.shape[:2]
        final_mask = np.zeros((height, width), dtype=np.uint8)

        selection_mask = self.generate_mask_from_selections()
        if selection_mask is not None:
            selection_mask = cv2.resize(selection_mask, (width, height))
            final_mask = cv2.bitwise_or(final_mask, selection_mask)

        stroke_mask = self.generate_mask_from_strokes()
        if stroke_mask is not None:
            stroke_mask = cv2.resize(stroke_mask, (width, height))
            final_mask = cv2.bitwise_or(final_mask, stroke_mask)

        if np.sum(final_mask) == 0:
            return None

        return final_mask

    def draw_segmentation_lines(self, bboxes, layers: int = 1, scale_factor: float = 1.0):
        if not self.hasPhoto():
            print("No photo loaded.")
            return

        if bboxes is None or len(bboxes) == 0:
            return

        # Calculate the centroid of all points
        all_points = np.array(bboxes).reshape(-1, 2)
        centroid = np.mean(all_points, axis=0)

        # Scale the line segments towards the centroid
        scaled_segments = []
        for x1, y1, x2, y2 in bboxes:
            scaled_p1 = (np.array([x1, y1]) - centroid) * scale_factor + centroid
            scaled_p2 = (np.array([x2, y2]) - centroid) * scale_factor + centroid
            scaled_segments.append((scaled_p1[0], scaled_p1[1], scaled_p2[0], scaled_p2[1]))

        # Create rectangles for each line segment
        fill_color = QtGui.QColor(255, 0, 0, 128)  # Semi-transparent red
        outline_color = QtGui.QColor(255, 0, 0)  # Solid red for the outline

        boxes = []
        for _ in range(layers):
            for x1, y1, x2, y2 in scaled_segments:
                path = QtGui.QPainterPath()
                path.addRect(QtCore.QRectF(x1, y1, x2 - x1, y2 - y1))
                
                path_item = QtWidgets.QGraphicsPathItem(path)
                path_item.setPen(QtGui.QPen(outline_color, 2, QtCore.Qt.SolidLine))
                path_item.setBrush(QtGui.QBrush(fill_color))
                boxes.append(path_item)

        command = SegmentBoxesCommand(self, boxes)
        self.command_emitted.emit(command)

        # # Ensure the rectangles are visible
        # self._scene.update()

    def load_state(self, state: Dict, show_overlays: bool = True):
        # Rispetta lo stato "Hide text boxes" salvato per l'immagine corrente.
        self.text_boxes_hidden = bool(state.get('text_boxes_hidden', False))
        # Gestisci il caso in cui 'transform' potrebbe essere mancante
        if 'transform' in state:
            self.setTransform(QtGui.QTransform(*state['transform']))
        else:
            # Usa una trasformazione identità come fallback
            self.setTransform(QtGui.QTransform())
        
        # Gestisci il caso in cui 'center' potrebbe essere mancante
        if 'center' in state:
            self.centerOn(QtCore.QPointF(*state['center']))
        else:
            # Centra sulla scena corrente
            self.centerOn(self.sceneRect().center())
        
        # Gestisci il caso in cui 'scene_rect' potrebbe essere mancante
        if 'scene_rect' in state:
            self.setSceneRect(QtCore.QRectF(*state['scene_rect']))
        # Se scene_rect non è presente, mantieni quello corrente
        
        # Carica i rettangoli se presenti
        for rect_data in state.get('rectangles', []):
            x1, y1, width, height = rect_data['rect']
            rect = QtCore.QRectF(0, 0, width, height)
            
            # Determina il tipo di forma (rettangolo o ellisse)
            is_rectangle = rect_data.get('is_rectangle', True)
            if is_rectangle:
                rect_item = MoveableRectItem(rect, self.photo)
            else:
                rect_item = MoveableEllipseItem(rect, self.photo)
            
            # Set transform origin point first
            if 'transform_origin' in rect_data:
                rect_item.setTransformOriginPoint(
                    QtCore.QPointF(*rect_data['transform_origin'])
                )
            
            # Set position and rotation
            rect_item.setPos(x1, y1)
            rect_item.setRotation(rect_data['rotation'])
            rect_item.setVisible(bool(rect_data.get('visible', show_overlays))
                                 and getattr(self, 'rect_boxes_visible', True))
            rect_item.setEnabled(bool(rect_data.get('enabled', True)))
            rect_item.setZValue(float(rect_data.get('z_value', rect_item.zValue())))
            
            # CORREZIONE: Aggiungi il rettangolo alla scena grafica - RIMOSSO perché già aggiunto tramite parent
            # self._scene.addItem(rect_item)
            if not show_overlays:
                rect_item.setVisible(False)
            self.rectangles.append(rect_item)
        
        # Recreate text block items
        for text_block in state.get('text_items_state', []):
            outline_enabled = outline_enabled_from_data(text_block)
            text_item = TextBlockItem(
                text=text_block['text'],
                parent_item= self.photo,
                font_family=text_block['font_family'],
                font_size=text_block['font_size'],
                render_color=text_block['text_color'],
                alignment=text_block['alignment'],
                line_spacing=text_block['line_spacing'],
                outline_color=outline_color_for_loading(text_block, None),
                outline_width=text_block['outline_width'] if outline_enabled else 0,
                bold=text_block['bold'],
                italic=text_block['italic'],
                underline=text_block['underline'],
                outline_enabled=outline_enabled,
            )
            text_item.detected_text_color = text_block.get('detected_text_color', '') or ''
            text_item.detected_text_color_data = text_block.get('detected_text_color_data', None)
            if 'width' in text_block:
                text_item.set_text(text_block['text'], text_block['width'])
            elif 'block' in text_block:
                x, y, w, h = text_block['block'].xywh
                text_item.set_text(text_block['text'], w)

            if 'direction' in text_block:
                text_item.set_direction(text_block['direction'])

            if 'transform_origin' in text_block and text_block['transform_origin']:
                text_item.setTransformOriginPoint(QtCore.QPointF(*text_block['transform_origin']))
            text_item.setPos(QtCore.QPointF(*text_block['position']))
            text_item.setRotation(text_block['rotation'])
            text_item.setScale(text_block['scale'])
            text_item.selection_outlines = text_block['selection_outlines']
            text_item.update()

            self._scene.addItem(text_item)
            apply_text_box_layer(text_item)
            self.text_items.append(text_item)
            if state.get('text_boxes_hidden', False):
                text_item.setVisible(False)
            
            # Il testo usa il layer contenuto definito in z_layers.py
            if hasattr(self, 'layer_manager') and self.layer_manager:
                from .layer_manager import LayerType
                self.layer_manager.add_layer(
                    text_item,
                    LayerType.TEXT_BOX,
                    z_index=TEXT_BOX_Z,
                    name=f"text_box_{id(text_item)}"
                )  
        if show_overlays and getattr(self, "markers_visible", True):
            self.update_all_markers()
        else:
            self.clear_text_item_markers()
            self.clear_rect_item_markers()

    def save_state(self):
        transform = self.transform()
        center = self.mapToScene(self.viewport().rect().center())

        rectangles_state = []
        for rect in self.rectangles:
            # Get the rectangle's scene coordinates
            x1 = rect.pos().x()
            y1 = rect.pos().y()
            width = rect.boundingRect().width() 
            height = rect.boundingRect().height() 
            
            # Salva il tipo di forma (rettangolo o ellisse)
            is_rectangle = isinstance(rect, MoveableRectItem)
            
            rectangles_state.append({
                'rect': (x1, y1, width, height),
                'rotation': rect.rotation(),
                'is_rectangle': is_rectangle,
                'visible': rect.isVisible(),
                'enabled': rect.isEnabled(),
                'z_value': float(rect.zValue()),
                'transform_origin': (
                    rect.transformOriginPoint().x(),
                    rect.transformOriginPoint().y()
                )
            })

        text_items_state = []
        for item in self.text_items:
            detected_text_color = getattr(item, "detected_text_color", "") or ""
            effective_text_color = item.text_color.name() if hasattr(item.text_color, "name") else str(item.text_color)
            user_text_color_override = ""
            if detected_text_color and effective_text_color and detected_text_color.lower() != effective_text_color.lower():
                user_text_color_override = effective_text_color
            text_items_state.append({
                'text': item.toHtml(),
                'font_family': item.font_family,
                'font_size': item.font_size,
                'text_color': item.text_color,
                'detected_text_color': detected_text_color,
                'detected_text_color_data': getattr(item, "detected_text_color_data", None),
                'user_text_color_override': user_text_color_override,
                'alignment': item.alignment,
                'line_spacing': item.line_spacing,
                'outline': item.outline,
                'outline_color': item.outline_color,
                'outline_width': item.outline_width,
                'bold': item.bold,
                'italic': item.italic,
                'underline': item.underline,
                'position': (item.pos().x(), item.pos().y()),
                'rotation': item.rotation(),
                'scale': item.scale(),
                'transform_origin': (item.transformOriginPoint().x(), 
                                     item.transformOriginPoint().y()),
                'width': item.boundingRect().width(),
                'selection_outlines': item.selection_outlines,
                'direction': item.direction
            })

        return {
            'rectangles': rectangles_state,
            'transform': (
                transform.m11(), transform.m12(), transform.m13(),
                transform.m21(), transform.m22(), transform.m23(),
                transform.m31(), transform.m32(), transform.m33()
            ),
            'center': (center.x(), center.y()),
            'scene_rect': (self.sceneRect().x(), self.sceneRect().y(), 
                        self.sceneRect().width(), self.sceneRect().height()),
            'text_items_state': text_items_state,
            'text_boxes_hidden': bool(getattr(self, 'text_boxes_hidden', False)),
        }

    def create_inpaint_cursor(self, cursor_type, size):
        from PySide6.QtGui import QPixmap, QPainter, QBrush, QColor, QCursor, QPen
        from PySide6.QtCore import Qt

        # Ensure size is at least 1 pixel
        size = max(1, size)
        
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        if cursor_type == "brush":
            # Cursore pennello inpainting (sempre rosso)
            painter.setBrush(QBrush(QColor(255, 0, 0, 127)))
            painter.setPen(Qt.PenStyle.NoPen)
        elif cursor_type == "pen":
            # Cursore penna (usa painting_color)
            color = QColor(self.painting_color)
            color.setAlpha(127)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor(0, 0, 0, 200), 1))
        elif cursor_type == "eraser":
            painter.setBrush(QBrush(QColor(0, 0, 0, 0)))  # Fully transparent
            painter.setPen(QPen(QColor(0, 0, 0, 127), 2))  # Outline with some transparency
        else:
            painter.setBrush(QBrush(QColor(0, 0, 0, 127)))  # Default to some color if unknown type
            painter.setPen(Qt.PenStyle.NoPen)

        painter.drawEllipse(0, 0, size, size)
        painter.end()

        return QCursor(pixmap, size // 2, size // 2)
    
    def set_br_er_size(self, size, scaled_size, tool_type=None):
        target = tool_type if tool_type else self.current_tool
        
        if target == 'brush':
            self.brush_size = size
            self.brush_scaled_size = scaled_size
            self.brush_cursor = self.create_inpaint_cursor("brush", scaled_size)
            if self.current_tool == 'brush':
                self.setCursor(self.brush_cursor)
        elif target == 'eraser':
            self.eraser_size = size
            self.eraser_scaled_size = scaled_size
            self.eraser_cursor = self.create_inpaint_cursor("eraser", scaled_size)
            if self.current_tool == 'eraser':
                self.setCursor(self.eraser_cursor)
        elif target == 'pen':
            self.pen_size = size
            self.pen_scaled_size = scaled_size
            self.pen_cursor = self.create_inpaint_cursor("pen", scaled_size)
            if self.current_tool == 'pen':
                self.setCursor(self.pen_cursor)
    
    def set_painting_color(self, color: QtGui.QColor):
        """Imposta il colore per Penna e Secchiello."""
        self.painting_color = color
        # Aggiorna il cursore della penna
        self.pen_cursor = self.create_inpaint_cursor("pen", self.pen_scaled_size)
        if self.current_tool == 'pen':
            self.setCursor(self.pen_cursor)
    
    def set_pen_opacity(self, opacity: int):
        """Imposta l'opacità della penna (0-100)."""
        color = QtGui.QColor(self.painting_color)
        color.setAlpha(int(255 * opacity / 100))
        self.painting_color = color
        # Aggiorna il cursore
        self.pen_cursor = self.create_inpaint_cursor("pen", self.pen_scaled_size)
        if self.current_tool == 'pen':
            self.setCursor(self.pen_cursor)
    
    def toggle_eyedropper(self):
        """Attiva/disattiva la modalità eyedropper."""
        self.eyedropper_mode = not self.eyedropper_mode
        if self.eyedropper_mode:
            self.setCursor(self.eyedropper_cursor)
        else:
            if self.current_tool == 'pen':
                self.setCursor(self.pen_cursor)
            elif self.current_tool == 'bucket':
                self.setCursor(QtCore.Qt.CrossCursor)
            elif self.current_tool == 'pan':
                self.setCursor(QtCore.Qt.CrossCursor)
            else:
                self.setCursor(QtCore.Qt.ArrowCursor)
    
    def pick_color_at_position(self, scene_pos: QtCore.QPointF) -> QtGui.QColor:
        """Preleva il colore dall'immagine alla posizione specificata."""
        if not self.hasPhoto() or not self.photo.contains(scene_pos):
            return QtGui.QColor(0, 0, 0)  # Nero di default
        
        # Converte la posizione della scena in coordinate dell'immagine
        local_pos = self.photo.mapFromScene(scene_pos)
        pixmap = self.photo.pixmap()
        
        if pixmap and not pixmap.isNull():
            x = int(local_pos.x())
            y = int(local_pos.y())
            
            # Verifica che le coordinate siano valide
            if 0 <= x < pixmap.width() and 0 <= y < pixmap.height():
                # Converte il pixmap in QImage per leggere il pixel
                image = pixmap.toImage()
                pixel_color = image.pixelColor(x, y)
                
                # Emetti il segnale se siamo in modalità eyedropper
                if self.eyedropper_mode:
                    self.eyedropperColorPicked.emit(pixel_color)
                
                return pixel_color
        
        return QtGui.QColor(0, 0, 0)

    def _get_bucket_controller(self) -> BucketFillUIController:
        """Ottiene o crea il controller per bucket fill asincrono."""
        if self._bucket_controller is None:
            from controller import ComicTranslate
            controller = None
            parent = self.parent()
            while parent and not isinstance(parent, ComicTranslate):
                parent = parent.parent()
            controller = parent

            self._bucket_controller = BucketFillUIController(self, controller)
        return self._bucket_controller

    def flood_fill_at(self, scene_pos: QtCore.QPointF, async_exec: bool = True):
        """Esegue il flood fill (secchiello) sull'immagine alla posizione specificata.

        Args:
            scene_pos: Posizione nella scena dove eseguire il fill
            async_exec: Se True, usa l'esecuzione asincrona non bloccante
        """
        if not self.hasPhoto():
            return

        if async_exec:
            controller = self._get_bucket_controller()
            scheduled = controller.schedule_fill(scene_pos)
            if scheduled:
                return
            else:
                pass

        self._flood_fill_sync(scene_pos)

    def _flood_fill_sync(self, scene_pos: QtCore.QPointF):
        """Esegue flood fill in modo sincrono (bloccante)."""
        old_pixmap = self.photo.pixmap().copy()

        local_pos = self.photo.mapFromScene(scene_pos)
        x = int(local_pos.x())
        y = int(local_pos.y())

        pixmap = self.photo.pixmap()
        if not pixmap or pixmap.isNull():
            return

        if not (0 <= x < pixmap.width() and 0 <= y < pixmap.height()):
            return

        qimage = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_RGB888)
        width = qimage.width()
        height = qimage.height()
        bytes_per_line = qimage.bytesPerLine()
        ptr = qimage.bits()
        arr = np.array(ptr).reshape((height, bytes_per_line))
        arr = arr[:, :width * 3].reshape((height, width, 3)).copy()

        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        fill_color = self.painting_color
        fill_bgr = (fill_color.blue(), fill_color.green(), fill_color.red())

        tol = self.bucket_fill_tolerance
        lo_diff = (tol, tol, tol)
        hi_diff = (tol, tol, tol)

        mask = np.zeros((height + 2, width + 2), np.uint8)

        cv2.floodFill(arr, mask, (x, y), fill_bgr, lo_diff, hi_diff,
                      cv2.FLOODFILL_FIXED_RANGE)

        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)

        new_qimage = QtGui.QImage(arr.data, width, height, width * 3,
                                   QtGui.QImage.Format.Format_RGB888)
        new_pixmap = QtGui.QPixmap.fromImage(new_qimage.copy())

        self.photo.setPixmap(new_pixmap)
        sync_viewer_photo_to_image_data(self)
        self._scene.update()

        command = BucketFillCommand(self, old_pixmap, new_pixmap)
        self.command_emitted.emit(command)

    def sel_rot_item(self):
        # Usa cache durante drag per evitare iterazioni costose su tutti gli item
        if self._sel_rot_item_cache_valid:
            return self._cached_sel_rot_item
        blk_item = next(
            (item for item in self._scene.items() if (
                isinstance(item, TextBlockItem) and item.selected)
            ), None )

        rect_item = next(
            (item for item in self._scene.items() if (
                isinstance(item, (MoveableRectItem, MoveableEllipseItem)) and item.selected)
            ),  None )
        self._cached_sel_rot_item = (blk_item, rect_item)
        return blk_item, rect_item

    def invalidate_sel_rot_cache(self):
        """Invalida la cache quando la selezione cambia."""
        self._sel_rot_item_cache_valid = False

    # Metodo add_shape() rimosso - ora si utilizzano solo SVG
    
    # Metodo select_shape() rimosso - ora si utilizzano solo SVG
    
    def get_max_z_value(self, min_allowed=None, max_allowed=None):
        """Ottiene il valore Z massimo tra gli elementi rilevanti della scena."""
        max_z = 0
        for item in self._scene.items():
            if min_allowed is not None and item.zValue() < min_allowed:
                continue
            if max_allowed is not None and item.zValue() > max_allowed:
                continue
            if item.zValue() > max_z:
                max_z = item.zValue()
        return max_z

    def _selected_shape_items(self):
        """Restituisce gli SVG selezionati."""
        from .svg_item import SvgItem

        selected = []
        for item in self._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                selected.append(item)
        return selected
    
    def bring_shape_to_front(self):
        """Porta la forma importata selezionata in primo piano nel suo range."""
        max_z = self.get_max_z_value(
            min_allowed=IMPORTED_SHAPE_LAYER_MIN,
            max_allowed=IMPORTED_SHAPE_LAYER_MAX,
        )
        target_z = IMPORTED_SHAPE_LAYER_DEFAULT if max_z == 0 else clamp_imported_shape_z(max_z + 0.01)

        for item in self._selected_shape_items():
            item.setZValue(target_z)
    
    def send_shape_to_back(self):
        """Invia la forma importata selezionata in secondo piano nel suo range."""
        for item in self._selected_shape_items():
            current_z = item.zValue()
            item.setZValue(clamp_imported_shape_z(current_z - 0.01))
    
    def set_svg_border_color(self, color):
        """Imposta il colore del bordo per l'SVG selezionato."""
        from .svg_item import SvgItem
        
        self._border_color = color
        
        # Applica solo agli SVG selezionati
        for item in self._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                item.set_border_color(color)
                item.set_show_border(True)  # Abilita automaticamente il bordo
    
    def set_svg_fill_color(self, color):
        """Imposta il colore di riempimento per l'SVG selezionato."""
        from .svg_item import SvgItem
        
        self._fill_color = color
        
        # Applica solo agli SVG selezionati
        for item in self._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                item.set_fill_color(color)
                item.set_show_fill(True)  # Abilita automaticamente il riempimento
    

    

    
    def set_svg_border_width(self, width):
        """Imposta lo spessore del bordo per l'SVG selezionato."""
        from .svg_item import SvgItem
        
        self._border_width = width
        
        # Applica solo agli SVG selezionati
        for item in self._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                item.set_border_width(width)
                item.set_show_border(True)  # Abilita automaticamente il bordo
    
    def delete_selected_svgs(self):
        """Elimina gli SVG attualmente selezionati."""
        from .svg_item import SvgItem
        
        to_remove = []
        for item in self._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                to_remove.append(item)
        
        for item in to_remove:
            print(f"[DEBUG] Eliminazione elemento selezionato: {type(item).__name__}")
            self._scene.removeItem(item)
        
        if to_remove:
            print(f"[DEBUG] Eliminati {len(to_remove)} elementi grafici")
        else:
            print("[DEBUG] Nessun elemento selezionato da eliminare")

    def reset_selected_svg_styles(self):
        """Ripristina gli stili originali per gli SVG selezionati."""
        from .svg_item import SvgItem
        
        reset_count = 0
        for item in self._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                item.reset_styles()
                reset_count += 1
        
        if reset_count > 0:
            print(f"[DEBUG] Ripristinati gli stili per {reset_count} SVG selezionati")
        else:
            print("[DEBUG] Nessun SVG selezionato per il reset degli stili")


    
    def get_selected_rectangles(self):
        """Restituisce tutti i rettangoli attualmente selezionati"""
        return [rect for rect in self.rectangles if hasattr(rect, 'selected') and rect.selected]
    
    def get_selected_shapes(self):
        """Compatibilità: restituisce gli SVG selezionati."""
        return self.get_selected_svg_items()
    
    # Metodi per la gestione delle funzionalità SVG avanzate rimossi
    
    def get_selected_svg_items(self):
        """Restituisce tutti gli elementi SVG attualmente selezionati"""
        from .svg_item import SvgItem
        selected_svgs = []
        for item in self._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                selected_svgs.append(item)
        return selected_svgs
