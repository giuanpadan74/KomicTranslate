import numpy as np
import easyocr

from .base import OCREngine
from ..utils.textblock import TextBlock, adjust_text_line_coordinates
from ..utils.color_extraction import extract_dominant_text_color


class EasyOCREngine(OCREngine):
    """OCR engine using EasyOCR for English text."""
    
    def __init__(self):
        """Initialize EasyOCR engine."""
        self.reader = None
        self.language = ['en']
        self.gpu_enabled = False
        self.expansion_percentage = 5
        
    def initialize(self, languages: list[str] = None, use_gpu: bool = False, 
                  expansion_percentage: int = 5, use_combined_mode: bool = False, **kwargs) -> None:
        """
        Initialize the EasyOCR engine.
        
        Args:
            languages: List of language codes for OCR
            use_gpu: Whether to use GPU acceleration
            expansion_percentage: Percentage to expand text bounding boxes
            use_combined_mode: Whether to extract font color along with OCR
            **kwargs: Additional parameters (ignored)
        """
        self.language = languages or ['en']
        self.gpu_enabled = use_gpu
        self.expansion_percentage = expansion_percentage
        self.use_combined_mode = use_combined_mode
        
        # Initialize model if not already loaded
        if self.reader is None:
            self.reader = easyocr.Reader(self.language, gpu=self.gpu_enabled)
        
    def process_image(self, img: np.ndarray, blk_list: list[TextBlock]) -> list[TextBlock]:
        """
        Process an image with EasyOCR and update text blocks.
        
        Args:
            img: Input image as numpy array
            blk_list: List of TextBlock objects to update with OCR text
            
        Returns:
            List of updated TextBlock objects with recognized text
        """
        for blk in blk_list:
            try:
                # Get box coordinates (cast a int per le caselle manuali float)
                if blk.bubble_xyxy is not None:
                    x1, y1, x2, y2 = [int(v) for v in blk.bubble_xyxy]
                else:
                    x1, y1, x2, y2 = adjust_text_line_coordinates(
                        blk.xyxy, 
                        self.expansion_percentage, 
                        self.expansion_percentage, 
                        img
                    )
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                
                # Check if coordinates are valid
                if x1 < x2 and y1 < y2 and x1 >= 0 and y1 >= 0 and x2 <= img.shape[1] and y2 <= img.shape[0]:
                    # Crop image and run OCR
                    cropped_img = img[y1:y2, x1:x2]
                    result = self.reader.readtext(cropped_img, paragraph=True)
                    texts = [r[1] for r in result if r is not None]
                    blk.text = ' '.join(texts)
                    
                    # Estrai automaticamente il colore del font solo se use_combined_mode è True
                    if self.use_combined_mode and (not blk.font_color or blk.font_color == ""):
                        try:
                            extracted_color = extract_dominant_text_color(cropped_img)
                            blk.font_color = extracted_color
                        except Exception as e:
                            print(f"Errore nell'estrazione automatica del colore: {e}")
                            blk.font_color = "#000000"  # Fallback al nero
                else:
                    print('Invalid textbbox to target img')
                    blk.text = ""
            except Exception as e:
                print(f"EasyOCR error on block: {str(e)}")
                blk.text = ""
                
        return blk_list