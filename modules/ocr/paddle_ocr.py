import numpy as np
from paddleocr import PaddleOCR

from .base import OCREngine
from ..utils.textblock import TextBlock
from ..utils.pipeline_utils import lists_to_blk_list
from ..utils.color_extraction import extract_dominant_text_color


class PaddleOCREngine(OCREngine):
    """OCR engine using PaddleOCR for Chinese text."""
    
    def __init__(self):
        """Initialize PaddleOCR engine."""
        self.ocr = None
        
    def initialize(self, lang: str = 'ch', use_combined_mode: bool = False, **kwargs) -> None:
        """
        Initialize the PaddleOCR engine.
        
        Args:
            lang: Language code for OCR
            use_combined_mode: Whether to extract font color along with OCR
            **kwargs: Additional parameters passed to PaddleOCR
        """
        self.use_combined_mode = use_combined_mode
        if self.ocr is None:
            self.ocr = PaddleOCR(lang=lang, **kwargs)
        
    def process_image(self, img: np.ndarray, blk_list: list[TextBlock]) -> list[TextBlock]:
        """
        Process an image with PaddleOCR and update text blocks.
        
        Args:
            img: Input image as numpy array
            blk_list: List of TextBlock objects to update with OCR text
            
        Returns:
            List of updated TextBlock objects with recognized text
        """
        try:
            result = self.ocr.ocr(img)
            
            if not result or not result[0]:
                return blk_list
                
            result = result[0]
            
            # Extract bounding boxes and text
            texts_bboxes = []
            texts_string = []
            
            for line in result:
                bbox, text_info = line
                # Convert from points [(x1,y1), (x2,y1), (x2,y2), (x1,y2)] to (x1,y1,x2,y2)
                x1, y1 = bbox[0]
                x2, y2 = bbox[2]
                texts_bboxes.append((x1, y1, x2, y2))
                texts_string.append(text_info[0])
                
            # Aggiorna i blocchi di testo con OCR e colore del font
            updated_blk_list = lists_to_blk_list(blk_list, texts_bboxes, texts_string)
            # Fallback per caselle manuali: se il detector globale non ha visto
            # il testo, rilancia Paddle sul crop del blocco vuoto.
            for _blk in updated_blk_list:
                if getattr(_blk, 'text', '') and getattr(_blk, 'text').strip():
                    continue
                try:
                    if getattr(_blk, 'bubble_xyxy', None) is not None:
                        _fx1, _fy1, _fx2, _fy2 = [int(v) for v in _blk.bubble_xyxy]
                    else:
                        from ..utils.textblock import adjust_text_line_coordinates as _adj
                        _fx1, _fy1, _fx2, _fy2 = _adj(_blk.xyxy, 5, 5, img)
                        _fx1, _fy1, _fx2, _fy2 = int(_fx1), int(_fy1), int(_fx2), int(_fy2)
                    if not (_fx1 < _fx2 and _fy1 < _fy2 and _fx1 >= 0 and _fy1 >= 0
                            and _fx2 <= img.shape[1] and _fy2 <= img.shape[0]):
                        continue
                    _crop = img[_fy1:_fy2, _fx1:_fx2]
                    if _crop.size == 0:
                        continue
                    _cres = self.ocr.ocr(_crop)
                    if _cres and _cres[0]:
                        _parts = []
                        for _line in _cres[0]:
                            try:
                                _parts.append(_line[1][0])
                            except Exception:
                                continue
                        _joined = ' '.join([p for p in _parts if p])
                        if _joined.strip():
                            _blk.text = _joined.strip()
                except Exception:
                    continue
            
            # Estrai il colore del font per ogni blocco solo se use_combined_mode è True
            if self.use_combined_mode:
                for i, blk in enumerate(updated_blk_list):
                    if i < len(texts_bboxes) and (not blk.font_color or blk.font_color == ""):
                        try:
                            x1, y1, x2, y2 = texts_bboxes[i]
                            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                            
                            # Verifica che le coordinate siano valide
                            if (x1 < x2 and y1 < y2 and x1 >= 0 and y1 >= 0 and 
                                x2 <= img.shape[1] and y2 <= img.shape[0]):
                                cropped_img = img[y1:y2, x1:x2]
                                extracted_color = extract_dominant_text_color(cropped_img)
                                blk.font_color = extracted_color
                            else:
                                blk.font_color = "#000000"  # Fallback al nero
                        except Exception as e:
                            print(f"Errore nell'estrazione automatica del colore: {e}")
                            blk.font_color = "#000000"  # Fallback al nero
                        
            return updated_blk_list
        
        except Exception as e:
            print(f"PaddleOCR error: {str(e)}")
            return blk_list