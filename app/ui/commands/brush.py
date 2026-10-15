from typing import List, TypedDict
from PySide6.QtGui import QUndoCommand, QColor
from PySide6.QtWidgets import QGraphicsPathItem
from .base import PathCommandBase, PathProperties

class AdvancedPathProperties(PathProperties):
    """Estende PathProperties per includere proprietà del pennello avanzato"""
    advanced_brush: bool
    brush_opacity: int  # 0-100
    original_color: str  # Colore originale senza opacità applicata

class BrushStrokeCommand(QUndoCommand, PathCommandBase):
    def __init__(self, viewer, path_item: QGraphicsPathItem):
        super().__init__()
        self.viewer = viewer
        self.scene = viewer._scene
        self.properties = self.save_path_properties(path_item)


    def redo(self):
        if not self.find_matching_item(self.scene, self.properties):
            path_item = self.create_path_item(self.properties)
            self.scene.addItem(path_item)
            self.scene.update()

    def undo(self):
        matching_item = self.find_matching_item(self.scene, self.properties)
        if matching_item:
            self.scene.removeItem(matching_item)
            self.scene.update()

class AdvancedBrushStrokeCommand(QUndoCommand, PathCommandBase):
    """Comando per gestire i tratti del pennello avanzato con proprietà estese"""
    
    def __init__(self, viewer, path_item: QGraphicsPathItem, advanced_properties=None):
        super().__init__()
        self.viewer = viewer
        self.scene = viewer._scene
        self.properties = self.save_advanced_path_properties(path_item, advanced_properties)
    
    def save_advanced_path_properties(self, path_item, advanced_properties=None) -> AdvancedPathProperties:
        """Salva le proprietà del path item includendo quelle avanzate"""
        base_properties = self.save_path_properties(path_item)
        
        # Aggiungi proprietà avanzate
        advanced_props = {
            'advanced_brush': advanced_properties.get('advanced_brush', False) if advanced_properties else False,
            'brush_opacity': advanced_properties.get('brush_opacity', 100) if advanced_properties else 100,
            'original_color': advanced_properties.get('original_color', base_properties['pen']) if advanced_properties else base_properties['pen']
        }
        
        # Combina le proprietà base con quelle avanzate
        return {**base_properties, **advanced_props}
    
    def create_advanced_path_item(self, properties: AdvancedPathProperties):
        """Crea un path item con proprietà avanzate"""
        path_item = self.create_path_item(properties)
        
        # Se è un pennello avanzato, applica le proprietà specifiche
        if properties.get('advanced_brush', False):
            # Applica l'opacità al colore
            original_color = QColor(properties['original_color'])
            opacity = properties.get('brush_opacity', 100)
            original_color.setAlpha(int(255 * opacity / 100))
            
            pen = path_item.pen()
            pen.setColor(original_color)
            path_item.setPen(pen)
        
        return path_item
    
    def find_advanced_matching_item(self, scene, properties: AdvancedPathProperties):
        """Trova un item che corrisponde alle proprietà avanzate"""
        for item in scene.items():
            if isinstance(item, QGraphicsPathItem):
                if (item.path() == properties['path'] and
                    item.pen().width() == properties['width']):
                    # Per il pennello avanzato, confronta anche l'opacità
                    if properties.get('advanced_brush', False):
                        item_alpha = item.pen().color().alpha()
                        expected_alpha = int(255 * properties.get('brush_opacity', 100) / 100)
                        if abs(item_alpha - expected_alpha) <= 5:  # Tolleranza per arrotondamenti
                            return item
                    else:
                        # Confronto standard per pennello normale
                        if (item.pen().color().name(QColor.HexArgb) == properties['pen'] and
                            item.brush().color().name(QColor.HexArgb) == properties['brush']):
                            return item
        return None
    
    def redo(self):
        if not self.find_advanced_matching_item(self.scene, self.properties):
            path_item = self.create_advanced_path_item(self.properties)
            self.scene.addItem(path_item)
            self.scene.update()
    
    def undo(self):
        matching_item = self.find_advanced_matching_item(self.scene, self.properties)
        if matching_item:
            self.scene.removeItem(matching_item)
            self.scene.update()

class SegmentBoxesCommand(QUndoCommand, PathCommandBase):
    def __init__(self, viewer, path_items: List[QGraphicsPathItem]):
        super().__init__()
        self.viewer = viewer
        self.scene = viewer._scene
        self.properties_list = [self.save_path_properties(item) for item in path_items]

    def redo(self):
        for properties in self.properties_list:
            if not self.find_matching_item(self.scene, properties):
                path_item = self.create_path_item(properties)
                self.scene.addItem(path_item)
        self.scene.update()

    def undo(self):
        for properties in self.properties_list:
            item = self.find_matching_item(self.scene, properties)
            if item:
                self.scene.removeItem(item)
        self.scene.update()

class ClearBrushStrokesCommand(QUndoCommand, PathCommandBase):
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.scene = viewer._scene
        self.properties_list = []

    def redo(self):
        self.properties_list = []
        for item in self.scene.items():
            if isinstance(item, QGraphicsPathItem) and item != self.viewer.photo:
                self.properties_list.append(self.save_path_properties(item))
                self.scene.removeItem(item)
        self.scene.update()
        
    def undo(self):
        for properties in self.properties_list:
            path_item = self.create_path_item(properties)
            self.scene.addItem(path_item)
        self.scene.update()
        
class EraseUndoCommand(QUndoCommand, PathCommandBase):
    def __init__(self, viewer, before_erase: PathProperties, after_erase: PathProperties):
        super().__init__()
        self.viewer = viewer
        self.scene = viewer._scene
        self.before_erase = before_erase
        self.after_erase = after_erase
        self.first = True

    def redo(self):
        if self.first:
            self.first = False
            return
        self.update_scene(self.after_erase)

    def undo(self):
        self.update_scene(self.before_erase)

    def update_scene(self, properties_list):
        items_to_remove = [
            item for item in self.scene.items() 
            if isinstance(item, QGraphicsPathItem) and item != self.viewer.photo
        ]
        for item in items_to_remove:
            self.scene.removeItem(item)

        for properties in properties_list:
            path_item = self.create_path_item(properties)
            self.scene.addItem(path_item)

        self.scene.update()
