"""
Layer Preservation Module

Gestisce la persistenza dei disegni durante il ridimensionamento
delle caselle di testo. Mantiene lo stato dei layer brush durante
le operazioni di resize/move.
"""

from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum, auto

from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem, QGraphicsScene
from PySide6.QtCore import QPointF, QRectF, Qt  # Qt serve in _create_brush_snapshot e _restore_brush_strokes
from PySide6.QtGui import QPainterPath, QPen, QBrush, QColor  # QColor usato in _create_brush_snapshot

from .brush_layer_rules import apply_brush_stroke_layer


class LayerOperation(Enum):
    """Tipi di operazioni sui layer che richiedono preservazione."""
    RESIZE = auto()
    MOVE = auto()
    ROTATE = auto()
    SCALE = auto()


@dataclass
class BrushStrokeSnapshot:
    """Snapshot di un tratto di pennello per ripristino."""
    path_data: Any  # Dati serializzabili del path
    pen: Dict[str, Any]  # Proprietà della penna
    brush: Dict[str, Any]  # Proprietà del brush
    z_index: float
    position: QPointF
    # Riferimento all'item grafico originale. Permette di NON ricreare un
    # item duplicato quando l'originale è ancora vivo in scena.
    source_item: Any = None


@dataclass 
class LayerSnapshot:
    """Snapshot dello stato dei layer per un'area specifica."""
    timestamp: float
    operation: LayerOperation
    affected_rect: QRectF
    brush_strokes: List[BrushStrokeSnapshot] = field(default_factory=list)
    other_items: List[Dict] = field(default_factory=list)


class LayerPreserveManager:
    """
    Gestisce la preservazione dei layer durante operazioni di trasformazione.
    Mantiene i disegni brush visibili durante resize/move delle caselle di testo.
    """
    
    def __init__(self, scene: QGraphicsScene):
        self._scene = scene
        self._snapshots: List[LayerSnapshot] = []
        self._max_snapshots = 10
        self._active_operation: Optional[LayerOperation] = None
        self._temp_items: List[QGraphicsItem] = []
        
    def begin_operation(self, operation: LayerOperation, affected_rect: QRectF) -> LayerSnapshot:
        """
        Inizia un'operazione che richiede preservazione dei layer.
        Crea uno snapshot dello stato attuale.
        
        Args:
            operation: Tipo di operazione
            affected_rect: Area interessata dall'operazione
            
        Returns:
            Lo snapshot creato
        """
        import time
        
        self._active_operation = operation
        
        # Crea lo snapshot
        snapshot = LayerSnapshot(
            timestamp=time.time(),
            operation=operation,
            affected_rect=affected_rect,
            brush_strokes=self._capture_brush_strokes(affected_rect),
            other_items=self._capture_other_items(affected_rect)
        )
        
        # Salva lo snapshot
        self._snapshots.append(snapshot)
        
        # Limita il numero di snapshot
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots.pop(0)
        
        return snapshot
    
    def end_operation(self, restore_brush_strokes: bool = True) -> bool:
        """
        Termina l'operazione attiva e opzionalmente ripristina i brush strokes.
        
        Args:
            restore_brush_strokes: Se True, ripristina i brush strokes catturati
            
        Returns:
            True se l'operazione è stata completata con successo
        """
        if self._active_operation is None:
            return False
        
        # Rimuovi items temporanei
        self._clear_temp_items()
        
        if restore_brush_strokes and self._snapshots:
            latest_snapshot = self._snapshots[-1]
            self._restore_brush_strokes(latest_snapshot.brush_strokes)
        
        self._active_operation = None
        return True
    
    def preserve_during_resize(
        self, 
        resize_rect: QRectF,
        resize_callback: Callable,
        *callback_args,
        **callback_kwargs
    ) -> Any:
        """
        Esegue un'operazione di resize preservando i layer brush.
        
        Args:
            resize_rect: Rettangolo dell'area di resize
            resize_callback: Funzione da chiamare per eseguire il resize
            *callback_args: Argomenti posizionali per la callback
            **callback_kwargs: Argomenti keyword per la callback
            
        Returns:
            Il risultato della callback
        """
        # Inizia l'operazione di preservazione
        self.begin_operation(LayerOperation.RESIZE, resize_rect)
        
        try:
            # Esegui il resize
            result = resize_callback(*callback_args, **callback_kwargs)
            
            # Ripristina i brush strokes
            self.end_operation(restore_brush_strokes=True)
            
            return result
        except Exception as e:
            # In caso di errore, termina l'operazione senza ripristinare
            self.end_operation(restore_brush_strokes=False)
            raise e
    
    def _capture_brush_strokes(self, rect: QRectF) -> List[BrushStrokeSnapshot]:
        """
        Cattura tutti i brush strokes nell'area specificata.
        
        Args:
            rect: Area di interesse
            
        Returns:
            Lista di snapshot dei brush strokes
        """
        snapshots = []
        
        for item in self._scene.items(rect):
            if isinstance(item, QGraphicsPathItem):
                # Questo è un brush stroke
                snapshot = self._create_brush_snapshot(item)
                if snapshot:
                    snapshots.append(snapshot)
        
        return snapshots
    
    def _create_brush_snapshot(self, item: QGraphicsPathItem) -> Optional[BrushStrokeSnapshot]:
        """
        Crea uno snapshot di un brush stroke.
        
        Args:
            item: L'item brush stroke
            
        Returns:
            Lo snapshot o None se non valido
        """
        try:
            path = item.path()
            pen = item.pen()
            brush = item.brush()
            
            # Serializza il path
            path_data = self._serialize_path(path)
            
            # Serializza pen e brush
            pen_data = {
                # Qt.ColorSpec NON esiste in PySide6 >= 6.11: il tipo corretto
                # e' QColor.HexArgb (QtGui). Con quello la cattura dei tratti
                # sollevava AttributeError e la preservazione non funzionava.
                'color': pen.color().name(QColor.HexArgb),
                'width': pen.width(),
                'style': pen.style().value if hasattr(pen.style(), 'value') else int(pen.style()),
                'cap': pen.capStyle().value if hasattr(pen.capStyle(), 'value') else int(pen.capStyle()),
                'join': pen.joinStyle().value if hasattr(pen.joinStyle(), 'value') else int(pen.joinStyle())
            }
            
            brush_data = {
                'color': brush.color().name(QColor.HexArgb),
                'style': brush.style().value if hasattr(brush.style(), 'value') else int(brush.style())
            }
            
            return BrushStrokeSnapshot(
                path_data=path_data,
                pen=pen_data,
                brush=brush_data,
                z_index=item.zValue(),
                position=item.pos(),
                source_item=item
            )
        except Exception as e:
            # Log l'errore ma non bloccare
            print(f"Error creating brush snapshot: {e}")
            return None
    
    def _serialize_path(self, path) -> List[Dict]:
        """
        Serializza un QPainterPath in una lista di elementi.
        
        Args:
            path: Il QPainterPath da serializzare
            
        Returns:
            Lista di dizionari rappresentanti gli elementi del path
        """
        elements = []
        for i in range(path.elementCount()):
            elem = path.elementAt(i)
            # NON usare int(elem.type): in PySide6 >= 6.9 le enum non
            # supportano piu' int(), quindi _serialize_path sollevava sempre
            # TypeError, la cattura del tratto falliva e l'intera
            # preservazione dei brush durante il resize non funzionava MAI.
            elem_type = elem.type
            elements.append({
                'type': elem_type.value if hasattr(elem_type, 'value') else int(elem_type),
                'x': float(elem.x),
                'y': float(elem.y)
            })
        return elements
    
    def _deserialize_path(self, path_data: List[Dict]) -> QPainterPath:
        """
        Deserializza una lista di elementi in un QPainterPath.
        
        Args:
            path_data: Lista di dizionari degli elementi
            
        Returns:
            Il QPainterPath ricostruito
        """
        from PySide6.QtGui import QPainterPath
        
        path = QPainterPath()
        for i, elem in enumerate(path_data):
            elem_type = elem.get('type', 0)
            x = elem.get('x', 0.0)
            y = elem.get('y', 0.0)
            
            if i == 0 or elem_type == 0:  # MoveToElement
                path.moveTo(x, y)
            elif elem_type == 1:  # LineToElement
                path.lineTo(x, y)
            elif elem_type == 2:  # CurveToElement
                # Per gli elementi curva, abbiamo bisogno di 3 punti
                # ma in questa serializzazione semplificata, trattiamo come linea
                path.lineTo(x, y)
            elif elem_type == 3:  # CurveToDataElement
                # Ignorato in questa implementazione semplificata
                pass
        
        return path
    
    def _restore_brush_strokes(self, snapshots: List[BrushStrokeSnapshot]):
        """
        Ripristina i brush strokes dallo snapshot.
        
        Args:
            snapshots: Lista di snapshot dei brush strokes
        """
        from PySide6.QtGui import QPainterPath, QPen, QBrush, QColor
        from PySide6.QtCore import Qt
        
        for snapshot in snapshots:
            try:
                # Se l'item ORIGINALE è ancora vivo nella scena non va
                # ricreato: il resize non lo tocca ne' lo rimuove, quindi
                # ricrearlo aggiungeva una copia identica sopra l'originale.
                # Prima ogni resize ricreava TUTTI i tratti: la scena
                # cresceva di N item a ogni operazione e i tratti venivano
                # disegnati N volte sovrapponendosi.
                original = getattr(snapshot, "source_item", None)
                if original is not None:
                    try:
                        if original.scene() is not None:
                            continue  # già presente: niente da fare
                    except RuntimeError:
                        # C++ object already deleted: procedo a ricrearlo
                        pass

                # Ricostruisci il path
                path = self._deserialize_path(snapshot.path_data)
                
                # Ricostruisci pen e brush
                pen_color = QColor(snapshot.pen['color'])
                pen = QPen(
                    pen_color,
                    snapshot.pen['width'],
                    Qt.PenStyle(snapshot.pen.get('style', 1)),
                    Qt.PenCapStyle(snapshot.pen.get('cap', 32)),
                    Qt.PenJoinStyle(snapshot.pen.get('join', 64))
                )
                
                brush_color = QColor(snapshot.brush['color'])
                brush = QBrush(
                    brush_color,
                    Qt.BrushStyle(snapshot.brush.get('style', 1))
                )
                
                # Crea il nuovo item
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                item.setBrush(brush)
                apply_brush_stroke_layer(item)
                item.setPos(snapshot.position)
                
                # Aggiungi alla scena
                self._scene.addItem(item)
                
                # Aggiungi alla lista items temporanei per tracking
                self._temp_items.append(item)
                
            except Exception as e:
                print(f"Error restoring brush stroke: {e}")
                continue
    
    def _capture_other_items(self, rect: QRectF) -> List[Dict]:
        """
        Cattura altri items nell'area (non brush strokes).
        
        Args:
            rect: Area di interesse
            
        Returns:
            Lista di dizionari con le proprietà degli items
        """
        items_data = []
        
        for item in self._scene.items(rect):
            if isinstance(item, QGraphicsPathItem):
                # Già gestito dai brush strokes
                continue
            
            # Cattura le proprietà generiche
            item_data = {
                'type': type(item).__name__,
                'z_value': item.zValue(),
                'pos': {'x': item.pos().x(), 'y': item.pos().y()},
                'visible': item.isVisible()
            }
            
            items_data.append(item_data)
        
        return items_data
    
    def _clear_temp_items(self):
        """Rimuove gli items temporanei creati durante l'operazione."""
        for item in self._temp_items:
            try:
                if item.scene():
                    item.scene().removeItem(item)
            except Exception:
                pass
        self._temp_items.clear()
    
    def get_active_operation(self) -> Optional[LayerOperation]:
        """Restituisce l'operazione attiva in corso."""
        return self._active_operation
    
    def is_preserving(self) -> bool:
        """Restituisce True se c'è un'operazione di preservazione attiva."""
        return self._active_operation is not None
    
    def cancel_operation(self):
        """Cancella l'operazione attiva senza ripristinare."""
        self._clear_temp_items()
        self._active_operation = None
