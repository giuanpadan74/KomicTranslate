"""Font Detection Module.

Usava engine LLM Vision (GPTOCR, GeminiOCR), rimossi con lo strato LLM.
Ora delega a geminiamo, l'unico engine vision rimasto.
"""

import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import numpy as np
import cv2
from PIL import Image

from ..utils.textblock import TextBlock
from ..ocr.factory import OCREngineFactory

logger = logging.getLogger(__name__)

@dataclass
class FontDetectionResult:
    """Result of font detection analysis."""
    font_family: str
    font_style: str  # normal, bold, italic, bold-italic
    font_weight: str  # light, normal, medium, bold, extra-bold
    font_size_estimate: str  # small, medium, large
    serif_type: str  # serif, sans-serif, monospace, decorative
    font_color: str = "#000000"  # Colore del font in formato hex
    confidence: float = 0.0  # 0.0 to 1.0
    additional_info: Dict[str, Any] = None  # Extra information from LLM
    
    def __post_init__(self):
        if self.additional_info is None:
            self.additional_info = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'font_family': self.font_family,
            'font_style': self.font_style,
            'font_weight': self.font_weight,
            'font_size_estimate': self.font_size_estimate,
            'serif_type': self.serif_type,
            'font_color': self.font_color,
            'confidence': self.confidence,
            'additional_info': self.additional_info
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FontDetectionResult':
        """Create from dictionary."""
        return cls(
            font_family=data.get('font_family', 'Unknown'),
            font_style=data.get('font_style', 'normal'),
            font_weight=data.get('font_weight', 'normal'),
            font_size_estimate=data.get('font_size_estimate', 'medium'),
            serif_type=data.get('serif_type', 'sans-serif'),
            font_color=data.get('font_color', '#000000'),
            confidence=data.get('confidence', 0.0),
            additional_info=data.get('additional_info', {})
        )

class FontDetector:
    """Font detection using LLM Vision models."""
    
    def __init__(self, settings):
        self.settings = settings
        self.ocr_factory = OCREngineFactory()
        
    def detect_fonts(self, img: np.ndarray, blk_list: List[TextBlock],
                    ocr_model: str = 'geminiamo') -> List[FontDetectionResult]:
        """Detect fonts for all text blocks.

        Args:
            img: Input image as numpy array
            blk_list: List of TextBlock objects
            ocr_model: engine vision da usare ('geminiamo')

        Returns:
            List of FontDetectionResult objects, one per text block
        """
        try:
            # Create OCR engine for font analysis
            engine = self.ocr_factory.create_engine(
                self.settings, 
                'English',  # Language doesn't matter for font detection
                ocr_model
            )
            
            # Check if engine supports font analysis
            if not hasattr(engine, 'analyze_fonts'):
                logger.error(f"OCR engine {ocr_model} doesn't support font analysis")
                return [self._create_fallback_result() for _ in blk_list]
            
            # Perform font analysis
            results = engine.analyze_fonts(img, blk_list)
            
            # Store results in text blocks
            for i, (blk, result) in enumerate(zip(blk_list, results)):
                blk.font_detection_result = result
                logger.info(f"Block {i}: Detected font {result.font_family} ({result.confidence:.2f})")
            
            return results
            
        except Exception as e:
            logger.error(f"Font detection failed: {str(e)}")
            # Return fallback results
            return [self._create_fallback_result() for _ in blk_list]
    
    def detect_font_single_block(self, img: np.ndarray, text_block: TextBlock,
                                ocr_model: str = 'geminiamo') -> FontDetectionResult:
        """Detect font for a single text block.
        
        Args:
            img: Input image as numpy array
            text_block: Single TextBlock object
            ocr_model: OCR model to use
            
        Returns:
            FontDetectionResult object
        """
        results = self.detect_fonts(img, [text_block], ocr_model)
        return results[0] if results else self._create_fallback_result()
    
    def _create_fallback_result(self) -> FontDetectionResult:
        """Create a fallback result when detection fails."""
        return FontDetectionResult(
            font_family="Unknown",
            font_style="normal",
            font_weight="normal",
            font_size_estimate="medium",
            serif_type="sans-serif",
            font_color="#000000",
            confidence=0.0,
            additional_info={"error": "Font detection failed"}
        )
    
    def get_available_models(self) -> List[str]:
        """Get list of available LLM Vision models for font detection."""
        try:
            from ..utils.model_manager import model_manager
            ocr_engines = model_manager.get_ocr_engines()
            
            # Filter for LLM Vision models that support font analysis
            vision_models = []
            for model_name, engine_info in ocr_engines.items():
                engine_type = engine_info.get('engine_type', '')
                if engine_type in ['gpt', 'gemini', 'claude', 'qwen']:
                    vision_models.append(model_name)
            
            return vision_models
            
        except Exception as e:
            logger.error(f"Failed to get available models: {str(e)}")
            return ['GPT-4o', 'Gemini-2.0-Flash-Exp']  # Fallback list
    
    def export_results(self, results: List[FontDetectionResult], 
                      format: str = 'json') -> str:
        """Export font detection results to specified format.
        
        Args:
            results: List of FontDetectionResult objects
            format: Export format ('json', 'csv', 'txt')
            
        Returns:
            Formatted string with results
        """
        if format == 'json':
            return json.dumps([result.to_dict() for result in results], indent=2)
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow(['Font Family', 'Style', 'Weight', 'Size', 'Type', 'Color', 'Confidence'])
            
            # Data
            for result in results:
                writer.writerow([
                    result.font_family,
                    result.font_style,
                    result.font_weight,
                    result.font_size_estimate,
                    result.serif_type,
                    result.font_color,
                    f"{result.confidence:.2f}"
                ])
            
            return output.getvalue()
        
        elif format == 'txt':
            lines = []
            for i, result in enumerate(results):
                lines.append(f"Block {i+1}:")
                lines.append(f"  Font Family: {result.font_family}")
                lines.append(f"  Style: {result.font_style}")
                lines.append(f"  Weight: {result.font_weight}")
                lines.append(f"  Size: {result.font_size_estimate}")
                lines.append(f"  Type: {result.serif_type}")
                lines.append(f"  Color: {result.font_color}")
                lines.append(f"  Confidence: {result.confidence:.2f}")
                lines.append("")
            
            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unsupported export format: {format}")