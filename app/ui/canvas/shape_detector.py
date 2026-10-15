import cv2
import numpy as np
from typing import Tuple, Optional

class ShapeDetector:
    @staticmethod
    def detect_shape_from_image(image: np.ndarray, bbox: Tuple[int, int, int, int], 
                               min_confidence: float = 0.6, default_to_rectangle: bool = False) -> str:
        """
        Rileva se una regione dell'immagine è un rettangolo o un'ellisse.
        
        Args:
            image: Immagine completa in formato OpenCV (BGR)
            bbox: Bounding box (x1, y1, x2, y2) relativo all'immagine
            min_confidence: Soglia minima di confidenza per il rilevamento
            default_to_rectangle: Se True, preferisce il rettangolo in caso di incertezza
            
        Returns:
            'rectangle', 'ellipse' o 'unknown'
        """
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
        
        if x2 <= x1 or y2 <= y1:
            return 'unknown'
        
        roi = image[y1:y2, x1:x2]
        if roi.size == 0:
            return 'unknown'
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        edges = cv2.Canny(gray, 50, 150)
        
        width = x2 - x1
        height = y2 - y1
        center_x = width // 2
        center_y = height // 2
        
        corner_scores = ShapeDetector._detect_corners(edges, width, height)
        rectangle_score = ShapeDetector._calculate_rectangle_score(corner_scores, edges, width, height)
        ellipse_score = ShapeDetector._calculate_ellipse_score(edges, gray, width, height)
        
        total = rectangle_score + ellipse_score
        if total == 0:
            return 'rectangle' if default_to_rectangle else 'ellipse'
        
        rect_confidence = rectangle_score / total
        ellipse_confidence = ellipse_score / total
        
        if rect_confidence >= min_confidence and rect_confidence > ellipse_confidence:
            return 'rectangle'
        elif ellipse_confidence >= min_confidence and ellipse_confidence > rect_confidence:
            return 'ellipse'
        
        # In caso di incertezza (bassa confidenza), usa la preferenza dell'utente
        # se l'aspect ratio non è estremo
        aspect_ratio = width / height if height > 0 else 1
        if 0.5 <= aspect_ratio <= 1.5:
            return 'rectangle' if default_to_rectangle else 'ellipse'
        
        return 'rectangle'
    
    @staticmethod
    def _detect_corners(edges: np.ndarray, width: int, height: int) -> dict:
        """Rileva la presenza di angoli netti nei bordi."""
        corners = {
            'top_left': 0, 'top_right': 0,
            'bottom_left': 0, 'bottom_right': 0
        }
        
        margin = 10
        
        if edges.shape[0] > margin * 2 and edges.shape[1] > margin * 2:
            regions = {
                'top_left': edges[margin:height//3, margin:width//3],
                'top_right': edges[margin:height//3, 2*width//3:width-margin],
                'bottom_left': edges[2*height//3:height-margin, margin:width//3],
                'bottom_right': edges[2*height//3:height-margin, 2*width//3:width-margin]
            }
            
            for key, region in regions.items():
                if region.size > 0:
                    corner_density = np.sum(region > 0) / region.size
                    corners[key] = corner_density
        
        return corners
    
    @staticmethod
    def _calculate_rectangle_score(corners: dict, edges: np.ndarray, 
                                  width: int, height: int) -> float:
        """Calcola il punteggio di somiglianza con un rettangolo."""
        corner_score = 0.0
        
        corner_count = sum(1 for c in corners.values() if c > 0.05)
        if corner_count >= 2:
            corner_score = min(corner_count / 4, 1.0)
        
        h_lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=min(width, height)*0.3, maxLineGap=10)
        line_score = 0.0
        if h_lines is not None:
            horizontal = sum(1 for line in h_lines if abs(line[0][3] - line[0][1]) < 10)
            vertical = sum(1 for line in h_lines if abs(line[0][2] - line[0][0]) < 10)
            total_lines = len(h_lines)
            if total_lines > 0:
                line_score = (horizontal + vertical) / (total_lines * 2)
                line_score = min(line_score, 1.0)
        
        return (corner_score * 0.6 + line_score * 0.4) * 0.8
    
    @staticmethod
    def _calculate_ellipse_score(edges: np.ndarray, gray: np.ndarray,
                                 width: int, height: int) -> float:
        """Calcola il punteggio di somiglianza con un'ellisse."""
        h, w = edges.shape
        
        cx, cy = w // 2, h // 2
        rx, ry = w // 2, h // 2
        
        y_coords, x_coords = np.ogrid[:h, :w]
        normalized_x = ((x_coords - cx) / rx) ** 2
        normalized_y = ((y_coords - cy) / ry) ** 2
        ellipse_distance = normalized_x + normalized_y
        
        edge_projection = edges > 0
        
        if np.sum(edge_projection) == 0:
            return 0.0
        
        ellipse_mask = (ellipse_distance >= 0.7) & (ellipse_distance <= 1.3)
        edge_on_ellipse = np.sum(edge_projection & ellipse_mask)
        total_edges = np.sum(edge_projection)
        
        edge_score = edge_on_ellipse / total_edges if total_edges > 0 else 0
        
        contour_score = 0.0
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            if len(largest_contour) >= 5:
                try:
                    ellipse = cv2.fitEllipse(largest_contour)
                    ellipse_mask_fit = np.zeros_like(edges)
                    cv2.ellipse(ellipse_mask_fit, ellipse, 255, 2)
                    match = cv2.matchShapes(ellipse_mask_fit, edges, cv2.CONTOURS_MATCH_I2, 0)
                    contour_score = max(0, 1 - match / 10)
                except:
                    pass
        
        return (edge_score * 0.5 + contour_score * 0.5) * 0.8
    
    @staticmethod
    def detect_shape_from_item(item, default_to_rectangle: bool = False) -> str:
        """
        Rileva la forma basandosi sulle proprietà geometriche dell'item grafico.
        Utilizza l'attributo shape_type se presente, altrimenti analizza la classe
        o le proprietà del bounding box.
        
        Args:
            item: MoveableRectItem o MoveableEllipseItem
            default_to_rectangle: Se True, preferisce il rettangolo in caso di incertezza
            
        Returns:
            'rectangle', 'ellipse' o 'unknown'
        """
        # Priorità 1: Attributo esplicito (più affidabile)
        if hasattr(item, 'shape_type'):
            return item.shape_type
            
        # Priorità 2: Analisi del nome della classe (robusta contro ricaricamenti dei moduli)
        class_name = item.__class__.__name__
        if 'RectItem' in class_name:
            return 'rectangle'
        elif 'EllipseItem' in class_name:
            return 'ellipse'
            
        from .rectangle import MoveableRectItem, MoveableEllipseItem
        
        # Priorità 3: Analisi della classe esatta
        if isinstance(item, MoveableRectItem):
            return 'rectangle'
        elif isinstance(item, MoveableEllipseItem):
            return 'ellipse'
        
        # Priorità 4: Analisi fallback basata sul bounding box
        try:
            rect = item.rect()
            w, h = rect.width(), rect.height()
            
            if w <= 0 or h <= 0:
                return 'rectangle' if default_to_rectangle else 'ellipse'
            
            aspect_ratio = w / h
            
            # Se è quasi un quadrato/cerchio, usa la preferenza dell'utente o ellisse di default
            if 0.85 <= aspect_ratio <= 1.15:
                return 'rectangle' if default_to_rectangle else 'ellipse'
            
            # Per forme allungate, tendenzialmente rettangoli se non specificato diversamente
            return 'rectangle'
        except AttributeError:
            return 'unknown'


def detect_shape_visual_feedback(result: str) -> Tuple[str, str]:
    """
    Genera il feedback visivo per il risultato del rilevamento.
    
    Args:
        result: Risultato del rilevamento ('rectangle', 'ellipse', 'unknown')
        
    Returns:
        Tuple (testo_feedback, colore)
    """
    feedback_map = {
        'rectangle': ('Rettangolo rilevato', '#4CAF50'),
        'ellipse': ('Ellisse rilevata', '#2196F3'),
        'unknown': ('Forma non determinata', '#FF9800')
    }
    
    return feedback_map.get(result, feedback_map['unknown'])
