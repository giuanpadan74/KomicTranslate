import numpy as np
import torch
from doctr.models import ocr_predictor

from .base import OCREngine
from ..utils.textblock import TextBlock
from ..utils.pipeline_utils import lists_to_blk_list
from ..utils.color_extraction import extract_dominant_text_color


class DocTROCREngine(OCREngine):
    """OCR engine using DocTR"""
    
    def __init__(self):
        """Initialize DocTR OCR engine."""
        self.model = None
        self.device = 'cpu'
        
    def initialize(self, device: str = 'cpu', use_combined_mode: bool = False, **kwargs) -> None:
        """
        Initialize the DocTR engine.
        
        Args:
            device: Device to use ('cpu' or 'cuda')
            use_combined_mode: Whether to extract font color along with OCR
            **kwargs: Additional parameters (ignored)
        """
        
        self.device = device
        self.use_combined_mode = use_combined_mode
        
        # Initialize model if not already loaded
        if self.model is None:
            self.model = ocr_predictor(
                det_arch='db_mobilenet_v3_large', 
                reco_arch='crnn_vgg16_bn', 
                pretrained=True,
            )

            # Move model to appropriate device after creation
            if device == 'cuda' and torch.cuda.is_available():
                self.model.cuda().half()
        
    def process_image(self, img: np.ndarray, blk_list: list[TextBlock]) -> list[TextBlock]:
        """
        Process an image with DocTR and update text blocks.
        
        Args:
            img: Input image as numpy array
            blk_list: List of TextBlock objects to update with OCR text
            
        Returns:
            List of updated TextBlock objects with recognized text
        """
        try:
            # Process whole image with DocTR
            result = self.model([img])
            
            # Extract text and bounding boxes
            texts_bboxes = []
            texts_string = []
            
            # Process result to extract boxes and text
            for page in result.pages:
                h, w = page.dimensions
                for block in page.blocks:
                    for line in block.lines:
                        # Get text from line
                        line_text = " ".join(word.value for word in line.words)
                        if not line_text.strip():
                            continue
                            
                        # Get coordinates and normalize to absolute pixel values
                        x_min, y_min = line.geometry[0]
                        x_max, y_max = line.geometry[1]
                        
                        # Convert relative coordinates to absolute pixel coordinates
                        x1 = int(x_min * w)
                        y1 = int(y_min * h)
                        x2 = int(x_max * w)
                        y2 = int(y_max * h)
                        
                        texts_bboxes.append((x1, y1, x2, y2))
                        texts_string.append(line_text)
            
            # Match detected text to provided blocks using lists_to_blk_list
            updated_blk_list = lists_to_blk_list(blk_list, texts_bboxes, texts_string)
            # Fallback per caselle manuali: il detector globale puo' non aver
            # visto il testo (e' il motivo per cui l'utente lo disegna a mano).
            # Senza fallback blk.text resta "" e la traduzione diventa '...'.
            try:
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
                        _crop_res = self.model([_crop])
                        _parts = []
                        for _page in _crop_res.pages:
                            for _block in _page.blocks:
                                for _line in _block.lines:
                                    _lt = " ".join(_w.value for _w in _line.words)
                                    if _lt.strip():
                                        _parts.append(_lt.strip())
                        if _parts:
                            _blk.text = " ".join(_parts)
                    except Exception:
                        continue
            except Exception:
                pass
            
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
            print(f"DocTR OCR error: {str(e)}")
            return blk_list
    
