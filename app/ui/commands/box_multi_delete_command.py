from PySide6.QtCore import QTimer
from PySide6.QtGui import QUndoCommand

from .base import RectCommandBase
from .box_text_commands import _deferred_markers_update
from ..canvas.polygon_overlay import remove_polygon_overlay
from ..canvas.z_layers import TEXT_BOX_Z


class DeleteMultipleBoxesCommand(QUndoCommand, RectCommandBase):
    def __init__(self, main_page, rect_items, text_items, blks, blk_list,
                 defer_update=False):
        super().__init__()
        self.ct = main_page
        self.viewer = main_page.image_viewer
        self.photo = self.viewer.photo
        self.scene = self.viewer._scene
        self.blk_list = blk_list
        self.rect_properties_list = [
            self.save_rect_properties(r) for r in rect_items if r]
        # toHtml() DEFERITO: salviamo le proprietà solo quando servono (per undo)
        self._txt_item_refs = [t for t in text_items if t]
        self.txt_item_prp_list = None  # Lazy: popolato da _ensure_txt_properties()
        self.blk_properties_list = [
            self.save_blk_properties(b) for b in blks if b]
        self._defer_update = defer_update
        self._properties_captured = False
        # Direct references for O(1) lookup on first redo
        self._direct_rects = list(rect_items)
        self._direct_txts = list(text_items)
        self._direct_blks = list(blks)

    def _ensure_txt_properties(self):
        """Cattura le proprietà dei text items (con toHtml()) solo quando necessario."""
        if self._properties_captured:
            return
        self.txt_item_prp_list = [
            self.save_txt_item_properties(t) for t in self._txt_item_refs]
        self._properties_captured = True

    def _find_rect(self, idx):
        """Find rect at idx: O(1) direct ref or fallback O(N)."""
        ref = self._direct_rects[idx] if idx < len(self._direct_rects) else None
        if ref is not None:
            try:
                from shiboken6 import isValid
                if isValid(ref) and ref.scene() is self.scene:
                    return ref
            except RuntimeError:
                pass
            self._direct_rects[idx] = None
        return self.find_matching_rect(
            self.scene, self.rect_properties_list[idx])

    def _find_txt(self, idx):
        """Find text item at idx: O(1) direct ref or fallback O(N)."""
        ref = self._direct_txts[idx] if idx < len(self._direct_txts) else None
        if ref is not None:
            try:
                from shiboken6 import isValid
                if isValid(ref) and ref.scene() is self.scene:
                    return ref
            except RuntimeError:
                pass
            self._direct_txts[idx] = None
        if self.txt_item_prp_list is not None and idx < len(self.txt_item_prp_list):
            return self.find_matching_txt_item(
                self.scene, self.txt_item_prp_list[idx])
        return None

    def _find_blk(self, idx):
        """Find block at idx: O(1) direct ref or fallback O(N)."""
        ref = self._direct_blks[idx] if idx < len(self._direct_blks) else None
        if ref is not None and ref in self.blk_list:
            return ref
        if idx < len(self._direct_blks):
            self._direct_blks[idx] = None
        return self.find_matching_blk(
            self.blk_list, self.blk_properties_list[idx])

    def redo(self):
        # Cattura proprietà (con toHtml()) PRIMA di rimuovere gli items
        self._ensure_txt_properties()
        # Abilita flag batch per sopprimere itemChange marker handling
        self.scene._batch_removing = True
        try:
            for i in range(len(self.rect_properties_list)):
                matching_rect = self._find_rect(i)
                if matching_rect:
                    remove_polygon_overlay(matching_rect, self.viewer)
                    self.scene.removeItem(matching_rect)
                    self.viewer.rectangles.remove(matching_rect)
            self.viewer.selected_rect = None

            # Raccogli items da rimuovere da selected_text_items (batch O(N))
            to_deselect = []
            for i in range(len(self.txt_item_prp_list)):
                matching_txt = self._find_txt(i)
                if matching_txt:
                    self.scene.removeItem(matching_txt)
                    self.viewer.text_items.remove(matching_txt)
                    to_deselect.append(matching_txt)
            if to_deselect and hasattr(self.ct, "selected_text_items"):
                deselect_set = set(id(x) for x in to_deselect)
                self.ct.selected_text_items = [
                    x for x in self.ct.selected_text_items
                    if id(x) not in deselect_set]
        finally:
            self.scene._batch_removing = False

        for i in range(len(self.blk_properties_list)):
            matching_blk = self._find_blk(i)
            if matching_blk:
                self.blk_list.remove(matching_blk)

        self.ct.curr_tblock_item = None
        self.ct.curr_tblock = None

        if self._defer_update:
            QTimer.singleShot(
                0, lambda: _deferred_markers_update(self.viewer, self.scene)
            )
        else:
            self.viewer.renumber_incremental_markers()

    def undo(self):
        # Cattura proprietà se non ancora fatto (es. undo senza redo previo)
        self._ensure_txt_properties()
        for rect_prp in self.rect_properties_list:
            if not self.find_matching_rect(self.scene, rect_prp):
                rect_item = self.create_rect_item(rect_prp, self.viewer.photo)
                self.viewer.connect_rect_item.emit(rect_item)
                self.viewer.rectangles.append(rect_item)

        for blk_prp in self.blk_properties_list:
            if not self.find_matching_blk(self.blk_list, blk_prp):
                blk = self.create_new_blk(blk_prp)
                self.blk_list.append(blk)

        for txt_prp in self.txt_item_prp_list:
            if not self.find_matching_txt_item(self.scene, txt_prp):
                text_item = self.create_new_txt_item(txt_prp, self.viewer.photo)
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
        self.scene.update()
