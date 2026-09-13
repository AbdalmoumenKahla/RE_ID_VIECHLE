from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .types import Detection


@dataclass
class _Track:
    track_id: int
    center: tuple[float, float]
    missed: int = 0


class CentroidTracker:
    """Fallback MOT tracker when Ultralytics ByteTrack is not installed.

    The normal stream path uses Ultralytics ByteTrack. Recognition is
    deliberately independent of either temporary track number.
    """

    def __init__(self, max_distance: float = 120.0, max_missed: int = 25) -> None:
        self.max_distance, self.max_missed = max_distance, max_missed
        self._next_id, self._tracks = 1, {}

    @staticmethod
    def _center(detection: Detection) -> tuple[float, float]:
        x1, y1, x2, y2 = detection.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def update(self, detections: Iterable[Detection]) -> list[Detection]:
        detections = list(detections)
        available = set(self._tracks)
        for detection in detections:
            center = self._center(detection)
            candidate = None
            best_distance = self.max_distance
            for track_id in available:
                x, y = self._tracks[track_id].center
                distance = ((x - center[0]) ** 2 + (y - center[1]) ** 2) ** 0.5
                if distance < best_distance:
                    candidate, best_distance = track_id, distance
            if candidate is None:
                candidate = self._next_id
                self._next_id += 1
                self._tracks[candidate] = _Track(candidate, center)
            else:
                available.remove(candidate)
                self._tracks[candidate].center = center
                self._tracks[candidate].missed = 0
            detection.track_id = candidate
        for track_id in list(available):
            self._tracks[track_id].missed += 1
            if self._tracks[track_id].missed > self.max_missed:
                del self._tracks[track_id]
        return detections
