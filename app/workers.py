from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event
from time import perf_counter, sleep
from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage

from app.attendance import AttendanceManager
from app.config import AppSettings, CAPTURE_DIR, VEHICLE_DIR, ensure_data_directories
from app.database import Database
from app.vision import Recognition, VisionPipeline


def qimage_from_bgr(frame: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888)
    return image.copy()


def store_image(image: np.ndarray, folder: Path, prefix: str) -> str:
    ensure_data_directories()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = folder / f"{prefix}_{stamp}.jpg"
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not save image to {path}")
    return str(path)


class PhotoAnalysisWorker(QObject):
    finished = Signal(object, object, object, str)  # crop, embedding, visual image, status
    failed = Signal(str)

    def __init__(self, path: str, database_path: str, settings: AppSettings) -> None:
        super().__init__()
        self.path, self.database_path, self.settings = path, database_path, settings

    @Slot()
    def run(self) -> None:
        try:
            image = cv2.imread(self.path)
            if image is None:
                raise ValueError("تعذّر فتح الصورة المحددة.")
            pipeline = VisionPipeline(Database(self.database_path), self.settings)
            detections = pipeline.detector.detect(image)
            if detections:
                best = max(detections, key=lambda d: d.confidence)
                crop = best.crop(image)
                status = f"تم اكتشاف مركبة ({best.confidence:.0%}). راجع الصورة المقصوصة ثم سجّلها."
            else:
                crop = image.copy()
                detail = pipeline.detector.error or "لم يتم اكتشاف مركبة"
                status = f"{detail}. يمكن استخدام الصورة الكاملة كمرجع يدوي."
            self.finished.emit(crop, pipeline.embedder.embed(crop), qimage_from_bgr(crop), status)
        except Exception as exc:
            self.failed.emit(str(exc))


class RegistrationVideoWorker(QObject):
    progress = Signal(int, str)
    candidate = Signal(int, object, object, object, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, path: str, database_path: str, settings: AppSettings) -> None:
        super().__init__()
        self.path, self.database_path, self.settings = path, database_path, settings
        self.stop_requested = Event()

    def stop(self) -> None:
        self.stop_requested.set()

    @Slot()
    def run(self) -> None:
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            self.failed.emit("تعذّر فتح الفيديو المحدد.")
            return
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            pipeline = VisionPipeline(Database(self.database_path), self.settings)
            candidates: dict[int, tuple[float, np.ndarray, np.ndarray]] = {}
            frame_number = 0
            # Sampling keeps registration responsive while the tracker still
            # sees consecutive sampled frames.
            sample_every = max(1, int(cap.get(cv2.CAP_PROP_FPS) // max(1, self.settings.processing_fps)))
            while not self.stop_requested.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                frame_number += 1
                if frame_number % sample_every:
                    continue
                for recognition in pipeline.process(frame):
                    crop = recognition.detection.crop(frame)
                    if crop.size == 0 or recognition.detection.track_id is None:
                        continue
                    old = candidates.get(recognition.detection.track_id)
                    if old is None or recognition.detection.confidence > old[0]:
                        candidates[recognition.detection.track_id] = (recognition.detection.confidence, crop, recognition.embedding)
                if frame_number % (sample_every * 15) == 0:
                    self.progress.emit(int(frame_number * 100 / total), f"جارٍ فحص الإطار {frame_number:,} — {len(candidates)} مركبات متتبعة")
            for index, (_, crop, embedding) in enumerate(candidates.values(), start=1):
                self.candidate.emit(index, crop, embedding, qimage_from_bgr(crop), f"المركبة {index}")
            if pipeline.detector.error:
                self.finished.emit(f"اكتمل الفحص، لكن {pipeline.detector.error}")
            else:
                self.finished.emit(f"اكتمل الفحص: تم العثور على {len(candidates)} مركبات متتبعة فريدة.")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            cap.release()


class PhotoRecognitionWorker(QObject):
    """One-off recognition worker so photo tests never block the GUI thread."""

    finished = Signal(QImage, object, dict, str)
    failed = Signal(str)

    def __init__(self, path: str, database_path: str, settings: AppSettings) -> None:
        super().__init__()
        self.path, self.database_path, self.settings = path, database_path, settings

    @Slot()
    def run(self) -> None:
        try:
            frame = cv2.imread(self.path)
            if frame is None:
                raise ValueError("تعذّر فتح الصورة المحددة.")
            pipeline = VisionPipeline(Database(self.database_path), self.settings)
            results = pipeline.process(frame)
            rows = [(item.detection.track_id, item.vehicle_name, item.similarity) for item in results]
            self.finished.emit(qimage_from_bgr(pipeline.annotate(frame, results)), rows, pipeline.timings, pipeline.detector.error or "")
        except Exception as exc:
            self.failed.emit(str(exc))


class StreamWorker(QObject):
    frame_ready = Signal(QImage)
    telemetry = Signal(dict)
    log = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, source: str, source_label: str, database_path: str, settings: AppSettings, camera_name: str = "") -> None:
        super().__init__()
        self.source, self.source_label = source, source_label
        self.database_path, self.settings, self.camera_name = database_path, settings, camera_name
        self.stop_requested = Event()

    def stop(self) -> None:
        self.stop_requested.set()

    @Slot()
    def run(self) -> None:
        capture_source: Any = self.source
        cap = cv2.VideoCapture(capture_source, cv2.CAP_FFMPEG if self.source.lower().startswith("rtsp") else cv2.CAP_ANY)
        if not cap.isOpened():
            self.failed.emit("تعذّر الاتصال بالمصدر. تحقق من المسار أو الرابط ودعم OpenCV وFFmpeg.")
            return
        database = Database(self.database_path)
        camera_id = database.upsert_camera(self.camera_name or self.source_label, self.source) if self.source_label == "Live camera" else None
        pipeline = VisionPipeline(database, self.settings)
        attendance = AttendanceManager(database, self.settings.absence_timeout_seconds)
        last_recorded: dict[tuple[int, int | None], float] = {}
        seen_unknown_tracks: set[int] = set()
        frame_count, started = 0, perf_counter()
        interval = 1.0 / max(1, self.settings.processing_fps)
        try:
            while not self.stop_requested.is_set():
                frame_started = perf_counter()
                ok, frame = cap.read()
                if not ok:
                    break
                frame_count += 1
                results = pipeline.process(frame)
                now_mono = perf_counter()
                for result in results:
                    if result.vehicle_id is not None:
                        key = (result.vehicle_id, result.detection.track_id)
                        # Attendance is refreshed every frame, but the detailed
                        # detection log is throttled to avoid a giant database.
                        attendance.seen(result.vehicle_id, camera_id, result.detection.confidence, result.similarity, result.detection.track_id, self.source_label)
                        if now_mono - last_recorded.get(key, 0) > 3:
                            database.add_detection(result.vehicle_id, camera_id, datetime.now().astimezone().isoformat(timespec="seconds"), result.detection.confidence, result.similarity, result.detection.track_id, self.source_label)
                            self.log.emit(f"{datetime.now():%H:%M:%S}  المسار {result.detection.track_id}  {result.vehicle_name}  {result.similarity:.0%}")
                            last_recorded[key] = now_mono
                    elif (result.detection.track_id or -1) not in seen_unknown_tracks:
                        crop = result.detection.crop(frame)
                        if crop.size:
                            path = store_image(crop, CAPTURE_DIR / "unknown", "unknown")
                            database.record_unknown(path, result.embedding, self.source_label, result.similarity)
                            seen_unknown_tracks.add(result.detection.track_id or -1)
                            self.log.emit(f"{datetime.now():%H:%M:%S}  المسار {result.detection.track_id}  غير معروف  {result.similarity:.0%}")
                attendance.close_expired()
                self.frame_ready.emit(qimage_from_bgr(pipeline.annotate(frame, results)))
                elapsed = max(0.001, perf_counter() - started)
                self.telemetry.emit({
                    "fps": frame_count / elapsed,
                    "device": pipeline.embedder.device_label,
                    "reid": pipeline.embedder.kind,
                    **pipeline.timings,
                    "detector_error": pipeline.detector.error or "",
                })
                wait = interval - (perf_counter() - frame_started)
                if wait > 0:
                    sleep(wait)
            attendance.close_expired()
            self.finished.emit("تم الإيقاف" if self.stop_requested.is_set() else "انتهى الفيديو")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            cap.release()
