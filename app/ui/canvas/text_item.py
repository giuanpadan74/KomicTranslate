from PySide6.QtWidgets import QGraphicsTextItem, QGraphicsItem, QGraphicsEllipseItem
from PySide6.QtGui import QFont, QCursor, QColor, QPen, QBrush, \
     QTextCharFormat, QTextBlockFormat, QTextCursor
from PySide6.QtCore import Qt, QRectF, Signal, QPointF
import math, copy
from dataclasses import dataclass
from enum import Enum
import json

from .text_box_marker import TextBoxMarker
from .layer_preserve import LayerPreserveManager, LayerOperation
from .z_layers import HANDLE_LAYER_DEFAULT

@dataclass
class TextBlockState:
    rect: tuple  
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
    
class OutlineType(Enum):
    Full_Document = 'full_document'
    Selection = 'selection'
    
@dataclass
class OutlineInfo:
    start: int
    end: int
    color: QColor
    width: float
    type: OutlineType

class TextBlockItem(QGraphicsTextItem):
    text_changed = Signal(str)
    item_selected = Signal(object)
    item_multi_selected = Signal(object, bool)  # Nuovo segnale per selezione multipla
    item_deselected = Signal()
    item_changed = Signal(QRectF, float, QPointF)
    text_highlighted = Signal(dict)
    change_undo = Signal(TextBlockState, TextBlockState)
    
    def __init__(self, 
             text = "", 
             parent_item = None, 
             font_family = "", 
             font_size = 20, 
             render_color = QColor(0, 0, 0), 
             alignment = Qt.AlignmentFlag.AlignCenter, 
             line_spacing = 1.2, 
             outline_color = QColor(255, 255, 255), 
             outline_width = 1,
             bold=False, 
             italic=False, 
             underline=False,
             direction=Qt.LayoutDirection.LeftToRight,
             outline_enabled=None):

        super().__init__(text)
        self.parent_item = parent_item
        self.text_color = render_color
        self.outline = bool(outline_color) if outline_enabled is None else bool(outline_enabled)
        self.outline_color = outline_color if self.outline else None
        self.outline_width = outline_width if self.outline else 0
        self.bold = bold
        self.italic = italic
        self.underline = underline
        self.font_family = font_family
        self.font_size = font_size
        self.alignment = alignment
        self.line_spacing = line_spacing
        self.direction = direction

        self.handle_size = 30
        self.selected = False
        self.multi_selected = False  # Stato per selezione multipla
        self.resizing = False
        self.resize_handle = None
        self._resize_start = None
        self.editing_mode = False
        self.last_selection = None 

        # Rotation properties
        self.rot_handle = None
        self.rotating = False
        self.last_rotation_angle = 0
        self.rotation_smoothing = 1.0  # rotation sensitivity
        self.center_scene_pos = None  

        self.old_state = None

        self.selection_outlines = []
        self._resize_text_dirty = False
        self._is_dragging = False
        self._cached_parent_rect = None
        self._cached_scene_rect = None
        self._drag_scene_updates_enabled = True
        
        # Layer Preserve Manager per preservare i disegni durante resize
        self._layer_preserve_manager = None
        self._resize_in_progress = False
        
        # Numbered marker
        self.marker = None

        self.setAcceptHoverEvents(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.document().contentsChanged.connect(self._on_text_changed)
        self.setTransformOriginPoint(self.boundingRect().center())
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        # Move handle
        self.move_handle = QGraphicsEllipseItem(-10, -10, 20, 20, self)
        self.move_handle.setBrush(QBrush(QColor(100, 100, 255, 200)))  # Blue semi-transparent
        self.move_handle.setPen(QPen(Qt.GlobalColor.white, 2))
        self.move_handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.move_handle.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self.move_handle.setZValue(HANDLE_LAYER_DEFAULT)
        self.move_handle.hide()
        self._update_handle_position()

        # Set the initial text direction
        self._apply_text_direction()

    def set_direction(self, direction):
        """Imposta la direzione del testo convertendo stringhe in enum Qt"""
        # Converti stringa in enum Qt.LayoutDirection se necessario
        if isinstance(direction, str):
            if direction.lower() in ['rtl', 'righttoleft']:
                qt_direction = Qt.LayoutDirection.RightToLeft
            else:
                qt_direction = Qt.LayoutDirection.LeftToRight
        else:
            qt_direction = direction
        
        if self.direction != qt_direction:
            self.direction = qt_direction
            self._apply_text_direction()
            self.update()

    def _apply_text_direction(self):
        """Applica la direzione del testo al documento"""
        text_option = self.document().defaultTextOption()
        # Assicurati che self.direction sia un Qt.LayoutDirection
        if isinstance(self.direction, str):
            if self.direction.lower() in ['rtl', 'righttoleft']:
                direction = Qt.LayoutDirection.RightToLeft
            else:
                direction = Qt.LayoutDirection.LeftToRight
        else:
            direction = self.direction
        
        text_option.setTextDirection(direction)
        self.document().setDefaultTextOption(text_option)

    def set_text(self, text, width):
        if self.is_html(text):
            self.setHtml(text)
            self.setTextWidth(width)
            if self.outline:
                self.set_outline(self.outline_color, self.outline_width)
            else:
                self.set_outline(None, None)
        else:
            self.set_plain_text(text)

    def set_plain_text(self, text):
        self.setPlainText(text)
        self.apply_all_attributes()

    def is_html(self, text):
        import re
        # Simple check for HTML tags
        return bool(re.search(r'<[^>]+>', text))

    def set_font(self, font_family, font_size):
        if not self.textCursor().hasSelection():
            self.font_family = font_family
            self.font_size = font_size

        try:
            _fs = float(str(font_size).replace(',', '.')) if isinstance(font_size, str) else float(font_size)
        except (ValueError, TypeError):
            _fs = 12.0
        font = QFont(font_family)
        try:
            font.setPointSizeF(_fs)
        except Exception:
            font.setPointSize(int(round(_fs)))
        self.update_text_format('font', font)

    def set_font_size(self, font_size):
        if not self.textCursor().hasSelection():
            self.font_size = font_size
        self.update_text_format('size', font_size)

    def update_text_width(self):
        width = self.document().size().width()
        self.setTextWidth(width)
        self._update_handle_position()

    def _update_handle_position(self):
        """Position the move handle above the top center of the block"""
        if hasattr(self, 'move_handle'):
            rect = self.boundingRect()
            self.move_handle.setPos(rect.width() / 2, -15)

    def set_marker(self, marker):
        """Set the numbered marker for this text box."""
        from shiboken6 import isValid

        # If there's an existing marker, remove it
        if self.marker and isValid(self.marker):
            try:
                if self.marker.scene():
                    self.marker.scene().removeItem(self.marker)
                # The marker is NOT parented to the text_item any more
                # (it's a top-level scene item), so setParentItem(None)
                # is a no-op but we still call it for safety.
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
        """Update the marker's position relative to this text box."""
        from shiboken6 import isValid
        try:
            marker = getattr(self, "marker", None)
            if not marker or not isValid(marker) or not self.scene():
                return
            marker.update_position_relative_to_item(self)
        except RuntimeError:
            self.marker = None
    
    def itemChange(self, change, value):
        """Override itemChange to update marker position when the item moves, rotates or changes scene"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            # Salta gestione marker durante rimozione batch (delete)
            scene = self.scene()
            if scene is not None and getattr(scene, '_batch_removing', False):
                return super().itemChange(change, value)
            # The marker is a top-level scene item (not parented to us).
            # If the text_item changes scene, the marker must follow.
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
            if not self._is_dragging:
                self.update_marker_position()
        return super().itemChange(change, value)

    def show_move_handle(self, show=True):
        if hasattr(self, 'move_handle'):
            self.move_handle.setVisible(show)

    def set_alignment(self, alignment):
        if not self.textCursor().hasSelection():
            self.alignment = alignment
        self.update_alignment(alignment)

    def update_alignment(self, alignment):
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        block_format = cursor.blockFormat()
        
        # Converti l'alignment in Qt.AlignmentFlag se è un int o stringa
        if isinstance(alignment, int):
            alignment = Qt.AlignmentFlag(alignment)
        elif isinstance(alignment, str):
            # Mappa le stringhe ai valori Qt.AlignmentFlag
            alignment_map = {
                'left': Qt.AlignmentFlag.AlignLeft,
                'center': Qt.AlignmentFlag.AlignCenter,
                'right': Qt.AlignmentFlag.AlignRight,
                'justify': Qt.AlignmentFlag.AlignJustify,
                'AlignLeft': Qt.AlignmentFlag.AlignLeft,
                'AlignCenter': Qt.AlignmentFlag.AlignCenter,
                'AlignRight': Qt.AlignmentFlag.AlignRight,
                'AlignJustify': Qt.AlignmentFlag.AlignJustify,
                '1': Qt.AlignmentFlag.AlignLeft,
                '2': Qt.AlignmentFlag.AlignCenter,
                '4': Qt.AlignmentFlag.AlignRight,
                '8': Qt.AlignmentFlag.AlignJustify
            }
            alignment = alignment_map.get(alignment, Qt.AlignmentFlag.AlignCenter)
        
        block_format.setAlignment(alignment)

        if has_selection:
            cursor.beginEditBlock()
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.mergeBlockFormat(block_format)
            cursor.endEditBlock()
        else:
            doc = self.document()
            cursor = QTextCursor(doc)
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.mergeBlockFormat(block_format)

        self.update()

    def update_text_format(self, attribute, value):
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()

        format_operations = {
            'color': lambda cf, v: cf.setForeground(v),
            'font': lambda cf, v: cf.setFont(v),
            'size': lambda cf, v: cf.setFontPointSize(v),
            'bold': lambda cf, v: cf.setFontWeight(QFont.Bold if v else QFont.Normal),
            'italic': lambda cf, v: cf.setFontItalic(v),
            'underline': lambda cf, v: cf.setFontUnderline(v),
        }

        if attribute not in format_operations:
            print(f"Unsupported attribute: {attribute}")
            return

        char_format = QTextCharFormat()
        format_operations[attribute](char_format, value)

        if not has_selection:
            cursor.select(QTextCursor.SelectionType.Document)    
  
        cursor.mergeCharFormat(char_format)

        # Update the document's default format
        doc_format = self.document().defaultTextOption()
        if attribute == 'color':
            self.setDefaultTextColor(value)
        elif attribute == 'font':
            self.document().setDefaultFont(value)
        elif attribute == 'size':
            font = self.document().defaultFont()
            try:
                _v = float(str(value).replace(',', '.')) if isinstance(value, str) else float(value)
            except (ValueError, TypeError):
                _v = 12.0
            try:
                font.setPointSizeF(_v)
            except Exception:
                font.setPointSize(int(round(_v)))
            self.document().setDefaultFont(font)
        
        # Clear the selection by moving the cursor to the end of the document
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.End)

        self.setTextCursor(cursor)
        self.document().setDefaultTextOption(doc_format)
        self.update()

    def set_line_spacing(self, spacing):
        self.line_spacing = spacing
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        spacing = spacing * 100
        spacing = float(spacing)
        block_format.setLineHeight(spacing, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.mergeBlockFormat(block_format)

    def set_color(self, color):
        # Ensure color is always a QColor object
        if isinstance(color, str):
            color = QColor(color)
        elif not isinstance(color, QColor):
            color = QColor(0, 0, 0)  # Default to black
            
        if not self.textCursor().hasSelection():
            self.text_color = color
        self.update_text_format('color', color)

    def update_outlines(self):
        """Update the selection outlines when text changes"""
        if self.outline:
            # Create an outline for the entire document
            doc = self.document()
            char_count = doc.characterCount()
            
            # Create an outline info for the entire document
            new_outline = OutlineInfo(  
                start = 0,
                end = max(0, char_count - 1),
                color = self.outline_color,  
                width = self.outline_width,
                type = OutlineType.Full_Document
            )
            
            # Remove all existing outlines and only keep the new Full_Document one
            self.selection_outlines = [new_outline]
        else:
            # Remove all outlines if outline is disabled
            self.selection_outlines = []

        self.update() 

    def set_outline(self, outline_color, outline_width):
        # Initialize start and end variables
        start = 0
        end = 0

        if self.textCursor().hasSelection():
            # Store outline properties for the current selection
            start = self.textCursor().selectionStart()
            end = self.textCursor().selectionEnd()
        else:
            # Set global outline properties only when there's no selection
            self.outline = True if outline_color else False
            
            if self.outline:
                self.outline_color = outline_color
                self.outline_width = outline_width
            else:
                # When disabling outline, clear the properties
                self.outline_color = None
                self.outline_width = 0

            char_count = self.document().characterCount()
            start = 0
            end = max(0, char_count - 1)

        # Ensure positions are within valid bounds
        char_count = self.document().characterCount()
        start = min(start, max(0, char_count - 1))
        end = min(end, max(0, char_count - 1))

        type = OutlineType.Full_Document if self.outline else OutlineType.Selection

        if type == OutlineType.Full_Document:
            # For full document, only keep this outline
            if outline_color and char_count > 0:
                self.selection_outlines = [
                    OutlineInfo(start, end, outline_color, outline_width, type)
                ]
            else:
                self.selection_outlines = []
        else:
            # For selection, maybe just keep this one (clear others)
            if outline_color and char_count > 0:
                self.selection_outlines = [
                    OutlineInfo(start, end, outline_color, outline_width, type)
                ]
            else:
                self.selection_outlines = []
        
        # Force immediate visual update
        self.update()
        # Also trigger a repaint to ensure the change is visible immediately
        if self.scene():
            self.scene().update()

    def paint(self, painter, option, widget=None):
        # Disegna il bordo per la selezione multipla
        if self.multi_selected:
            painter.save()
            pen = QPen(QColor(255, 165, 0), 3)  # Bordo arancione per selezione multipla
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
            painter.restore()
        
        # Only draw selection outlines if NOT in editing mode and NOT dragging
        if self.selection_outlines and not self.editing_mode and not self._is_dragging:
            doc = self.document().clone()
            painter.save()
            
            # Clear the document first to only show outlined parts
            cursor = QTextCursor(doc)
            cursor.select(QTextCursor.SelectionType.Document)
            fmt = cursor.charFormat()
            fmt.setForeground(QColor(0, 0, 0, 0))  # Transparent
            cursor.mergeCharFormat(fmt)

            # Apply outline colors only to selected regions
            for outline_info in self.selection_outlines:
                doc_length = doc.characterCount()
                # Ensure positions are within document bounds
                safe_start = min(outline_info.start, max(0, doc_length - 1))
                safe_end = min(outline_info.end, max(0, doc_length - 1))
                
                # Only proceed if we have valid positions
                if safe_start <= safe_end and doc_length > 0:
                    cursor.setPosition(safe_start)
                    cursor.setPosition(safe_end, QTextCursor.KeepAnchor)
                    fmt = cursor.charFormat()
                # Converti la stringa colore in QColor se necessario
                if isinstance(outline_info.color, str):
                    color = QColor(outline_info.color)
                else:
                    color = outline_info.color
                fmt.setForeground(color)
                cursor.mergeCharFormat(fmt)

                # Draw the outline for this selection
                offsets = [(dx, dy) 
                    for dx in (-outline_info.width, 0, outline_info.width)
                    for dy in (-outline_info.width, 0, outline_info.width)
                    if dx != 0 or dy != 0
                ]
                
                for dx, dy in offsets:
                    painter.save()
                    painter.translate(dx, dy)
                    doc.drawContents(painter)
                    painter.restore()

            painter.restore()

        # Draw the normal text on top
        super().paint(painter, option, widget)

    def set_bold(self, state):
        if not self.textCursor().hasSelection():
            self.bold = state
        self.update_text_format('bold', state)

    def set_italic(self, state):
        if not self.textCursor().hasSelection():
            self.italic = state
        self.update_text_format('italic', state)

    def set_underline(self, state):
        if not self.textCursor().hasSelection():
            self.underline = state
        self.update_text_format('underline', state)
    
    def set_multi_selected(self, state):
        """Imposta lo stato di selezione multipla"""
        self.multi_selected = state
        try:
            self.update()  # Aggiorna la visualizzazione
        except RuntimeError:
            # L'oggetto C++ è già stato eliminato
            pass
    
    def is_multi_selected(self):
        """Restituisce True se l'elemento è in selezione multipla"""
        return self.multi_selected

    def apply_all_attributes(self):
        self.set_font(self.font_family, self.font_size)
        self.set_color(self.text_color)
        if self.outline:
            self.set_outline(self.outline_color, self.outline_width)
        else:
            self.set_outline(None, None)
        self.set_bold(self.bold)
        self.set_italic(self.italic)
        self.set_underline(self.underline)
        self.set_line_spacing(self.line_spacing)
        self.update_text_width()
        self.alignment = Qt.AlignmentFlag.AlignCenter
        self.set_alignment(self.alignment)

    def mouseDoubleClickEvent(self, event):
        if not self.editing_mode:
            self.enter_editing_mode()
        super().mouseDoubleClickEvent(event)

    def enter_editing_mode(self):
        self.editing_mode = True
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.setFocus()

    def exit_editing_mode(self):
        self.editing_mode = False
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clearFocus()
        # Sync any changes made during editing
        self._sync_editing_changes()
        # Update outlines now that we're out of editing mode
        self.update_outlines()

    def focusOutEvent(self, event):
        """Handle focus out event to sync changes made during editing"""
        if self.editing_mode:
            self._sync_editing_changes()
            # Update outlines now that focus is leaving (exiting editing mode)
            self.update_outlines()
        super().focusOutEvent(event)

    def _sync_editing_changes(self):
        """Synchronize changes made during editing with object properties"""
        # Get the current HTML content
        current_html = self.toHtml()
        
        # Extract and update properties from the current document
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        
        if cursor.hasSelection():
            char_format = cursor.charFormat()
            block_format = cursor.blockFormat()
            
            # Update font properties if they've changed
            font = char_format.font()
            if font.family() and font.family() != self.font_family:
                self.font_family = font.family()
            if font.pointSize() > 0 and font.pointSize() != self.font_size:
                self.font_size = font.pointSize()
            
            # Update text formatting properties
            self.bold = font.bold()
            self.italic = font.italic()
            self.underline = font.underline()
            
            # Update text color
            if char_format.foreground().color().isValid():
                self.text_color = char_format.foreground().color()
            
            # Update alignment
            if block_format.alignment() != 0:
                self.alignment = block_format.alignment()

    def _on_text_changed(self):
        new_text = self.toPlainText()
        self.text_changed.emit(new_text)
        # Only update outlines when not in editing mode
        if not self.editing_mode:
            self.update_outlines()

    def mousePressEvent(self, event):
        if not self.editing_mode:
            scene_pos = event.scenePos()
            local_pos = self.mapFromScene(scene_pos)
            self.selected = self.boundingRect().contains(local_pos)

            if event.button() == Qt.LeftButton:
                self.old_state = TextBlockState.from_item(self)
                self.resize_handle = self.get_handle_at_position(local_pos, self.boundingRect())
                if self.resize_handle:
                    self.resizing = True
                    self._resize_start = scene_pos
                    self._resize_in_progress = True
                    
                    # Inizializza il LayerPreserveManager per preservare i disegni
                    if self.scene() and self._layer_preserve_manager is None:
                        from .layer_preserve import LayerPreserveManager
                        self._layer_preserve_manager = LayerPreserveManager(self.scene())
                    
                    # Inizia l'operazione di preservazione
                    if self._layer_preserve_manager:
                        from .layer_preserve import LayerOperation
                        # Calcola l'area interessata dal resize (bounding rect della casella + margine)
                        affected_rect = self.mapRectToScene(self.boundingRect())
                        # Espandi il rect per includere anche le aree vicine
                        affected_rect = affected_rect.adjusted(-50, -50, 50, 50)
                        self._layer_preserve_manager.begin_operation(
                            LayerOperation.RESIZE, 
                            affected_rect
                        )
                else:
                    self._is_dragging = True
                    self._cached_parent_rect = self.parent_item.boundingRect()
                    self._cached_scene_rect = self.mapToScene(self.boundingRect()).boundingRect()
                    self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

            if self.selected and self.isSelected():
                super().mousePressEvent(event)
                return

            self.setSelected(self.selected)

            if self.selected:
                self.show_move_handle(True)
                ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
                if ctrl_pressed:
                    self.item_multi_selected.emit(self, True)
                else:
                    self.item_selected.emit(self)

        super().mousePressEvent(event)
        self.last_selection = self.textCursor().selection()

    def mouseReleaseEvent(self, event):
        was_dragging = self._is_dragging
        
        if self.old_state:
            new_state = TextBlockState.from_item(self)
            if self.old_state.rect != new_state.rect:
                self.change_undo.emit(self.old_state, new_state)
        
        if not self.editing_mode:
            if event.button() == Qt.LeftButton:
                # Finalizza l'operazione di preservazione se in corso
                if self._resize_in_progress and self._layer_preserve_manager:
                    self._layer_preserve_manager.end_operation(restore_brush_strokes=True)
                    self._resize_in_progress = False
                
                self.resizing = False
                self.rotating = False
                self.resize_handle = None
                self._resize_start = None
                self.center_scene_pos = None
                self._is_dragging = False
                self._cached_parent_rect = None
                self._cached_scene_rect = None
                # Aggiorna marker solo alla fine del drag (non durante)
                if was_dragging:
                    self.update_marker_position()
                self.update_cursor(event.pos())
                
                if was_dragging:
                    new_rect = QRectF(self.pos(), self.boundingRect().size())
                    self.item_changed.emit(new_rect, self.rotation(), self.transformOriginPoint())
                
                if self._resize_text_dirty:
                    plain_text = self.toPlainText().replace('\n', ' ')
                    self.setPlainText(plain_text)
                    self.apply_all_attributes()
                    self.update()
                    self._resize_text_dirty = False
        super().mouseReleaseEvent(event)

        current_selection = self.textCursor().selection()
        if current_selection != self.last_selection:
            self.on_selection_changed()
        self.last_selection = current_selection

    def mouseMoveEvent(self, event):
        if not self.editing_mode:
            scene_pos = event.scenePos()
            local_pos = self.mapFromScene(scene_pos)
                
            if self.resizing and self.resize_handle:
                self.resize_item(local_pos)
            else:
                self.update_cursor(local_pos)
                if self.parent_item:
                    # Se clicchiamo sulla maniglia o se siamo in modalità spostamento (cursore SizeAll)
                    if self.move_handle.isVisible() and self.move_handle.contains(self.move_handle.mapFromScene(scene_pos)):
                        local_last_scene = self.mapFromScene(event.lastScenePos())
                        self.move_item(local_pos, local_last_scene)
                    elif self.cursor().shape() == Qt.CursorShape.SizeAllCursor:
                        local_last_scene = self.mapFromScene(event.lastScenePos())
                        self.move_item(local_pos, local_last_scene)
                    else:
                        super().mouseMoveEvent(event)
                else:
                    super().mouseMoveEvent(event)
        else:
            super().mouseMoveEvent(event)

    def hoverMoveEvent(self, event):
        if self.selected:
            self.update_cursor(event.pos())
            super().hoverMoveEvent(event)

    def contextMenuEvent(self, event):
        super().contextMenuEvent(event)
        if self.editing_mode:
            self.enter_editing_mode()
    
    def handleDeselection(self):
        if self.selected:
            self.setSelected(False)
            self.selected = False
            self.show_move_handle(False)
            self.item_deselected.emit()
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if self.editing_mode:
                self.exit_editing_mode()
            self.update()

    def init_rotation(self, scene_pos):
        self.rotating = True
        center = self.boundingRect().center()
        self.center_scene_pos = self.mapToScene(center)
        self.last_rotation_angle = math.degrees(math.atan2(
            scene_pos.y() - self.center_scene_pos.y(),
            scene_pos.x() - self.center_scene_pos.x()
        ))

    def move_item(self, local_pos: QPointF, last_scene_pos: QPointF):
        delta = self.mapToParent(local_pos) - self.mapToParent(last_scene_pos)
        
        if abs(delta.x()) < 1 and abs(delta.y()) < 1:
            return
        
        new_pos = self.pos() + delta
        
        if self._is_dragging and self._cached_parent_rect and self._cached_scene_rect:
            parent_rect = self._cached_parent_rect
            bounding_rect = self._cached_scene_rect
            
            if bounding_rect.left() + delta.x() < 0:
                new_pos.setX(self.pos().x() - bounding_rect.left())
            elif bounding_rect.right() + delta.x() > parent_rect.width():
                new_pos.setX(self.pos().x() + parent_rect.width() - bounding_rect.right())
            
            if bounding_rect.top() + delta.y() < 0:
                new_pos.setY(self.pos().y() - bounding_rect.top())
            elif bounding_rect.bottom() + delta.y() > parent_rect.height():
                new_pos.setY(self.pos().y() + parent_rect.height() - bounding_rect.bottom())
        else:
            scene_rect = self.mapToScene(self.boundingRect())
            bounding_rect = scene_rect.boundingRect()
            parent_rect = self.parent_item.boundingRect()
            
            if bounding_rect.left() + delta.x() < 0:
                new_pos.setX(self.pos().x() - bounding_rect.left())
            elif bounding_rect.right() + delta.x() > parent_rect.width():
                new_pos.setX(self.pos().x() + parent_rect.width() - bounding_rect.right())
            
            if bounding_rect.top() + delta.y() < 0:
                new_pos.setY(self.pos().y() - bounding_rect.top())
            elif bounding_rect.bottom() + delta.y() > parent_rect.height():
                new_pos.setY(self.pos().y() + parent_rect.height() - bounding_rect.bottom())
        
        self.setPos(new_pos)

        if not self._is_dragging:
            new_rect = QRectF(new_pos, self.boundingRect().size())
            self.item_changed.emit(new_rect, self.rotation(), self.transformOriginPoint())

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

        # Update Textblock
        rect = QRectF(self.pos(), self.boundingRect().size())
        self.item_changed.emit(rect, self.rotation(), self.transformOriginPoint())
    
    def update_cursor(self, pos):
        if not self.editing_mode:
            cursor = self.get_cursor_for_position(pos)
            self.setCursor(QCursor(cursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))

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
        # Se la casella è piccola, il ridimensionamento è più difficile di proposito 
        # per favorire lo spostamento
        for handle, handle_rect in handles.items():
            if handle_rect.contains(pos):
                return handle

        return None
    
    def resize_item(self, pos):
        if not self._resize_start:
            return

        # Convert positions to scene coordinates
        scene_pos = self.mapToScene(pos)
        scene_start = self._resize_start

        # Calculate delta in scene coordinates
        scene_delta = scene_pos - scene_start

        # Get current rotation in radians
        angle_rad = math.radians(-self.rotation())  # Negative because we want to counter-rotate

        # Rotate delta back to item's original coordinate system
        rotated_delta_x = scene_delta.x() * math.cos(angle_rad) - scene_delta.y() * math.sin(angle_rad)
        rotated_delta_y = scene_delta.x() * math.sin(angle_rad) + scene_delta.y() * math.cos(angle_rad)
        rotated_delta = QPointF(rotated_delta_x, rotated_delta_y)

        # Get the current rect in item coordinates
        rect = self.boundingRect()
        new_rect = QRectF(rect)
        original_height = rect.height()

        # Apply the changes based on which handle is being dragged
        if self.resize_handle in ['left', 'top_left', 'bottom_left']:
            new_rect.setLeft(rect.left() + rotated_delta.x())
        if self.resize_handle in ['right', 'top_right', 'bottom_right']:
            new_rect.setRight(rect.right() + rotated_delta.x())
        if self.resize_handle in ['top', 'top_left', 'top_right']:
            new_rect.setTop(rect.top() + rotated_delta.y())
        if self.resize_handle in ['bottom', 'bottom_left', 'bottom_right']:
            new_rect.setBottom(rect.bottom() + rotated_delta.y())

        # Ensure minimum size
        min_size = 10
        if new_rect.width() < min_size:
            if 'left' in self.resize_handle:
                new_rect.setLeft(new_rect.right() - min_size)
            else:
                new_rect.setRight(new_rect.left() + min_size)
        if new_rect.height() < min_size:
            if 'top' in self.resize_handle:
                new_rect.setTop(new_rect.bottom() - min_size)
            else:
                new_rect.setBottom(new_rect.top() + min_size)

        # Calculate the change in position in scene coordinates
        old_pos = self.mapToScene(rect.topLeft())
        new_pos = self.mapToScene(new_rect.topLeft())
        pos_delta = new_pos - old_pos
        act_pos = self.pos() + pos_delta

        # Convert the new rectangle to scene coordinates to check bounds
        scene_rect = self.mapRectToScene(new_rect)
        parent_rect = self.parent_item.boundingRect()
        
        # Ensure the rectangle stays within parent bounds
        if (scene_rect.left() >= 0 and 
            scene_rect.right() <= parent_rect.right() and
            scene_rect.top() >= 0 and 
            scene_rect.bottom() <= parent_rect.bottom()):

            # Update position
            self.setPos(act_pos)

            # Update size and font
            self.setTextWidth(new_rect.width())
            height_ratio = new_rect.height() / original_height
            new_font_size = self.font_size * height_ratio
            self.set_font_size(new_font_size)

            # Update marker position. The marker's diameter is now a
            # fixed fraction of the loaded page's pixel size and is
            # decoupled from the parent transform, so we don't pass the
            # (auto-scaled) font_size to the marker any more -- doing so
            # was the root cause of the "growing marker" bug.
            if self.marker:
                self.update_marker_position()

            # Sostituisci i caratteri di a capo con spazi per una visualizzazione continua
            # (solo alla fine del resize, non durante il trascinamento per evitare re-render)
            self._resize_text_dirty = True

            # Update the resize start position
            self._resize_start = scene_pos

            # Update Textblock
            nrect = QRectF(act_pos, self.boundingRect().size())
            self.item_changed.emit(nrect, self.rotation(), self.transformOriginPoint())

    def on_selection_changed(self):
        cursor = self.textCursor()
        properties = self.get_selected_text_properties(cursor)
        if self.editing_mode:
            self.text_highlighted.emit(properties)

    def get_selected_text_properties(self, cursor: QTextCursor):
        # Helper function to safely get color name
        def get_color_name(color):
            if isinstance(color, str):
                return color
            elif hasattr(color, 'name'):
                return color.name()
            else:
                return '#000000'  # Default black
        
        if not cursor.hasSelection():
            return {
                'font_family': self.font_family,
                'font_size': self.font_size,
                'bold': False,
                'italic': False,
                'underline': False,
                'text_color': get_color_name(self.text_color),
                'alignment': self.alignment,
                'outline': self.outline,
                'outline_color': get_color_name(self.outline_color) if self.outline_color else None,
                'outline_width': self.outline_width,
            }

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        # Find all selections that completely contain the current selection
        containing_outlines = [
            outline for outline in self.selection_outlines
            if outline.start <= start and outline.end >= end
        ]

        # Get outline properties from the last (most recent) containing selection
        outline_properties = None
        if containing_outlines:
            latest_outline = containing_outlines[-1]  # Get the last one from the list
            outline_properties = {
                'outline': True,
                'outline_color': get_color_name(latest_outline.color),
                'outline_width': latest_outline.width
            }
        else:
            outline_properties = {
                'outline': False,
                'outline_color': None,
                'outline_width': None
            }

        # Create a new cursor for traversing the selection
        format_cursor = QTextCursor(cursor)

        # Initialize properties with default values
        properties = {
            'font_family': set(),
            'font_size': set(),
            'bold': True,
            'italic': True,
            'underline': True,
            'text_color': set(),
            'alignment': None,
        }

        # Get initial block format for alignment
        format_cursor.setPosition(start)
        properties['alignment'] = format_cursor.blockFormat().alignment()

        # Iterate through the selection one character at a time
        for pos in range(start, end):
            format_cursor.setPosition(pos)
            format_cursor.setPosition(pos + 1, QTextCursor.KeepAnchor)
            char_format = format_cursor.charFormat()

            # Update properties
            properties['font_family'].add(char_format.font().family())
            properties['font_size'].add(char_format.fontPointSize())
            properties['bold'] &= char_format.font().bold()
            properties['italic'] &= char_format.font().italic()
            properties['underline'] &= char_format.font().underline()
            properties['text_color'].add(char_format.foreground().color().name())

        # Convert sets to single values if all elements are the same, otherwise set to None
        for key, value in properties.items():
            if isinstance(value, set):
                properties[key] = list(value)[0] if len(value) == 1 else None

        # Merge outline properties with other properties
        properties.update(outline_properties)

        return properties
    
    def __copy__(self):
        cls = self.__class__
        new_instance = cls(
            text=self.toHtml(),
            parent_item=self.parent_item,
            font_family=self.font_family,
            font_size=self.font_size,
            render_color=self.text_color,
            alignment=self.alignment,
            line_spacing=self.line_spacing,
            outline_color=self.outline_color,
            outline_width=self.outline_width,
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            outline_enabled=self.outline
        )
        
        new_instance.set_text(self.toHtml(), self.boundingRect().width())
        new_instance.setTransformOriginPoint(self.transformOriginPoint())
        new_instance.setPos(self.pos())
        new_instance.setRotation(self.rotation())
        new_instance.setScale(self.scale())
        new_instance.__dict__.update(copy.copy(self.__dict__))
        return new_instance

    def to_dict(self):
        """Converte l'oggetto in un dizionario per la serializzazione."""
        # Ensure text_color has a default value if None
        text_color = self.text_color if self.text_color else QColor(0, 0, 0)
        # Ensure outline_color has a default value if None
        outline_color = self.outline_color if self.outline_color else QColor(255, 255, 255)
        
        return {
            '__class__': 'TextBlockItem',
            'text': self.toHtml(),
            'rect': {
                'x': self.pos().x(),
                'y': self.pos().y(),
                'width': self.boundingRect().width(),
                'height': self.boundingRect().height()
            },
            'angle': self.rotation(),
            'font_family': self.font_family,
            'font_size': self.font_size,
            'color': {
                'r': text_color.red(),
                'g': text_color.green(),
                'b': text_color.blue(),
                'a': text_color.alpha()
            },
            'background_color': {
                'r': 255,
                'g': 255,
                'b': 255,
                'a': 0
            },
            'border_color': {
                'r': 0,
                'g': 0,
                'b': 0,
                'a': 0
            },
            'border_width': 1,
            'alignment': int(self.alignment),
            'opacity': 1.0,
            'translation': "",
            'original_text': self.toPlainText(),
            'outline': self.outline,
            'outline_color': {
                'r': outline_color.red(),
                'g': outline_color.green(),
                'b': outline_color.blue(),
                'a': outline_color.alpha()
            },
            'outline_width': self.outline_width,
            'bold': self.bold,
            'italic': self.italic,
            'underline': self.underline,
            'line_spacing': self.line_spacing,
            'direction': self.direction
        }

    @classmethod
    def from_dict(cls, data):
        """Crea un'istanza di TextBlockItem da un dizionario."""
        # Crea un'istanza vuota
        instance = cls()
        
        # Imposta le proprietà di base
        instance.setHtml(data.get('text', ''))
        
        # Imposta il rettangolo
        rect_data = data.get('rect', {})
        instance.setPos(rect_data.get('x', 0), rect_data.get('y', 0))
        instance.setTextWidth(rect_data.get('width', 100))
        
        # Imposta l'angolo di rotazione
        instance.setRotation(data.get('angle', 0))
        
        # Imposta le proprietà di stile
        instance.font_family = data.get('font_family', 'Arial')
        instance.font_size = data.get('font_size', 12)
        
        # Imposta i colori
        color_data = data.get('color', {'r':0, 'g':0, 'b':0, 'a':255})
        instance.text_color = QColor(
            color_data.get('r', 0),
            color_data.get('g', 0),
            color_data.get('b', 0),
            color_data.get('a', 255)
        )
        
        # Imposta le altre proprietà
        instance.alignment = data.get('alignment', int(Qt.AlignmentFlag.AlignCenter))
        instance.outline = data.get('outline', False)
        outline_color_data = data.get('outline_color', {'r':255, 'g':255, 'b':255, 'a':255})
        instance.outline_color = QColor(
            outline_color_data.get('r', 255),
            outline_color_data.get('g', 255),
            outline_color_data.get('b', 255),
            outline_color_data.get('a', 255)
        )
        instance.outline_width = data.get('outline_width', 1)
        instance.bold = data.get('bold', False)
        instance.italic = data.get('italic', False)
        instance.underline = data.get('underline', False)
        instance.line_spacing = data.get('line_spacing', 1.2)
        # Handle direction - ensure it's a Qt.LayoutDirection
        direction_data = data.get('direction', Qt.LayoutDirection.LeftToRight)
        if isinstance(direction_data, dict):
            # If direction was saved as a dict, use default
            instance.direction = Qt.LayoutDirection.LeftToRight
        elif isinstance(direction_data, int):
            # Convert int to Qt.LayoutDirection
            instance.direction = Qt.LayoutDirection(direction_data)
        else:
            # Use as-is if already Qt.LayoutDirection
            instance.direction = direction_data
        
        # Aggiorna il formato del testo
        instance.apply_all_attributes()
        
        return instance
