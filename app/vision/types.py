from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]
    confidence: float
    class_id: int
    track_id: int | None = None

    def crop(self, frame: np.ndarray) -> np.ndarray:
        x1, y1, x2, y2 = self.bbox
        return frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)].copy()

