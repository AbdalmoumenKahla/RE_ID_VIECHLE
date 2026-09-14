from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np


class Database:
    """Thread-safe-by-connection SQLite repository for the local application."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connection() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS vehicles (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    owner TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vehicle_images (
                    id INTEGER PRIMARY KEY,
                    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                    image_path TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vehicle_embeddings (
                    id INTEGER PRIMARY KEY,
                    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                    image_id INTEGER REFERENCES vehicle_images(id) ON DELETE CASCADE,
                    embedding BLOB NOT NULL,
                    dimension INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cameras (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attendance_sessions (
                    id INTEGER PRIMARY KEY,
                    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                    camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
                    arrival_time TEXT NOT NULL,
                    departure_time TEXT,
                    last_seen_time TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PRESENT', 'LEFT'))
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_status ON attendance_sessions(status, last_seen_time);
                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY,
                    vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL,
                    camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
                    timestamp TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    similarity REAL,
                    track_id INTEGER,
                    source TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS unknown_vehicles (
                    id INTEGER PRIMARY KEY,
                    image_path TEXT NOT NULL,
                    embedding BLOB,
                    dimension INTEGER,
                    first_seen_time TEXT NOT NULL,
                    last_seen_time TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    best_similarity REAL NOT NULL DEFAULT 0,
                    resolved_vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL
                );
                """
            )
            columns = {row["name"] for row in con.execute("PRAGMA table_info(vehicle_embeddings)")}
            if "image_id" not in columns:  # compatibility with early prototype databases
                con.execute("ALTER TABLE vehicle_embeddings ADD COLUMN image_id INTEGER")

    @staticmethod
    def now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def add_vehicle(self, name: str, owner: str) -> int:
        with self.connection() as con:
            cursor = con.execute(
                "INSERT INTO vehicles(name, owner, created_at) VALUES (?, ?, ?)",
                (name.strip(), owner.strip(), self.now()),
            )
            return int(cursor.lastrowid)

    def update_vehicle(self, vehicle_id: int, name: str, owner: str) -> None:
        with self.connection() as con:
            con.execute("UPDATE vehicles SET name=?, owner=? WHERE id=?", (name.strip(), owner.strip(), vehicle_id))

    def delete_vehicle(self, vehicle_id: int) -> None:
        with self.connection() as con:
            con.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))

    def get_vehicle(self, vehicle_id: int) -> sqlite3.Row | None:
        with self.connection() as con:
            return con.execute("SELECT * FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()

    def list_vehicles(self, search: str = "") -> list[sqlite3.Row]:
        query = "SELECT * FROM vehicles"
        params: Sequence[object] = ()
        if search.strip():
            query += " WHERE name LIKE ? OR owner LIKE ?"
            term = f"%{search.strip()}%"
            params = (term, term)
        query += " ORDER BY name COLLATE NOCASE"
        with self.connection() as con:
            return con.execute(query, params).fetchall()

    def add_reference(self, vehicle_id: int, image_path: str, embedding: np.ndarray, label: str = "") -> None:
        emb = np.asarray(embedding, dtype=np.float32).ravel()
        with self.connection() as con:
            cursor = con.execute(
                "INSERT INTO vehicle_images(vehicle_id,image_path,label,created_at) VALUES (?,?,?,?)",
                (vehicle_id, image_path, label.strip(), self.now()),
            )
            image_id = int(cursor.lastrowid)
            con.execute(
                "INSERT INTO vehicle_embeddings(vehicle_id,image_id,embedding,dimension,created_at) VALUES (?,?,?,?,?)",
                (vehicle_id, image_id, emb.tobytes(), int(emb.size), self.now()),
            )

    def reference_images(self, vehicle_id: int) -> list[sqlite3.Row]:
        with self.connection() as con:
            return con.execute("SELECT * FROM vehicle_images WHERE vehicle_id=? ORDER BY id DESC", (vehicle_id,)).fetchall()

    def remove_reference(self, image_id: int) -> None:
        with self.connection() as con:
            con.execute("DELETE FROM vehicle_embeddings WHERE image_id=?", (image_id,))
            con.execute("DELETE FROM vehicle_images WHERE id=?", (image_id,))

    def all_embeddings(self) -> list[tuple[int, np.ndarray]]:
        with self.connection() as con:
            rows = con.execute("SELECT vehicle_id, embedding, dimension FROM vehicle_embeddings").fetchall()
        return [(int(row["vehicle_id"]), np.frombuffer(row["embedding"], dtype=np.float32, count=row["dimension"]).copy()) for row in rows]

    def upsert_camera(self, name: str, url: str) -> int:
        with self.connection() as con:
            row = con.execute("SELECT id FROM cameras WHERE url=?", (url,)).fetchone()
            if row:
                return int(row["id"])
            cursor = con.execute("INSERT INTO cameras(name,url,created_at) VALUES(?,?,?)", (name, url, self.now()))
            return int(cursor.lastrowid)

    def open_session(self, vehicle_id: int, camera_id: int | None, at: str) -> int:
        with self.connection() as con:
            row = con.execute(
                "SELECT id FROM attendance_sessions WHERE vehicle_id=? AND camera_id IS ? AND status='PRESENT'",
                (vehicle_id, camera_id),
            ).fetchone()
            if row:
                con.execute("UPDATE attendance_sessions SET last_seen_time=? WHERE id=?", (at, row["id"]))
                return int(row["id"])
            cursor = con.execute(
                "INSERT INTO attendance_sessions(vehicle_id,camera_id,arrival_time,last_seen_time,status) VALUES(?,?,?,?, 'PRESENT')",
                (vehicle_id, camera_id, at, at),
            )
            return int(cursor.lastrowid)

    def refresh_session(self, vehicle_id: int, camera_id: int | None, at: str) -> None:
        with self.connection() as con:
            con.execute(
                "UPDATE attendance_sessions SET last_seen_time=? WHERE vehicle_id=? AND camera_id IS ? AND status='PRESENT'",
                (at, vehicle_id, camera_id),
            )

    def close_expired_sessions(self, cutoff: str) -> int:
        with self.connection() as con:
            cursor = con.execute(
                "UPDATE attendance_sessions SET departure_time=last_seen_time,status='LEFT' WHERE status='PRESENT' AND last_seen_time < ?",
                (cutoff,),
            )
            return cursor.rowcount

    def add_detection(self, vehicle_id: int | None, camera_id: int | None, at: str, confidence: float, similarity: float | None, track_id: int | None, source: str) -> None:
        with self.connection() as con:
            con.execute(
                "INSERT INTO detections(vehicle_id,camera_id,timestamp,confidence,similarity,track_id,source) VALUES(?,?,?,?,?,?,?)",
                (vehicle_id, camera_id, at, confidence, similarity, track_id, source),
            )

    def record_unknown(self, image_path: str, embedding: np.ndarray, source: str, similarity: float) -> int:
        emb = np.asarray(embedding, dtype=np.float32).ravel()
        now = self.now()
        with self.connection() as con:
            cursor = con.execute(
                "INSERT INTO unknown_vehicles(image_path,embedding,dimension,first_seen_time,last_seen_time,source,best_similarity) VALUES(?,?,?,?,?,?,?)",
                (image_path, emb.tobytes(), int(emb.size), now, now, source, similarity),
            )
            return int(cursor.lastrowid)

    def list_unknown(self, only_open: bool = True) -> list[sqlite3.Row]:
        query = "SELECT u.*, v.name AS resolved_name FROM unknown_vehicles u LEFT JOIN vehicles v ON v.id=u.resolved_vehicle_id"
        if only_open:
            query += " WHERE u.resolved_vehicle_id IS NULL"
        query += " ORDER BY u.last_seen_time DESC"
        with self.connection() as con:
            return con.execute(query).fetchall()

    def get_unknown(self, unknown_id: int) -> sqlite3.Row | None:
        with self.connection() as con:
            return con.execute("SELECT * FROM unknown_vehicles WHERE id=?", (unknown_id,)).fetchone()

    def delete_unknown(self, unknown_id: int) -> None:
        with self.connection() as con:
            con.execute("DELETE FROM unknown_vehicles WHERE id=?", (unknown_id,))

    def delete_all_unknown(self) -> list[str]:
        with self.connection() as con:
            rows = con.execute(
                "SELECT image_path FROM unknown_vehicles WHERE resolved_vehicle_id IS NULL"
            ).fetchall()
            con.execute("DELETE FROM unknown_vehicles WHERE resolved_vehicle_id IS NULL")
            return [str(row["image_path"]) for row in rows]

    def resolve_unknown(self, unknown_id: int, vehicle_id: int) -> None:
        with self.connection() as con:
            con.execute("UPDATE unknown_vehicles SET resolved_vehicle_id=? WHERE id=?", (vehicle_id, unknown_id))

    def dashboard_rows(self) -> list[sqlite3.Row]:
        with self.connection() as con:
            return con.execute(
                """
                SELECT v.*, s.arrival_time, s.departure_time, s.last_seen_time,
                       COALESCE(s.status, 'NOT SEEN') AS attendance_status
                FROM vehicles v
                LEFT JOIN attendance_sessions s ON s.id = (
                  SELECT id FROM attendance_sessions x WHERE x.vehicle_id=v.id
                  ORDER BY CASE x.status WHEN 'PRESENT' THEN 0 ELSE 1 END, x.arrival_time DESC LIMIT 1
                ) ORDER BY v.name COLLATE NOCASE
                """
            ).fetchall()

    def dashboard_counts(self) -> dict[str, int]:
        with self.connection() as con:
            registered = int(con.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0])
            present = int(con.execute("SELECT COUNT(DISTINCT vehicle_id) FROM attendance_sessions WHERE status='PRESENT'").fetchone()[0])
            today = datetime.now().astimezone().date().isoformat()
            left = int(con.execute("SELECT COUNT(*) FROM attendance_sessions WHERE status='LEFT' AND departure_time LIKE ?", (today + "%",)).fetchone()[0])
            unknown = int(con.execute("SELECT COUNT(*) FROM unknown_vehicles WHERE resolved_vehicle_id IS NULL").fetchone()[0])
        return {"registered": registered, "present": present, "left": left, "not_seen": max(0, registered - present - left), "unknown": unknown}

    def vehicle_history(self, vehicle_id: int) -> list[sqlite3.Row]:
        with self.connection() as con:
            return con.execute("SELECT * FROM attendance_sessions WHERE vehicle_id=? ORDER BY arrival_time DESC", (vehicle_id,)).fetchall()

    def history(self, date_value: str = "", vehicle: str = "", owner: str = "", status: str = "", camera: str = "") -> list[sqlite3.Row]:
        clauses, params = ["1=1"], []
        if date_value:
            clauses.append("s.arrival_time LIKE ?")
            params.append(date_value + "%")
        if vehicle:
            clauses.append("v.name LIKE ?")
            params.append("%" + vehicle + "%")
        if owner:
            clauses.append("v.owner LIKE ?")
            params.append("%" + owner + "%")
        if status and status != "All":
            clauses.append("s.status=?")
            params.append(status)
        if camera:
            clauses.append("COALESCE(c.name, '') LIKE ?")
            params.append("%" + camera + "%")
        query = """SELECT s.*, v.name, v.owner, c.name AS camera_name FROM attendance_sessions s
                   JOIN vehicles v ON v.id=s.vehicle_id LEFT JOIN cameras c ON c.id=s.camera_id
                   WHERE """ + " AND ".join(clauses) + " ORDER BY s.arrival_time DESC"
        with self.connection() as con:
            return con.execute(query, params).fetchall()
