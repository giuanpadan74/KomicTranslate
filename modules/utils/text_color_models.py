from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


RGBColor = Tuple[int, int, int]
HSLColor = Tuple[float, float, float]


@dataclass(frozen=True)
class ColorSwatch:
    hex: str
    rgb: RGBColor
    hsl: HSLColor
    ratio: float

    def to_dict(self) -> Dict:
        return {
            "hex": self.hex,
            "rgb": list(self.rgb),
            "hsl": list(self.hsl),
            "ratio": float(self.ratio),
        }


@dataclass(frozen=True)
class DetectedTextColor:
    hex: str
    rgb: RGBColor
    hsl: HSLColor
    confidence: float
    is_gradient: bool = False
    palette: List[ColorSwatch] = field(default_factory=list)
    method: str = "image_cluster"

    def to_dict(self) -> Dict:
        return {
            "hex": self.hex,
            "rgb": list(self.rgb),
            "hsl": list(self.hsl),
            "confidence": float(self.confidence),
            "is_gradient": bool(self.is_gradient),
            "palette": [s.to_dict() for s in self.palette],
            "method": self.method,
        }

