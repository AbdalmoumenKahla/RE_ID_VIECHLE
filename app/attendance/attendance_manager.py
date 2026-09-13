from __future__ import annotations

from datetime import datetime, timedelta

from app.database import Database


class AttendanceManager:
    """Turns recognized detections into visit sessions, never per-frame sessions."""

    def __init__(self, database: Database, absence_timeout_seconds: int) -> None:
        self.database = database
        self.absence_timeout_seconds = absence_timeout_seconds

    def seen(self, vehicle_id: int, camera_id: int | None, confidence: float, similarity: float, track_id: int | None, source: str, at: datetime | None = None) -> None:
        seen_at = (at or datetime.now().astimezone()).isoformat(timespec="seconds")
        self.database.open_session(vehicle_id, camera_id, seen_at)

    def close_expired(self, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now().astimezone()) - timedelta(seconds=self.absence_timeout_seconds)
        return self.database.close_expired_sessions(cutoff.isoformat(timespec="seconds"))
