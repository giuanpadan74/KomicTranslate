from PySide6.QtCore import QTimer
from PySide6.QtGui import QUndoCommand

from .base import RectCommandBase
from ..canvas.polygon_overlay import remove_polygon_overlay
from ..canvas.z_layers import TEXT_BOX_Z


def _deferred_markers_update(viewer, scene):
    """Aggiorna marker in modo incrementale nella prossima iterazione dell'event loop.

    Usa renumber_incremental_markers che rinumera i marker esistenti
    senza rimuoverli/ricrearli, evitando decine di repaint.
    """
    viewer.renumber_incremental_markers()


class DeleteBoxesCommand(QUndoCommand, RectCommandBase):
    def __init__(self, main_page, rect_item, text_item, blk, blk_list,
                 defer_update=False):
        super().__init__()
        self.ct = main_page
        self.viewer = main_page.image_viewer
        self.photo = self.viewer.photo
        self.scene = self.viewer._scene
        self.rect_properties = self.save_rect_properties(rect_item) if rect_item else None
        # toHtml() DEFERITO: catturato solo quando necessario (per undo)
        self._txt_item_ref = text_item
        self.txt_item_prp = None  # Lazy: popolato da _ensure_txt_properties()
        self.blk_properties = self.save_blk_properties(blk)
        self.blk_list = blk_list
        self._defer_update = defer_update
        self._properties_captured = False
        # Direct references for O(1) lookup on first redo
        self._direct_rect = rect_item
        self._direct_txt = text_item
        self._direct_blk = blk

    def _ensure_txt_properties(self):
        """Cattura le proprietà del text item (con toHtml()) solo quando necessario."""
        if self._properties_captured:
            return
        if self._txt_item_ref is not None:
            self.txt_item_prp = self.save_txt_item_properties(self._txt_item_ref)
        self._properties_captured = True

    def _find_rect(self):
        """Find rect: O(1) direct ref or fallback O(N) property match."""
        ref = self._direct_rect
        if ref is not None:
            try:
                from shiboken6 import isValid
                if isValid(ref) and ref.scene() is self.scene:
                    return ref
            except RuntimeError:
                pass
            self._direct_rect = None
        return (self.find_matching_rect(self.scene, self.rect_properties)
                if self.rect_properties else None)

    def _find_txt(self):
        """Find text item: O(1) direct ref or fallback O(N) property match."""
        ref = self._direct_txt
        if ref is not None:
            try:
                from shiboken6 import isValid
                if isValid(ref) and ref.scene() is self.scene:
                    return ref
            except RuntimeError:
                pass
            self._direct_txt = None
        return (self.find_matching_txt_item(self.scene, self.txt_item_prp)
                if self.txt_item_prp else None)

    def _find_blk(self):
        """Find block: O(1) direct ref or fallback O(N) property match."""
        ref = self._direct_blk
        if ref is not None and ref in self.blk_list:
            return ref
        self._direct_blk = None
        return self.find_matching_blk(self.blk_list, self.blk_properties)

    def redo(self):
        # Cattura proprietà (con toHtml()) PRIMA di rimuovere l'item
        self._ensure_txt_properties()
        removed_any = False
        matching_rect = self._find_rect()
        matching_txt_item = self._find_txt()
        matching_blk = self._find_blk()

        # Abilita flag batch per sopprimere itemChange marker handling
        self.scene._batch_removing = True
        try:
            if matching_rect:
                remove_polygon_overlay(matching_rect, self.viewer)
                self.scene.removeItem(matching_rect)
                # find_matching_* scandisce scene.items(), che puo' non
                # coincidere con viewer.rectangles: list.remove() sollevava
                # ValueError e lasciava la scena a meta' modificata.
                if matching_rect in self.viewer.rectangles:
                    self.viewer.rectangles.remove(matching_rect)
                self.viewer.selected_rect = None
                removed_any = True

            if matching_txt_item:
                self.scene.removeItem(matching_txt_item)
                if matching_txt_item in self.viewer.text_items:
                    self.viewer.text_items.remove(matching_txt_item)
                self.ct.curr_tblock_item = None
                if (hasattr(self.ct, "selected_text_items")
                        and matching_txt_item in self.ct.selected_text_items):
                    self.ct.selected_text_items.remove(matching_txt_item)
                removed_any = True
        finally:
            self.scene._batch_removing = False

        if matching_blk:
            self.blk_list.remove(matching_blk)
            self.ct.curr_tblock = None
            removed_any = True

        if removed_any:
            if self._defer_update:
                QTimer.singleShot(
                    0, lambda: _deferred_markers_update(self.viewer, self.scene)
                )
            else:
                self.viewer.renumber_incremental_markers()

    def undo(self):
        # Cattura proprietà se non ancora fatto (es. undo senza redo previo)
        self._ensure_txt_properties()
        restored_any = False

        if self.rect_properties and not self.find_matching_rect(self.scene, self.rect_properties):
            rect_item = self.create_rect_item(self.rect_properties, self.viewer.photo)
            self.viewer.connect_rect_item.emit(rect_item)
            self.viewer.rectangles.append(rect_item)
            restored_any = True

        if not self.find_matching_blk(self.blk_list, self.blk_properties):
            blk = self.create_new_blk(self.blk_properties)
            self.blk_list.append(blk)
            if self.rect_properties:
                matching_rect = self.find_matching_rect(self.scene, self.rect_properties)
                if matching_rect:
                    self.viewer.connect_rect_item.emit(matching_rect)
            restored_any = True

        if self.txt_item_prp and not self.find_matching_txt_item(self.scene, self.txt_item_prp):
            text_item = self.create_new_txt_item(self.txt_item_prp, self.viewer.photo)
            self.viewer.connect_text_item.emit(text_item)
            self.scene.addItem(text_item)
            text_item.setZValue(TEXT_BOX_Z)
            self.viewer.text_items.append(text_item)
            restored_any = True

        if restored_any:
            font_size = (
                float(str(self.ct.font_size_dropdown.currentText()).replace(',', '.'))
                if hasattr(self.ct, "font_size_dropdown")
                else 20
            )
            self.viewer.update_all_markers(font_size=font_size)
            self.scene.update()


class AddTextItemCommand(QUndoCommand, RectCommandBase):
    def __init__(self, main_page, text_item):
        super().__init__()
        self.ct = main_page
        self.viewer = main_page.image_viewer
        self.photo = self.viewer.photo
        self.scene = self.viewer._scene
        self.txt_item_prp = self.save_txt_item_properties(text_item)

    def redo(self):
        if not self.find_matching_txt_item(self.scene, self.txt_item_prp):
            text_item = self.create_new_txt_item(self.txt_item_prp, self.viewer.photo)
            self.viewer.connect_text_item.emit(text_item)
            self.scene.addItem(text_item)
            text_item.setZValue(TEXT_BOX_Z)
            self.viewer.text_items.append(text_item)
            font_size = (
                float(str(self.ct.font_size_dropdown.currentText()).replace(',', '.'))
                if hasattr(self.ct, "font_size_dropdown")
                else 20
            )
            self.viewer.update_all_markers(font_size=font_size)

    def undo(self):
        matching_txt_item = self.find_matching_txt_item(self.scene, self.txt_item_prp)
        if matching_txt_item:
            self.scene.removeItem(matching_txt_item)
            self.viewer.text_items.remove(matching_txt_item)

            controller = self.viewer.parent()
            if hasattr(controller, "text_items"):
                for key, item in list(controller.text_items.items()):
                    if item == matching_txt_item:
                        del controller.text_items[key]
                        break

            font_size = (
                float(str(self.ct.font_size_dropdown.currentText()).replace(',', '.'))
                if hasattr(self.ct, "font_size_dropdown")
                else 20
            )
            self.viewer.update_all_markers(font_size=font_size)
            self.scene.update()
