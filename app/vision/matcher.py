from __future__ import annotations

import numpy as np

from app.database import Database


class VehicleMatcher:
    def __init__(self, database: Database, threshold: float) -> None:
        self.database = database
        self.threshold = threshold

    def match(self, query: np.ndarray) -> tuple[int | None, float]:
        query = np.asarray(query, dtype=np.float32).ravel()
        if query.size == 0 or not np.any(query):
            return None, 0.0
        best_vehicle, best_score = None, -1.0
        for vehicle_id, reference in self.database.all_embeddings():
            if reference.shape != query.shape:
                continue
            denom = float(np.linalg.norm(query) * np.linalg.norm(reference))
            score = float(np.dot(query, reference) / denom) if denom else 0.0
            if score > best_score:
                best_vehicle, best_score = vehicle_id, score
        return (best_vehicle, max(0.0, best_score)) if best_score >= self.threshold else (None, max(0.0, best_score))

