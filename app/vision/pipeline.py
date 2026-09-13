from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import cv2
import numpy as np

from app.config import AppSettings
from app.database import Database

from .detector import VehicleDetector
from .matcher import VehicleMatcher
from .reid import VehicleEmbedder
from .tracker import CentroidTracker
from .types import Detection


@dataclass
class Recognition:
    detection: Detection
    vehicle_id: int | None
    vehicle_name: str
    owner: str
    similarity: float
    embedding: np.ndarray


class VisionPipeline:
    """Detection → tracking → embedding → matching. Track IDs never identify cars."""

    def __init__(self, database: Database, settings: AppSettings) -> None:
        self.database = database
        self.detector = VehicleDetector(settings.yolo_model, settings.detection_confidence, settings.preferred_device)
        self.tracker = CentroidTracker()
        self.embedder = VehicleEmbedder(settings.preferred_device, settings.reid_model_path)
        self.matcher = VehicleMatcher(database, settings.match_threshold)
        self.timings = {"detection_ms": 0.0, "reid_ms": 0.0, "tracking_ms": 0.0}

    def process(self, frame: np.ndarray) -> list[Recognition]:
        began = perf_counter()
        detected = self.detector.detect_and_track(frame)
        after_detection = perf_counter()
        # Use YOLO's ByteTrack IDs when available; use the local centroid
        # adapter only when the runtime cannot provide tracker IDs.
        tracked = detected if detected and all(item.track_id is not None for item in detected) else self.tracker.update(detected)
        after_tracking = perf_counter()
        results: list[Recognition] = []
        for detection in tracked:
            crop = detection.crop(frame)
            if crop.size == 0:
                continue
            embedding = self.embedder.embed(crop)
            vehicle_id, similarity = self.matcher.match(embedding)
            vehicle = self.database.get_vehicle(vehicle_id) if vehicle_id else None
            results.append(Recognition(detection, vehicle_id, vehicle["name"] if vehicle else "Unknown", vehicle["owner"] if vehicle else "", similarity, embedding))
        after_reid = perf_counter()
        self.timings = {
            "detection_ms": (after_detection - began) * 1000,
            "tracking_ms": (after_tracking - after_detection) * 1000,
            "reid_ms": (after_reid - after_tracking) * 1000,
        }
        return results

    def annotate(self, frame: np.ndarray, results: list[Recognition]) -> np.ndarray:
        canvas = frame.copy()
        for result in results:
            x1, y1, x2, y2 = result.detection.bbox
            known = result.vehicle_id is not None
            colour = (40, 190, 98) if known else (40, 160, 240)
            label = f"{result.vehicle_name}  {result.similarity:.0%}  T{result.detection.track_id or '-'}"
            cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, 2)
            cv2.rectangle(canvas, (x1, max(0, y1 - 24)), (min(canvas.shape[1], x1 + 310), y1), colour, -1)
            cv2.putText(canvas, label, (x1 + 5, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 24, 30), 1, cv2.LINE_AA)
        return canvas
