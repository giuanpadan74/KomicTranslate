"""Font Detection Module for Comic Translate."""

from .font_detector import FontDetector, FontDetectionResult
from .font_detection_dialog import FontDetectionDialog
from .font_installer import FontInstaller

__all__ = [
    'FontDetector',
    'FontDetectionResult', 
    'FontDetectionDialog',
    'FontInstaller'
]