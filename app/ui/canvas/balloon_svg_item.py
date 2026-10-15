"""Classe per elementi SVG di fumetti con manipolazione selettiva dei corni."""

import os
import re
import math
from xml.etree import ElementTree as ET
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsItem
from .svg_item import SvgItem


class BalloonTail:
    """Rappresenta un corno/coda di un fumetto"""
    
    def __init__(self, points, original_points=None):
        self.points = points  # Lista di QPointF che definiscono il corno
        self.original_points = original_points or points.copy()  # Punti originali per il reset
        self.is_selected = False
        self.handle_rect = QRectF()  # Rettangolo dell'handle per la selezione
        
    def get_tip_point(self):
        """Restituisce il punto della punta del corno"""
        if not self.points:
            return QPointF()
        # La punta è solitamente il punto più lontano dal centro del fumetto
        return self.points[-1] if len(self.points) > 1 else self.points[0]
    
    def get_base_point(self):
        """Restituisce il punto di base del corno (attaccato al fumetto)"""
        if not self.points:
            return QPointF()
        return self.points[0]
    
    def get_center_point(self):
        """Restituisce il punto centrale del corno per il posizionamento dell'handle"""
        if not self.points:
            return QPointF()
        
        # Calcola il centro geometrico dei punti
        total_x = sum(p.x() for p in self.points)
        total_y = sum(p.y() for p in self.points)
        return QPointF(total_x / len(self.points), total_y / len(self.points))
    
    def transform(self, transform_matrix):
        """Applica una trasformazione ai punti del corno"""
        self.points = [transform_matrix.map(point) for point in self.points]
    
    def scale_from_base(self, scale_factor):
        """Scala il corno mantenendo fisso il punto di base"""
        if not self.points or len(self.points) < 2:
            return
        
        base = self.get_base_point()
        for i in range(1, len(self.points)):
            # Scala ogni punto rispetto alla base
            delta = self.points[i] - base
            self.points[i] = base + delta * scale_factor
    
    def rotate_around_base(self, angle_degrees):
        """Ruota il corno attorno al punto di base"""
        if not self.points or len(self.points) < 2:
            return
        
        base = self.get_base_point()
        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        
        for i in range(1, len(self.points)):
            # Trasla alla base, ruota, e trasla indietro
            delta = self.points[i] - base
            rotated_x = delta.x() * cos_a - delta.y() * sin_a
            rotated_y = delta.x() * sin_a + delta.y() * cos_a
            self.points[i] = base + QPointF(rotated_x, rotated_y)


class BalloonSvgItem(SvgItem):
    """Elemento SVG di fumetto con supporto per manipolazione selettiva dei corni"""
    
    # Segnali specifici per i corni
    tail_modified = Signal(int)  # Emesso quando un corno viene modificato
    tail_selected = Signal(int)  # Emesso quando un corno viene selezionato
    
    def __init__(self, svg_path, parent=None):
        super().__init__(svg_path, parent)
        
        # Proprietà specifiche per i corni
        self.tails = []  # Lista di BalloonTail
        self.selected_tail_index = -1  # Indice del corno selezionato (-1 = nessuno)
        self.tail_handle_size = 10.0
        
        # Analizza l'SVG per identificare i corni
        self._analyze_svg_for_tails()
    
    def _analyze_svg_for_tails(self):
        """Analizza il file SVG per identificare automaticamente i corni dei fumetti"""
        if not os.path.exists(self.svg_path):
            return
        
        try:
            # Leggi e analizza il file SVG
            tree = ET.parse(self.svg_path)
            root = tree.getroot()
            
            # Trova tutti i path nell'SVG
            paths = self._find_svg_paths(root)
            
            # Analizza ogni path per identificare potenziali corni
            for path_data in paths:
                tails = self._extract_tails_from_path(path_data)
                self.tails.extend(tails)
            
            print(f"Identificati {len(self.tails)} corni nel fumetto {os.path.basename(self.svg_path)}")
            
        except Exception as e:
            print(f"Errore nell'analisi dell'SVG per i corni: {e}")
    
    def _find_svg_paths(self, element):
        """Trova tutti i path nell'elemento SVG"""
        paths = []
        
        # Namespace SVG
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        
        # Cerca path diretti
        for path in element.findall('.//svg:path', ns):
            d_attr = path.get('d')
            if d_attr:
                paths.append(d_attr)
        
        # Se non trova path con namespace, prova senza
        if not paths:
            for path in element.findall('.//path'):
                d_attr = path.get('d')
                if d_attr:
                    paths.append(d_attr)
        
        return paths
    
    def _extract_tails_from_path(self, path_data):
        """Estrae i corni da un path SVG analizzando la geometria"""
        tails = []
        
        try:
            # Converte il path SVG in punti
            points = self._parse_svg_path_to_points(path_data)
            
            if len(points) < 10:  # Troppo pochi punti per contenere corni
                return tails
            
            # Identifica potenziali corni analizzando la curvatura e le proiezioni
            tail_segments = self._identify_tail_segments(points)
            
            for segment in tail_segments:
                if len(segment) >= 3:  # Un corno deve avere almeno 3 punti
                    tail = BalloonTail(segment)
                    tails.append(tail)
        
        except Exception as e:
            print(f"Errore nell'estrazione dei corni dal path: {e}")
        
        return tails
    
    def _parse_svg_path_to_points(self, path_data):
        """Converte un path SVG in una lista di punti"""
        points = []
        
        # Rimuovi caratteri non necessari e dividi i comandi
        path_data = re.sub(r'[,\s]+', ' ', path_data.strip())
        commands = re.findall(r'[MmLlHhVvCcSsQqTtAaZz][^MmLlHhVvCcSsQqTtAaZz]*', path_data)
        
        current_pos = QPointF(0, 0)
        
        for command in commands:
            cmd = command[0]
            params = command[1:].strip().split()
            
            try:
                if cmd in 'Mm':  # Move to
                    if len(params) >= 2:
                        x, y = float(params[0]), float(params[1])
                        if cmd == 'M':
                            current_pos = QPointF(x, y)
                        else:  # 'm' - relativo
                            current_pos += QPointF(x, y)
                        points.append(current_pos)
                
                elif cmd in 'Ll':  # Line to
                    for i in range(0, len(params), 2):
                        if i + 1 < len(params):
                            x, y = float(params[i]), float(params[i + 1])
                            if cmd == 'L':
                                current_pos = QPointF(x, y)
                            else:  # 'l' - relativo
                                current_pos += QPointF(x, y)
                            points.append(current_pos)
                
                elif cmd in 'Cc':  # Cubic Bezier
                    for i in range(0, len(params), 6):
                        if i + 5 < len(params):
                            # Per semplicità, prendiamo solo il punto finale della curva
                            x, y = float(params[i + 4]), float(params[i + 5])
                            if cmd == 'C':
                                current_pos = QPointF(x, y)
                            else:  # 'c' - relativo
                                current_pos += QPointF(x, y)
                            points.append(current_pos)
            
            except (ValueError, IndexError):
                continue  # Ignora comandi malformati
        
        return points
    
    def _identify_tail_segments(self, points):
        """Identifica i segmenti che rappresentano i corni analizzando la geometria"""
        if len(points) < 10:
            return []
        
        # Calcola il centro approssimativo del fumetto
        center_x = sum(p.x() for p in points) / len(points)
        center_y = sum(p.y() for p in points) / len(points)
        center = QPointF(center_x, center_y)
        
        # Calcola le distanze dal centro per ogni punto
        distances = [math.sqrt((p.x() - center.x())**2 + (p.y() - center.y())**2) for p in points]
        
        # Trova i punti che si allontanano significativamente dal centro (potenziali corni)
        avg_distance = sum(distances) / len(distances)
        threshold = avg_distance * 1.5  # Soglia per identificare proiezioni
        
        tail_segments = []
        current_segment = []
        in_tail = False
        
        for i, (point, distance) in enumerate(zip(points, distances)):
            if distance > threshold:
                if not in_tail:
                    # Inizia un nuovo corno
                    in_tail = True
                    current_segment = [point]
                else:
                    current_segment.append(point)
            else:
                if in_tail:
                    # Fine del corno
                    if len(current_segment) >= 3:
                        tail_segments.append(current_segment)
                    current_segment = []
                    in_tail = False
        
        # Aggiungi l'ultimo segmento se necessario
        if in_tail and len(current_segment) >= 3:
            tail_segments.append(current_segment)
        
        return tail_segments
    
    def paint(self, painter, option, widget=None):
        """Disegna l'elemento SVG"""
        # Disegna l'SVG base
        super().paint(painter, option, widget)
    

    

    
    def mousePressEvent(self, event):
        """Gestisce il click del mouse per ridimensionamento normale"""
        # Gestione normale dell'SVG
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Gestisce il movimento del mouse"""
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Gestisce il rilascio del mouse"""
        super().mouseReleaseEvent(event)
    

    
    def hoverMoveEvent(self, event):
        """Gestisce il movimento del mouse"""
        super().hoverMoveEvent(event)
    
    def get_selected_tail(self):
        """Restituisce il corno attualmente selezionato"""
        if 0 <= self.selected_tail_index < len(self.tails):
            return self.tails[self.selected_tail_index]
        return None
    
    def reset_tail_to_original(self, tail_index=None):
        """Ripristina un corno (o tutti) alla forma originale"""
        if tail_index is None:
            # Ripristina tutti i corni
            for tail in self.tails:
                tail.points = tail.original_points.copy()
        elif 0 <= tail_index < len(self.tails):
            # Ripristina un corno specifico
            self.tails[tail_index].points = self.tails[tail_index].original_points.copy()
        
        self.update()
    
    def get_tail_count(self):
        """Restituisce il numero di corni identificati"""
        return len(self.tails)
    
    def __str__(self):
        """Rappresentazione stringa dell'elemento"""
        return f"BalloonSvgItem({os.path.basename(self.svg_path)}, tails={len(self.tails)}, scale={self.get_uniform_scale():.2f})"