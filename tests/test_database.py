from datetime import datetime, timedelta

import numpy as np

from app.attendance import AttendanceManager
from app.database import Database


def test_reference_lifecycle_and_match_data(tmp_path):
    db = Database(tmp_path / "attendance.sqlite3")
    vehicle_id = db.add_vehicle("Car A", "Ahmed")
    db.add_reference(vehicle_id, "a.jpg", np.array([1.0, 0.0], dtype=np.float32), "front")
    assert len(db.all_embeddings()) == 1
    image_id = db.reference_images(vehicle_id)[0]["id"]
    db.remove_reference(image_id)
    assert db.all_embeddings() == []


def test_attendance_creates_visit_then_closes_after_timeout(tmp_path):
    db = Database(tmp_path / "attendance.sqlite3")
    vehicle_id = db.add_vehicle("Car A", "Ahmed")
    attendance = AttendanceManager(db, absence_timeout_seconds=60)
    arrival = datetime.now().astimezone() - timedelta(seconds=90)
    attendance.seen(vehicle_id, None, 0.9, 0.9, 5, "test", arrival)
    assert db.vehicle_history(vehicle_id)[0]["status"] == "PRESENT"
    attendance.close_expired(datetime.now().astimezone())
    visit = db.vehicle_history(vehicle_id)[0]
    assert visit["status"] == "LEFT"
    assert visit["departure_time"] == visit["last_seen_time"]

