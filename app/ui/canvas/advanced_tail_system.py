"""Sistema avanzato per il posizionamento personalizzabile del corno delle forme.

Questo modulo implementa un sistema avanzato che permette il posizionamento
preciso e personalizzabile del corno (tail) delle forme lungo il perimetro,
con controlli interattivi e feedback visivo.
"""

import math
from enum import Enum
from typing import Tuple, Optional, Dict, Any
from PySide6 import QtCore, QtGui, QtWidgets


class AnchorType(Enum):
    """Tipi di ancoraggio per il corno delle forme."""
    PARAMETRIC = "parametric"  # Posizionamento lungo il perimetro (0.0-1.0)
    ABSOLUTE = "absolute"      # Posizione assoluta in coordinate
    RELATIVE = "relative"      # Posizione relativa al centro


class TailConfiguration:
    """Configurazione semplificata per il posizionamento del corno delle forme.
    
    Questa classe gestisce solo i parametri essenziali:
    - Posizione lungo il perimetro della forma
    - Angolo del corno
    - Lunghezza del corno
    """
    
    def __init__(self, 
                 perimeter_position: float = 0.5,
                 angle: float = 45.0,
                 length: float = 30.0,
                 legacy_direction: str = "bottom"):
        """
        Inizializza la configurazione del corno.
        
        Args:
            perimeter_position: Posizione lungo il perimetro (0.0-1.0)
            angle: Angolo del corno in gradi
            length: Lunghezza del corno
            legacy_direction: Direzione legacy per compatibilità
        """
        self._perimeter_position = max(0.0, min(1.0, perimeter_position))
        self._angle = angle
        self._length = max(5.0, length)
        self._legacy_direction = legacy_direction
        

        
    @property
    def perimeter_position(self) -> float:
        """Posizione lungo il perimetro (0.0-1.0)."""
        return self._perimeter_position
        
    @perimeter_position.setter
    def perimeter_position(self, value: float):
        self._perimeter_position = max(0.0, min(1.0, value))
        
    @property
    def angle(self) -> float:
        """Angolo del corno in gradi."""
        return self._angle
        
    @angle.setter
    def angle(self, value: float):
        self._angle = value
        
    @property
    def length(self) -> float:
        """Lunghezza del corno."""
        return self._length
        
    @length.setter
    def length(self, value: float):
        self._length = max(5.0, value)
        

        
    @property
    def legacy_direction(self) -> str:
        """Direzione legacy per compatibilità."""
        return self._legacy_direction
        
    @legacy_direction.setter
    def legacy_direction(self, value: str):
        if value in ['top', 'right', 'bottom', 'left']:
            self._legacy_direction = value
            

        
    def get_anchor_point(self, rect: QtCore.QRectF) -> QtCore.QPointF:
        """Calcola il punto di ancoraggio del corno sul perimetro della forma.
        
        Args:
            rect: Rettangolo della forma
            
        Returns:
            Punto di ancoraggio sul perimetro
        """
        # Usa sempre il sistema parametrico semplificato
        return self._get_parametric_anchor_point(rect)
            
    def _get_legacy_anchor_point(self, rect: QtCore.QRectF) -> QtCore.QPointF:
        """Calcola il punto di ancoraggio usando il sistema legacy."""
        if self._legacy_direction == 'bottom':
            return QtCore.QPointF(rect.center().x(), rect.bottom())
        elif self._legacy_direction == 'top':
            return QtCore.QPointF(rect.center().x(), rect.top())
        elif self._legacy_direction == 'right':
            return QtCore.QPointF(rect.right(), rect.center().y())
        elif self._legacy_direction == 'left':
            return QtCore.QPointF(rect.left(), rect.center().y())
        else:
            return QtCore.QPointF(rect.center().x(), rect.bottom())
            
    def _get_parametric_anchor_point(self, rect: QtCore.QRectF) -> QtCore.QPointF:
        """Calcola il punto di ancoraggio usando il posizionamento parametrico su circonferenza ellittica.
        
        Il perimetro viene parametrizzato da 0.0 a 1.0 lungo la circonferenza di un'ellisse
        che segue la forma SVG invece del perimetro rettangolare.
        """
        pos = self._perimeter_position
        
        # Calcola il centro e i raggi dell'ellisse
        center_x = rect.center().x()
        center_y = rect.center().y()
        radius_x = rect.width() / 2
        radius_y = rect.height() / 2
        
        # Converte la posizione parametrica (0.0-1.0) in angolo (0-2π)
        theta = pos * 2 * math.pi
        
        # Calcola il punto sulla circonferenza ellittica
        x = center_x + radius_x * math.cos(theta)
        y = center_y + radius_y * math.sin(theta)
        
        return QtCore.QPointF(x, y)
            
    def get_tail_tip_point(self, rect: QtCore.QRectF) -> QtCore.QPointF:
        """Calcola il punto finale (punta) del corno.
        
        Args:
            rect: Rettangolo della forma
            
        Returns:
            Punto finale del corno
        """
        anchor = self.get_anchor_point(rect)
        
        # Calcola la direzione del corno
        angle_rad = math.radians(self._angle)
        
        # Calcola il punto finale
        tip_x = anchor.x() + self._length * math.cos(angle_rad)
        tip_y = anchor.y() + self._length * math.sin(angle_rad)
        
        return QtCore.QPointF(tip_x, tip_y)
        
    def to_dict(self) -> Dict[str, Any]:
        """Converte la configurazione in un dizionario per la serializzazione."""
        return {
            'perimeter_position': self._perimeter_position,
            'angle': self._angle,
            'length': self._length,
            'legacy_direction': self._legacy_direction
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TailConfiguration':
        """Crea una configurazione da un dizionario."""
        return cls(
            perimeter_position=data.get('perimeter_position', 0.5),
            angle=data.get('angle', 45.0),
            length=data.get('length', 30.0),
            legacy_direction=data.get('legacy_direction', 'bottom')
        )
        
    def convert_from_legacy(self, direction: str, tail_size: float) -> None:
        """Converte una configurazione legacy nel nuovo sistema.
        
        Args:
            direction: Direzione legacy ('top', 'right', 'bottom', 'left')
            tail_size: Dimensione legacy del corno
        """
        self._legacy_direction = direction
        self._length = tail_size
        
        # Mappa la direzione legacy alla posizione parametrica sulla circonferenza ellittica
        direction_map = {
            'right': 0.0,     # 0° - lato destro dell'ellisse
            'bottom': 0.25,   # 90° - parte inferiore dell'ellisse
            'left': 0.5,      # 180° - lato sinistro dell'ellisse
            'top': 0.75       # 270° - parte superiore dell'ellisse
        }
        
        self._perimeter_position = direction_map.get(direction, 0.375)
        
        # Imposta l'angolo appropriato
        angle_map = {
            'right': 0,
            'bottom': 90,
            'left': 180,
            'top': 270
        }
        
        self._angle = angle_map.get(direction, 90)


class AdvancedTailRenderer:
    """Renderer semplificato per il disegno del corno del balloon.
    
    Questa classe gestisce il rendering del corno con supporto per:
    - Forme semplici e dirette
    - Compatibilità con il sistema legacy
    """
    
    def __init__(self, config: TailConfiguration):
        """
        Inizializza il renderer con una configurazione.
        
        Args:
            config: Configurazione del corno
        """
        self._config = config
        
    def create_tail_path(self, rect: QtCore.QRectF) -> QtGui.QPainterPath:
        """Crea il path del corno basato sulla configurazione.
        
        Args:
            rect: Rettangolo del balloon
            
        Returns:
            Path del corno da disegnare
        """
        return self._create_simple_tail_path(rect)
        
    def _create_simple_tail_path(self, rect: QtCore.QRectF) -> QtGui.QPainterPath:
        """Crea il path del corno usando il sistema semplificato."""
        path = QtGui.QPainterPath()
        
        # Ottieni i punti chiave
        anchor = self._config.get_anchor_point(rect)
        tip = self._config.get_tail_tip_point(rect)
        
        # Calcola la larghezza base del corno (proporzionale alla lunghezza)
        base_width = self._config.length * 0.3
        
        # Calcola il vettore direzione
        dx = tip.x() - anchor.x()
        dy = tip.y() - anchor.y()
        length = math.sqrt(dx*dx + dy*dy)
        
        if length == 0:
            return path
            
        # Normalizza il vettore direzione
        dx /= length
        dy /= length
        
        # Calcola il vettore perpendicolare
        perp_x = -dy
        perp_y = dx
        
        # Calcola i punti del corno
        base_half_width = base_width / 2
        
        # Punti alla base
        base_left = QtCore.QPointF(
            anchor.x() + perp_x * base_half_width,
            anchor.y() + perp_y * base_half_width
        )
        base_right = QtCore.QPointF(
            anchor.x() - perp_x * base_half_width,
            anchor.y() - perp_y * base_half_width
        )
        
        # Costruisci il path del triangolo
        path.moveTo(base_left)
        path.lineTo(tip)
        path.lineTo(base_right)
        path.closeSubpath()
        
        return path
        
    def get_bounding_rect(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        """Calcola il rettangolo contenente il corno.
        
        Args:
            rect: Rettangolo del balloon
            
        Returns:
            Rettangolo contenente il corno
        """
        anchor = self._config.get_anchor_point(rect)
        tip = self._config.get_tail_tip_point(rect)
        
        # Calcola la larghezza base del corno
        base_width = self._config.length * 0.3
        
        # Calcola il rettangolo contenente anchor e tip
        min_x = min(anchor.x(), tip.x()) - base_width / 2
        max_x = max(anchor.x(), tip.x()) + base_width / 2
        min_y = min(anchor.y(), tip.y()) - base_width / 2
        max_y = max(anchor.y(), tip.y()) + base_width / 2
        
        return QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)



class TailHandleManager:
    """Gestore semplificato degli handle per il controllo del corno.
    
    Questa classe gestisce solo 2 handle essenziali:
    - Handle di ancoraggio (per spostare lungo il perimetro)
    - Handle della punta (per controllare angolo e lunghezza)
    """
    
    def __init__(self, config: TailConfiguration, handle_size: float = 8.0):
        """
        Inizializza il gestore degli handle.
        
        Args:
            config: Configurazione del corno
            handle_size: Dimensione degli handle
        """
        self._config = config
        self._handle_size = handle_size
        self._handles = {}
        self._active_handle = None
        self._drag_start_pos = None
        
    def update_handles(self, rect: QtCore.QRectF, is_selected: bool = True):
        """Aggiorna la posizione degli handle.
        
        Args:
            rect: Rettangolo del balloon
            is_selected: Se il balloon è selezionato
        """
        if not is_selected:
            self._handles.clear()
            return
            
        hs = self._handle_size / 2
        
        # Handle per il punto di ancoraggio (posizionamento lungo il perimetro)
        anchor = self._config.get_anchor_point(rect)
        self._handles['anchor'] = QtCore.QRectF(
            anchor.x() - hs, anchor.y() - hs, self._handle_size, self._handle_size
        )
        
        # Handle per la punta del corno (controllo angolo e lunghezza)
        tip = self._config.get_tail_tip_point(rect)
        self._handles['tip'] = QtCore.QRectF(
            tip.x() - hs, tip.y() - hs, self._handle_size, self._handle_size
        )
        
    def paint_handles(self, painter: QtGui.QPainter):
        """Disegna gli handle per il controllo del corno.
        
        Args:
            painter: Painter per il disegno
        """
        if not self._handles:
            return
            
        painter.save()
        
        # Colori per i 2 handle essenziali
        colors = {
            'anchor': QtGui.QColor(255, 100, 100),  # Rosso per ancoraggio
            'tip': QtGui.QColor(100, 255, 100)      # Verde per punta
        }
        
        for handle_type, handle_rect in self._handles.items():
            color = colors.get(handle_type, QtGui.QColor(200, 200, 200))
            
            # Disegna il bordo dell'handle
            painter.setPen(QtGui.QPen(color.darker(150), 2))
            painter.setBrush(QtGui.QBrush(color))
            painter.drawEllipse(handle_rect)
            
            # Disegna un punto centrale
            center = handle_rect.center()
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1))
            painter.drawPoint(center)
            
        painter.restore()
            
    def get_handle_at_pos(self, pos: QtCore.QPointF) -> Optional[str]:
        """Trova l'handle alla posizione specificata.
        
        Args:
            pos: Posizione da controllare
            
        Returns:
            Nome dell'handle o None se nessun handle è alla posizione
        """
        for handle_type, handle_rect in self._handles.items():
            if handle_rect.contains(pos):
                return handle_type
                
        return None
        
    def start_drag(self, handle_type: str, pos: QtCore.QPointF) -> bool:
        """Inizia il trascinamento di un handle.
        
        Args:
            handle_type: Tipo di handle da trascinare
            pos: Posizione iniziale del mouse
            
        Returns:
            True se il trascinamento è iniziato
        """
        if handle_type not in self._handles:
            return False
            
        self._active_handle = handle_type
        self._drag_start_pos = pos
        return True
        
    def update_drag(self, pos: QtCore.QPointF, rect: QtCore.QRectF) -> bool:
        """Aggiorna il trascinamento.
        
        Args:
            pos: Posizione corrente del mouse
            rect: Rettangolo del balloon
            
        Returns:
            True se la configurazione è cambiata
        """
        if not self._active_handle:
            return False
            
        if self._active_handle == 'anchor':
            return self._update_anchor_drag(pos, rect)
        elif self._active_handle == 'tip':
            return self._update_tip_drag(pos, rect)
            
        return False
        
    def end_drag(self):
        """Termina il trascinamento."""
        self._active_handle = None
        self._drag_start_pos = None
        
    def _update_anchor_drag(self, pos: QtCore.QPointF, rect: QtCore.QRectF) -> bool:
        """Aggiorna il trascinamento dell'handle di ancoraggio."""
        # Trova la posizione parametrica più vicina sul perimetro
        new_position = self._find_closest_perimeter_position(pos, rect)
        
        if abs(new_position - self._config.perimeter_position) > 0.001:
            self._config.perimeter_position = new_position
            return True
            
        return False
        
    def _update_tip_drag(self, pos: QtCore.QPointF, rect: QtCore.QRectF) -> bool:
        """Aggiorna il trascinamento dell'handle della punta."""
        anchor = self._config.get_anchor_point(rect)
        
        # Calcola nuova lunghezza e angolo
        dx = pos.x() - anchor.x()
        dy = pos.y() - anchor.y()
        new_length = math.sqrt(dx*dx + dy*dy)
        new_angle = math.degrees(math.atan2(dy, dx))
        
        changed = False
        
        if abs(new_length - self._config.length) > 1.0:
            self._config.length = max(5.0, new_length)
            changed = True
            
        if abs(new_angle - self._config.angle) > 1.0:
            self._config.angle = new_angle
            changed = True
            
        return changed
        

        
    def _find_closest_perimeter_position(self, pos: QtCore.QPointF, rect: QtCore.QRectF) -> float:
        """Trova la posizione parametrica più vicina sulla circonferenza ellittica.
        
        Args:
            pos: Posizione del mouse
            rect: Rettangolo del balloon
            
        Returns:
            Posizione parametrica (0.0-1.0)
        """
        # Calcola il centro e i raggi dell'ellisse
        center_x = rect.center().x()
        center_y = rect.center().y()
        radius_x = rect.width() / 2
        radius_y = rect.height() / 2
        
        # Trasla la posizione del mouse rispetto al centro dell'ellisse
        dx = pos.x() - center_x
        dy = pos.y() - center_y
        
        # Calcola l'angolo dal centro dell'ellisse alla posizione del mouse
        angle = math.atan2(dy, dx)
        
        # Normalizza l'angolo a [0, 2π]
        if angle < 0:
            angle += 2 * math.pi
            
        # Converte l'angolo in posizione parametrica (0.0-1.0)
        param_pos = angle / (2 * math.pi)
        
        return max(0.0, min(1.0, param_pos))
        
    @property
    def active_handle(self) -> Optional[str]:
        """Handle attualmente attivo."""
        return self._active_handle
        
    @property
    def has_handles(self) -> bool:
        """Indica se ci sono handle disponibili."""
        return len(self._handles) > 0