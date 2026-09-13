from __future__ import annotations

import numpy as np

from .types import Detection


VEHICLE_CLASSES = {2, 3, 5, 7}  # COCO: car, motorcycle, bus, truck


class VehicleDetector:
    """Local Ultralytics YOLO detector with its built-in ByteTrack adapter."""

    def __init__(self, model_name: str, confidence: float, device: str = "auto") -> None:
        self.model_name = model_name
        self.confidence = confidence
        self.device = None if device == "auto" else device
        self._model = None
        self.error: str | None = None

    def _load(self) -> None:
        if self._model is not None or self.error:
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_name)
        except Exception as exc:
            self.error = f"YOLO unavailable: {exc}"

    @property
    def ready(self) -> bool:
        self._load()
        return self._model is not None

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Detection-only path used for one-off photo cropping."""
        self._load()
        if self._model is None:
            return []
        try:
            result = self._model.predict(frame, conf=self.confidence, classes=list(VEHICLE_CLASSES), device=self.device, verbose=False)[0]
            return self._boxes_to_detections(result.boxes)
        except Exception as exc:
            self.error = f"YOLO inference error: {exc}"
            return []

    def detect_and_track(self, frame: np.ndarray) -> list[Detection]:
        """Run the local YOLO + ByteTrack pipeline; no tracker ID is an identity."""
        self._load()
        if self._model is None:
            return []
        try:
            result = self._model.track(
                frame, persist=True, tracker="bytetrack.yaml", conf=self.confidence,
                classes=list(VEHICLE_CLASSES), device=self.device, verbose=False,
            )[0]
            return self._boxes_to_detections(result.boxes, include_tracks=True)
        except Exception as exc:
            # Fall back to local detection; VisionPipeline's centroid adapter
            # supplies a temporary track only if the packaged ByteTrack fails.
            self.error = f"ByteTrack inference error: {exc}"
            return self.detect(frame)

    @staticmethod
    def _boxes_to_detections(boxes, include_tracks: bool = False) -> list[Detection]:
        if boxes is None:
            return []
        detections: list[Detection] = []
        for box in boxes:
            xyxy = box.xyxy[0].cpu().numpy().astype(int).tolist()
            track_id = int(box.id[0]) if include_tracks and box.id is not None else None
            detections.append(Detection(tuple(xyxy), float(box.conf[0]), int(box.cls[0]), track_id))
        return detections

