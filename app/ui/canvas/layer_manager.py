"""
Layer Manager Module

Gestisce la gerarchia dei layer nell'applicazione paint-style.
Ogni elemento (caselle di testo, disegni pennello, forme) è memorizzato
come layer indipendente con un ordine di sovrapposizione definito.
"""

from enum import Enum, auto
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
import json
import copy

from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsItem, QGraphicsPathItem,
    QGraphicsTextItem, QGraphicsRectItem, QGraphicsPixmapItem
)
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QPainterPath, QPen, QBrush, QColor
from .z_layers import (
    BACKGROUND_Z,
    BRUSH_STROKE_Z,
    HANDLE_LAYER_DEFAULT,
    IMPORTED_SHAPE_LAYER_DEFAULT,
    TEXT_BOX_Z,
)


class LayerType(Enum):
    """Tipi di layer supportati."""
    BACKGROUND = auto()      # Layer di sfondo (immagine)
    BRUSH_STROKE = auto()    # Tratti di pennello/disegno
    TEXT_BOX = auto()        # Caselle di testo
    SHAPE = auto()           # Forme geometriche
    OVERLAY = auto()         # Elementi overlay (marker, UI)


@dataclass
class LayerState:
    """Stato serializzabile di un layer."""
    layer_id: str
    layer_type: str
    z_index: float
    visible: bool
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Converte lo stato in dizionario."""
        return {
            'layer_id': self.layer_id,
            'layer_type': self.layer_type,
            'z_index': self.z_index,
            'visible': self.visible,
            'properties': self.properties
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LayerState':
        """Crea uno stato da dizionario."""
        return cls(
            layer_id=data['layer_id'],
            layer_type=data['layer_type'],
            z_index=data['z_index'],
            visible=data['visible'],
            properties=data.get('properties', {})
        )


class Layer:
    """
    Rappresenta un singolo layer nella scena.
    """
    
    def __init__(
        self,
        layer_id: str,
        layer_type: LayerType,
        graphics_item: QGraphicsItem,
        z_index: float = 0.0,
        name: str = ""
    ):
        self.layer_id = layer_id
        self.layer_type = layer_type
        self.graphics_item = graphics_item
        self.z_index = z_index
        self.name = name or f"{layer_type.name}_{layer_id[:8]}"
        self.visible = True
        self.metadata: Dict[str, Any] = {}
        
        # Applica lo z-index all'item grafico
        self._apply_z_index()
    
    def _apply_z_index(self):
        """Applica il valore z-index all'item grafico."""
        if self.graphics_item:
            self.graphics_item.setZValue(self.z_index)
    
    def set_z_index(self, z_index: float):
        """Imposta un nuovo valore z-index."""
        self.z_index = z_index
        self._apply_z_index()
    
    def set_visible(self, visible: bool):
        """Imposta la visibilità del layer."""
        self.visible = visible
        if self.graphics_item:
            self.graphics_item.setVisible(visible)
    
    def bring_to_front(self):
        """Porta il layer in primo piano."""
        self.z_index = float('inf')
        self._apply_z_index()
    
    def send_to_back(self):
        """Manda il layer in secondo piano."""
        self.z_index = float('-inf')
        self._apply_z_index()
    
    def get_state(self) -> LayerState:
        """Restituisce lo stato serializzabile del layer."""
        # Estrai proprietà specifiche in base al tipo
        properties = self._extract_properties()
        
        return LayerState(
            layer_id=self.layer_id,
            layer_type=self.layer_type.name,
            z_index=self.z_index,
            visible=self.visible,
            properties=properties
        )
    
    def _extract_properties(self) -> Dict[str, Any]:
        """Estrae le proprietà specifiche del tipo di layer."""
        properties = {}
        
        if isinstance(self.graphics_item, QGraphicsPathItem):
            # Salva le proprietà del path
            path = self.graphics_item.path()
            pen = self.graphics_item.pen()
            brush = self.graphics_item.brush()
            
            properties['path_data'] = self._path_to_data(path)
            properties['pen_color'] = pen.color().name(Qt.ColorSpec.HexArgb)
            properties['pen_width'] = pen.width()
            properties['brush_color'] = brush.color().name(Qt.ColorSpec.HexArgb)
            
        elif isinstance(self.graphics_item, QGraphicsTextItem):
            # Salva le proprietà del testo
            properties['text'] = self.graphics_item.toPlainText()
            properties['font_family'] = self.graphics_item.font().family()
            properties['font_size'] = self.graphics_item.font().pointSize()
            
        elif isinstance(self.graphics_item, QGraphicsRectItem):
            # Salva le proprietà del rettangolo
            rect = self.graphics_item.rect()
            properties['rect'] = [rect.x(), rect.y(), rect.width(), rect.height()]
            pen = self.graphics_item.pen()
            brush = self.graphics_item.brush()
            properties['pen_color'] = pen.color().name()
            properties['brush_color'] = brush.color().name()
        
        return properties
    
    def _path_to_data(self, path: QPainterPath) -> List[Dict]:
        """Converte un QPainterPath in dati serializzabili."""
        elements = []
        for i in range(path.elementCount()):
            elem = path.elementAt(i)
            elements.append({
                'type': elem.type,
                'x': elem.x,
                'y': elem.y
            })
        return elements


class LayerManager(QObject):
    """
    Gestisce tutti i layer della scena.
    Mantiene l'ordine di sovrapposizione e garantisce la persistenza dei dati.
    """
    
    # Segnali
    layer_added = Signal(str)  # layer_id
    layer_removed = Signal(str)  # layer_id
    layer_updated = Signal(str)  # layer_id
    layer_order_changed = Signal()
    state_restored = Signal()
    
    def __init__(self, scene: QGraphicsScene):
        super().__init__()
        self._scene = scene
        self._layers: Dict[str, Layer] = {}
        self._ordered_ids: List[str] = []
        self._id_counter = 0
        
        # Valori canonici: vedi tabella tecnica in z_layers.py
        self._default_z_values = {
            LayerType.BACKGROUND: BACKGROUND_Z,
            LayerType.BRUSH_STROKE: BRUSH_STROKE_Z,
            LayerType.TEXT_BOX: TEXT_BOX_Z,
            LayerType.SHAPE: IMPORTED_SHAPE_LAYER_DEFAULT,
            LayerType.OVERLAY: HANDLE_LAYER_DEFAULT,
        }
        
        # Storia degli stati per undo/redo
        self._state_history: List[List[LayerState]] = []
        self._history_index = -1
        self._max_history = 50
    
    def _generate_id(self) -> str:
        """Genera un ID univoco per il layer."""
        self._id_counter += 1
        return f"layer_{self._id_counter}_{id(self)}"
    
    def add_layer(
        self,
        graphics_item: QGraphicsItem,
        layer_type: LayerType,
        z_index: Optional[float] = None,
        name: str = "",
        layer_id: Optional[str] = None
    ) -> str:
        """
        Aggiunge un nuovo layer alla scena.
        
        Args:
            graphics_item: L'item grafico Qt da gestire
            layer_type: Il tipo di layer
            z_index: Valore z-index personalizzato (opzionale)
            name: Nome descrittivo del layer
            layer_id: ID personalizzato (opzionale)
            
        Returns:
            L'ID del layer creato
        """
        # Genera ID se non fornito
        if layer_id is None:
            layer_id = self._generate_id()
        
        # Determina lo z-index
        if z_index is None:
            z_index = self._default_z_values.get(layer_type, 0.0)
            # Aggiungi un offset basato sull'ordine per evitare sovrapposizioni
            z_index += len(self._layers) * 0.01
        
        # Crea il layer
        layer = Layer(
            layer_id=layer_id,
            layer_type=layer_type,
            graphics_item=graphics_item,
            z_index=z_index,
            name=name
        )
        
        # Aggiungi alla scena se non è già presente
        if graphics_item.scene() != self._scene:
            self._scene.addItem(graphics_item)
        
        # Registra il layer
        self._layers[layer_id] = layer
        self._ordered_ids.append(layer_id)
        
        # Ordina i layer per z-index
        self._sort_layers()
        
        # Emetti segnale
        self.layer_added.emit(layer_id)
        
        return layer_id
    
    def remove_layer(self, layer_id: str) -> bool:
        """
        Rimuove un layer dalla scena.
        
        Args:
            layer_id: L'ID del layer da rimuovere
            
        Returns:
            True se il layer è stato rimosso, False altrimenti
        """
        if layer_id not in self._layers:
            return False
        
        layer = self._layers[layer_id]
        
        # Rimuovi l'item dalla scena
        if layer.graphics_item and layer.graphics_item.scene():
            layer.graphics_item.scene().removeItem(layer.graphics_item)
        
        # Rimuovi dai registri
        del self._layers[layer_id]
        if layer_id in self._ordered_ids:
            self._ordered_ids.remove(layer_id)
        
        # Emetti segnale
        self.layer_removed.emit(layer_id)
        
        return True
    
    def get_layer(self, layer_id: str) -> Optional[Layer]:
        """Restituisce un layer dato il suo ID."""
        return self._layers.get(layer_id)
    
    def get_all_layers(self) -> List[Layer]:
        """Restituisce tutti i layer ordinati per z-index."""
        return [self._layers[layer_id] for layer_id in self._ordered_ids]
    
    def get_layers_by_type(self, layer_type: LayerType) -> List[Layer]:
        """Restituisce tutti i layer di un determinato tipo."""
        return [
            layer for layer in self._layers.values()
            if layer.layer_type == layer_type
        ]
    
    def get_layer_for_item(self, graphics_item: QGraphicsItem) -> Optional[Layer]:
        """Trova il layer associato a un item grafico."""
        for layer in self._layers.values():
            if layer.graphics_item == graphics_item:
                return layer
        return None
    
    def update_layer_z_index(self, layer_id: str, new_z_index: float):
        """Aggiorna lo z-index di un layer."""
        layer = self._layers.get(layer_id)
        if layer:
            layer.set_z_index(new_z_index)
            self._sort_layers()
            self.layer_updated.emit(layer_id)
    
    def _sort_layers(self):
        """Ordina i layer per z-index crescente."""
        self._ordered_ids.sort(
            key=lambda layer_id: self._layers[layer_id].z_index
        )
    
    def bring_to_front(self, layer_id: str):
        """Porta un layer in primo piano."""
        max_z = max(
            (layer.z_index for layer in self._layers.values()),
            default=0.0
        )
        self.update_layer_z_index(layer_id, max_z + 1.0)
    
    def send_to_back(self, layer_id: str):
        """Manda un layer in secondo piano."""
        min_z = min(
            (layer.z_index for layer in self._layers.values()),
            default=0.0
        )
        self.update_layer_z_index(layer_id, min_z - 1.0)
    
    def save_state(self) -> List[LayerState]:
        """
        Salva lo stato corrente di tutti i layer.
        Restituisce una lista di LayerState ordinata per z-index.
        """
        states = []
        for layer_id in self._ordered_ids:
            layer = self._layers[layer_id]
            states.append(layer.get_state())
        return states
    
    def restore_state(self, states: List[LayerState]):
        """
        Ripristina lo stato dei layer da una lista di LayerState.
        """
        # Prima rimuovi tutti i layer esistenti
        for layer_id in list(self._layers.keys()):
            self.remove_layer(layer_id)
        
        # Ripristina ogni layer
        for state in states:
            # Qui dovresti creare il graphics_item appropriato
            # in base al tipo e alle proprietà salvate
            # Per ora, creiamo solo la struttura
            pass
        
        self.state_restored.emit()
    
    def push_history(self):
        """Salva lo stato corrente nella storia per undo/redo."""
        # Rimuovi gli stati futuri se siamo in mezzo alla storia
        if self._history_index < len(self._state_history) - 1:
            self._state_history = self._state_history[:self._history_index + 1]
        
        # Aggiungi il nuovo stato
        self._state_history.append(self.save_state())
        self._history_index += 1
        
        # Limita la dimensione della storia
        if len(self._state_history) > self._max_history:
            self._state_history.pop(0)
            self._history_index -= 1
    
    def undo(self) -> bool:
        """Annulla l'ultima operazione."""
        if self._history_index > 0:
            self._history_index -= 1
            self.restore_state(self._state_history[self._history_index])
            return True
        return False
    
    def redo(self) -> bool:
        """Ripristina l'operazione annullata."""
        if self._history_index < len(self._state_history) - 1:
            self._history_index += 1
            self.restore_state(self._state_history[self._history_index])
            return True
        return False


class LayerGroup:
    """
    Raggruppa più layer per operazioni batch.
    """
    
    def __init__(self, layer_manager: LayerManager, name: str = ""):
        self.layer_manager = layer_manager
        self.name = name
        self.layer_ids: List[str] = []
    
    def add_layer(self, layer_id: str):
        """Aggiunge un layer al gruppo."""
        if layer_id not in self.layer_ids:
            self.layer_ids.append(layer_id)
    
    def remove_layer(self, layer_id: str):
        """Rimuove un layer dal gruppo."""
        if layer_id in self.layer_ids:
            self.layer_ids.remove(layer_id)
    
    def set_z_index(self, z_index: float):
        """Imposta lo stesso z-index per tutti i layer del gruppo."""
        for layer_id in self.layer_ids:
            self.layer_manager.update_layer_z_index(layer_id, z_index)
    
    def offset_z_index(self, offset: float):
        """Sposta tutti i layer del gruppo di un offset z."""
        for layer_id in self.layer_ids:
            layer = self.layer_manager.get_layer(layer_id)
            if layer:
                new_z = layer.z_index + offset
                self.layer_manager.update_layer_z_index(layer_id, new_z)
    
    def bring_to_front(self):
        """Porta tutti i layer del gruppo in primo piano."""
        for layer_id in self.layer_ids:
            self.layer_manager.bring_to_front(layer_id)
    
    def send_to_back(self):
        """Manda tutti i layer del gruppo in secondo piano."""
        for layer_id in self.layer_ids:
            self.layer_manager.send_to_back(layer_id)
