from PySide6.QtGui import QUndoCommand
from .base import RectCommandBase

class MultipleTextFormatCommand(QUndoCommand, RectCommandBase):
    def __init__(self, viewer, old_items, new_items):
        super().__init__()
        self.scene = viewer._scene
        self.old_items_data = []
        self.new_items_data = []
        
        # Salva i dati degli elementi vecchi e nuovi
        for old_item, new_item in zip(old_items, new_items):
            old_data = {
                'dict': old_item.__dict__.copy(),
                'properties': self.save_txt_item_properties(old_item),
                'html': old_item.toHtml()
            }
            new_data = {
                'dict': new_item.__dict__.copy(),
                'properties': self.save_txt_item_properties(new_item),
                'html': new_item.toHtml()
            }
            self.old_items_data.append(old_data)
            self.new_items_data.append(new_data)

    def redo(self):
        for old_data, new_data in zip(self.old_items_data, self.new_items_data):
            matching_item = self.find_matching_txt_item(self.scene, old_data['properties'])
            if matching_item:
                matching_item.set_text(new_data['html'], new_data['properties']['width'])
                matching_item.__dict__.update(new_data['dict'])
                matching_item.update()

    def undo(self):
        for old_data, new_data in zip(self.old_items_data, self.new_items_data):
            matching_item = self.find_matching_txt_item(self.scene, new_data['properties'])
            if matching_item:
                matching_item.set_text(old_data['html'], old_data['properties']['width'])
                matching_item.__dict__.update(old_data['dict'])
                matching_item.update()