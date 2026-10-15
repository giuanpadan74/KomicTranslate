"""Modulo per l'estrazione del colore dominante del testo dalle immagini."""

import numpy as np
import cv2
from typing import Tuple, List, Optional
from sklearn.cluster import KMeans
import logging

logger = logging.getLogger(__name__)

def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Converte un colore RGB in formato hex.
    
    Args:
        rgb: Tupla (R, G, B) con valori 0-255
        
    Returns:
        Stringa hex nel formato #RRGGBB
    """
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Converte un colore hex in RGB.
    
    Args:
        hex_color: Stringa hex nel formato #RRGGBB
        
    Returns:
        Tupla (R, G, B) con valori 0-255
    """
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def is_background_color(color_hsv: np.ndarray, brightness_threshold: float = 0.8) -> bool:
    """Determina se un colore è probabilmente uno sfondo.
    
    Args:
        color_hsv: Colore in formato HSV (H, S, V)
        brightness_threshold: Soglia di luminosità per considerare un colore come sfondo
        
    Returns:
        True se il colore è probabilmente uno sfondo
    """
    # Colori molto chiari (bianchi/grigi chiari) sono spesso sfondi
    if color_hsv[2] > brightness_threshold:
        return True
    
    # Colori con saturazione molto bassa (grigi) possono essere sfondi
    if color_hsv[1] < 0.1 and color_hsv[2] > 0.5:
        return True
        
    return False

def extract_dominant_text_color(img_region: np.ndarray, 
                               n_colors: int = 8,
                               min_saturation: float = 0.05,
                               max_brightness: float = 0.9) -> str:
    """Estrae il colore dominante del testo da una regione dell'immagine.
    
    Args:
        img_region: Regione dell'immagine come array numpy (BGR)
        n_colors: Numero di cluster per K-means
        min_saturation: Saturazione minima per considerare un colore come testo
        max_brightness: Luminosità massima per considerare un colore come testo
        
    Returns:
        Colore del testo in formato hex (#RRGGBB)
    """
    try:
        # Verifica che l'immagine non sia vuota
        if img_region is None or img_region.size == 0:
            logger.warning("Regione immagine vuota, uso colore di default")
            return "#000000"
        
        # Converti da BGR a RGB
        img_rgb = cv2.cvtColor(img_region, cv2.COLOR_BGR2RGB)
        
        # Ridimensiona l'immagine se troppo grande per migliorare le performance
        height, width = img_rgb.shape[:2]
        if height * width > 50000:  # Se più di 50k pixel
            scale = np.sqrt(50000 / (height * width))
            new_width = int(width * scale)
            new_height = int(height * scale)
            img_rgb = cv2.resize(img_rgb, (new_width, new_height))
        
        # Converti in HSV per migliore analisi del colore
        img_hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
        
        # Reshape per K-means (ogni pixel diventa un punto)
        pixels = img_rgb.reshape(-1, 3)
        pixels_hsv = img_hsv.reshape(-1, 3)
        
        # Normalizza i valori HSV
        pixels_hsv = pixels_hsv.astype(np.float32)
        pixels_hsv[:, 0] /= 179.0  # H: 0-179 -> 0-1
        pixels_hsv[:, 1] /= 255.0  # S: 0-255 -> 0-1
        pixels_hsv[:, 2] /= 255.0  # V: 0-255 -> 0-1
        
        # Prima strategia: cerca colori non-bianchi
        # Filtra i pixel che non sono quasi bianchi
        non_white_mask = np.logical_or(
            pixels_hsv[:, 1] > 0.1,  # Saturazione > 10%
            pixels_hsv[:, 2] < 0.9   # Luminosità < 90%
        )
        
        if np.sum(non_white_mask) > len(pixels) * 0.05:  # Se almeno 5% dei pixel non sono bianchi
            # Usa solo i pixel non-bianchi per il clustering
            filtered_pixels = pixels[non_white_mask]
            
            if len(filtered_pixels) > 0:
                # Applica K-means sui pixel filtrati
                n_clusters = min(n_colors, len(filtered_pixels))
                if n_clusters > 0:
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                    kmeans.fit(filtered_pixels)
                    
                    # Ottieni i centri dei cluster e le loro frequenze
                    centers = kmeans.cluster_centers_
                    labels = kmeans.labels_
                    
                    # Calcola la frequenza di ogni cluster
                    unique_labels, counts = np.unique(labels, return_counts=True)
                    
                    # Trova il cluster più frequente
                    most_frequent_idx = np.argmax(counts)
                    dominant_color = centers[most_frequent_idx]
                    
                    # Converti in formato hex
                    color_rgb = tuple(int(c) for c in dominant_color)
                    hex_color = rgb_to_hex(color_rgb)
                    
                    logger.debug(f"Colore dominante estratto (strategia filtrata): {hex_color}")
                    return hex_color
        
        # Strategia di fallback: K-means tradizionale con filtri migliorati
        # Applica K-means clustering su tutti i pixel
        kmeans = KMeans(n_clusters=min(n_colors, len(pixels)), random_state=42, n_init=10)
        kmeans.fit(pixels)
        
        # Ottieni i centri dei cluster e le loro frequenze
        centers = kmeans.cluster_centers_
        labels = kmeans.labels_
        
        # Calcola la frequenza di ogni cluster
        unique_labels, counts = np.unique(labels, return_counts=True)
        
        # Converti i centri in HSV per l'analisi
        centers_hsv = []
        for center in centers:
            # Converti RGB a HSV
            center_rgb = center.reshape(1, 1, 3).astype(np.uint8)
            center_hsv = cv2.cvtColor(center_rgb, cv2.COLOR_RGB2HSV)
            centers_hsv.append(center_hsv[0, 0] / np.array([179.0, 255.0, 255.0]))
        
        # Filtra i colori che probabilmente sono testo (non sfondo)
        text_candidates = []
        for i, (center, center_hsv, count) in enumerate(zip(centers, centers_hsv, counts)):
            # Salta i colori quasi bianchi (sfondo)
            if center_hsv[2] > 0.95 and center_hsv[1] < 0.05:  # Molto chiaro e poco saturo
                continue
                
            # Salta i colori di sfondo chiari
            if is_background_color(center_hsv, brightness_threshold=0.95):
                continue
                
            text_candidates.append((center, count, center_hsv))
        
        # Se non ci sono candidati validi, usa il colore più scuro
        if not text_candidates:
            logger.info("Nessun candidato testo trovato, uso il colore più scuro")
            darkest_idx = np.argmin([c[2] for c in centers_hsv])  # Minima luminosità
            dominant_color = centers[darkest_idx]
        else:
            # Ordina per frequenza e scegli il più comune tra i candidati
            text_candidates.sort(key=lambda x: x[1], reverse=True)
            dominant_color = text_candidates[0][0]
        
        # Converti in formato hex
        color_rgb = tuple(int(c) for c in dominant_color)
        hex_color = rgb_to_hex(color_rgb)
        
        logger.debug(f"Colore dominante estratto: {hex_color}")
        return hex_color
        
    except Exception as e:
        logger.error(f"Errore nell'estrazione del colore: {str(e)}")
        return "#000000"  # Colore di fallback

def extract_text_colors_from_blocks(img: np.ndarray, 
                                   text_blocks: List,
                                   **kwargs) -> List[str]:
    """Estrae i colori del testo per una lista di text block.
    
    Args:
        img: Immagine completa come array numpy
        text_blocks: Lista di TextBlock objects
        **kwargs: Parametri aggiuntivi per extract_dominant_text_color
        
    Returns:
        Lista di colori in formato hex, uno per ogni text block
    """
    colors = []
    
    for block in text_blocks:
        try:
            # Ottieni le coordinate del bounding box
            if hasattr(block, 'xyxy') and block.xyxy is not None:
                x1, y1, x2, y2 = block.xyxy
            elif hasattr(block, 'bubble_xyxy') and block.bubble_xyxy is not None:
                x1, y1, x2, y2 = block.bubble_xyxy
            else:
                logger.warning("Text block senza coordinate valide")
                colors.append("#000000")
                continue
            
            # Assicurati che le coordinate siano valide
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            # Estrai la regione dell'immagine
            height, width = img.shape[:2]
            x1 = max(0, min(x1, width))
            y1 = max(0, min(y1, height))
            x2 = max(x1, min(x2, width))
            y2 = max(y1, min(y2, height))
            
            if x2 <= x1 or y2 <= y1:
                logger.warning("Coordinate del text block non valide")
                colors.append("#000000")
                continue
                
            region = img[y1:y2, x1:x2]
            
            # Estrai il colore dominante
            color = extract_dominant_text_color(region, **kwargs)
            colors.append(color)
            
        except Exception as e:
            logger.error(f"Errore nell'estrazione del colore per il block: {str(e)}")
            colors.append("#000000")
    
    return colors

def validate_color(color: str) -> str:
    """Valida e normalizza un colore hex.
    
    Args:
        color: Colore in formato hex
        
    Returns:
        Colore hex validato e normalizzato
    """
    if not color or not isinstance(color, str):
        return "#000000"
    
    # Rimuovi spazi e converti in minuscolo
    color = color.strip().lower()
    
    # Aggiungi # se mancante
    if not color.startswith('#'):
        color = '#' + color
    
    # Verifica lunghezza
    if len(color) != 7:
        return "#000000"
    
    # Verifica caratteri hex validi
    try:
        int(color[1:], 16)
        return color.upper()
    except ValueError:
        return "#000000"