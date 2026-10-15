import cv2
import numpy as np
from typing import Optional
from io import BytesIO
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color
from PySide6.QtGui import QColor

class ImageProcessor:
    def __init__(self):
        pass
    
    def cv2_to_pil_image(self, cv2_image: np.ndarray, input_format: str = 'BGR') -> Optional[Image.Image]:
        if cv2_image is None:
            return None
        
        if len(cv2_image.shape) == 3 and cv2_image.shape[2] == 3:
            if input_format.upper() == 'BGR':
                rgb_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
                return Image.fromarray(rgb_image)
            elif input_format.upper() == 'RGB':
                return Image.fromarray(cv2_image)
            else:
                rgb_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
                return Image.fromarray(rgb_image)
        else:
            return Image.fromarray(cv2_image)
    
    def qcolor_to_reportlab_color(self, qcolor) -> Color:
        if isinstance(qcolor, str):
            if qcolor.startswith('#'):
                qcolor = QColor(qcolor)
            else:
                qcolor = QColor(qcolor)
        elif isinstance(qcolor, dict):
            qcolor = QColor(qcolor.get('r', 0), qcolor.get('g', 0), qcolor.get('b', 0), qcolor.get('a', 255))
        elif not isinstance(qcolor, QColor):
            print(f"[WARNING] Tipo di colore non riconosciuto: {type(qcolor)}, valore: {qcolor}")
            qcolor = QColor(0, 0, 0)
        
        if not qcolor.isValid():
            print(f"[WARNING] Colore non valido, uso nero di default")
            qcolor = QColor(0, 0, 0)
        
        r = qcolor.red() / 255.0
        g = qcolor.green() / 255.0
        b = qcolor.blue() / 255.0
        a = qcolor.alpha() / 255.0
        
        return Color(r, g, b, alpha=a)
    
    def image_to_jpeg_buffer(self, pil_image: Image.Image, quality: int = 85) -> BytesIO:
        img_buffer = BytesIO()
        pil_image.save(img_buffer, format='JPEG', quality=quality, optimize=True)
        img_buffer.seek(0)
        return img_buffer
