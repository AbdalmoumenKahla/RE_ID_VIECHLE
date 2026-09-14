from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import sys


APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
# A frozen application must not write beside Program Files. Source checkouts
# retain a convenient project-local data directory for development.
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", APP_ROOT)) / "VehicleAttendance" if getattr(sys, "frozen", False) else APP_ROOT / "data"
VEHICLE_DIR = DATA_DIR / "vehicles"
CAPTURE_DIR = DATA_DIR / "captures"
MODEL_DIR = APP_ROOT / "models"
SETTINGS_PATH = DATA_DIR / "settings.json"
DATABASE_PATH = DATA_DIR / "vehicle_attendance.sqlite3"


@dataclass
class AppSettings:
    detection_confidence: float = 0.45
    match_threshold: float = 0.72
    absence_timeout_seconds: int = 60
    processing_fps: int = 12
    camera_url: str = ""
    preferred_device: str = "auto"  # auto, cpu, cuda
    # YOLO26 Medium is the best accuracy/throughput default for a desktop
    # parking installation. Use yolo26n.pt on a weak CPU or yolo26l.pt on a
    # capable CUDA workstation after validating its live-camera FPS.
    yolo_model: str = "yolo26m.pt"
    reid_model_path: str = ""
    database_path: str = str(DATABASE_PATH)

    @classmethod
    def load(cls) -> "AppSettings":
        ensure_data_directories()
        if not SETTINGS_PATH.exists():
            return cls()
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            allowed = {field.name for field in fields(cls)}
            return cls(**{key: value for key, value in raw.items() if key in allowed})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        ensure_data_directories()
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def ensure_data_directories() -> None:
    for directory in (DATA_DIR, VEHICLE_DIR, CAPTURE_DIR, MODEL_DIR):
        directory.mkdir(parents=True, exist_ok=True)
