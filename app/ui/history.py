from __future__ import annotations

import csv

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.ui.common import PageHeader, duration, iso_display
from app.workers import store_image


class HistoryPage(QWidget):
    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        root.addWidget(PageHeader("Attendance history", "Filter local visit sessions and export them to a CSV file that opens in Microsoft Excel."))
        filters = QHBoxLayout()
        self.date, self.vehicle, self.owner, self.camera = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.date.setPlaceholderText("Date: YYYY-MM-DD")
        self.vehicle.setPlaceholderText("Vehicle")
        self.owner.setPlaceholderText("Owner")
        self.camera.setPlaceholderText("Camera")
        self.status = QComboBox()
        self.status.addItems(["All", "PRESENT", "LEFT"])
        for widget in (self.date, self.vehicle, self.owner, self.camera):
            widget.returnPressed.connect(self.refresh)
        apply = QPushButton("Apply filters")
        apply.clicked.connect(self.refresh)
        export = QPushButton("Export CSV")
        export.clicked.connect(self.export_csv)
        for widget in (self.date, self.vehicle, self.owner, self.camera, self.status, apply, export):
            filters.addWidget(widget)
        root.addLayout(filters)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Vehicle", "Owner", "Date", "Arrival", "Departure", "Duration", "Status"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

    def rows(self):
        return self.context.database.history(self.date.text().strip(), self.vehicle.text().strip(), self.owner.text().strip(), self.status.currentText(), self.camera.text().strip())

    def refresh(self) -> None:
        rows = self.rows()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row["name"], row["owner"] or "—", iso_display(row["arrival_time"])[:11], iso_display(row["arrival_time"], True), iso_display(row["departure_time"], True), duration(row["arrival_time"], row["departure_time"]), row["status"])
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export attendance CSV", "attendance_history.csv", "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["Vehicle", "Owner", "Arrival", "Departure", "Duration", "Status", "Camera"])
                for row in self.rows():
                    writer.writerow([row["name"], row["owner"], row["arrival_time"], row["departure_time"] or "", duration(row["arrival_time"], row["departure_time"]), row["status"], row["camera_name"] or ""])
            QMessageBox.information(self, "Export complete", f"Saved {len(self.rows())} visits to:\n{path}")
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))


class UnknownVehiclesPage(QWidget):
    registered = Signal()

    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        root.addWidget(PageHeader("Unknown vehicles", "Review low-confidence/unmatched sightings and promote one to a permanent registered profile."))
        bar = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        register = QPushButton("Register selected unknown")
        register.setObjectName("primaryButton")
        register.clicked.connect(self.register_selected)
        bar.addWidget(refresh)
        bar.addWidget(register)
        bar.addStretch()
        root.addLayout(bar)
        content = QHBoxLayout()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "First seen", "Last seen", "Source", "Best similarity"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.show_selected)
        content.addWidget(self.table, 2)
        self.preview = QLabel("Select a sighting")
        self.preview.setObjectName("imagePreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(330, 260)
        content.addWidget(self.preview, 1)
        root.addLayout(content, 1)

    def refresh(self) -> None:
        rows = self.context.database.list_unknown()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (str(row["id"]), iso_display(row["first_seen_time"]), iso_display(row["last_seen_time"]), row["source"], f"{row['best_similarity']:.0%}")
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))

    def show_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        unknown = self.context.database.get_unknown(int(self.table.item(selected[0].row(), 0).text()))
        if unknown:
            pixmap = QPixmap(unknown["image_path"])
            self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def register_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Select a sighting", "Choose an unknown vehicle first.")
            return
        unknown = self.context.database.get_unknown(int(self.table.item(selected[0].row(), 0).text()))
        if not unknown:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Register unknown vehicle")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Use the selected crop as the first reference image."))
        name, owner = QLineEdit(), QLineEdit()
        name.setPlaceholderText("Vehicle name")
        owner.setPlaceholderText("Owner")
        form = QFormLayout()
        form.addRow("Vehicle name *", name)
        form.addRow("Owner", owner)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not name.text().strip():
            return
        try:
            image = cv2.imread(unknown["image_path"])
            vehicle_id = self.context.database.add_vehicle(name.text(), owner.text())
            target = store_image(image, self.context.vehicle_dir / str(vehicle_id), "reference")
            embedding = np.frombuffer(unknown["embedding"], dtype=np.float32, count=unknown["dimension"]).copy()
            self.context.database.add_reference(vehicle_id, target, embedding, "promoted unknown sighting")
            self.context.database.resolve_unknown(unknown["id"], vehicle_id)
            self.refresh()
            self.registered.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Registration failed", str(exc))


class SettingsPage(QWidget):
    saved = Signal()

    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        root.addWidget(PageHeader("Settings", "Tune these values against your own camera angles and real recordings. No threshold is universally correct."))
        form = QFormLayout()
        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(0.05, 0.99)
        self.confidence.setSingleStep(0.05)
        self.confidence.setValue(context.settings.detection_confidence)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.05, 0.99)
        self.threshold.setSingleStep(0.01)
        self.threshold.setValue(context.settings.match_threshold)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 3600)
        self.timeout.setValue(context.settings.absence_timeout_seconds)
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(context.settings.processing_fps)
        self.device = QComboBox()
        self.device.addItems(["auto", "cpu", "cuda"])
        self.device.setCurrentText(context.settings.preferred_device)
        self.yolo = QLineEdit(context.settings.yolo_model)
        self.reid_path = QLineEdit(context.settings.reid_model_path)
        self.database_path = QLineEdit(context.settings.database_path)
        form.addRow("Detection confidence", self.confidence)
        form.addRow("Re-ID match threshold", self.threshold)
        form.addRow("Departure timeout (seconds)", self.timeout)
        form.addRow("Processing FPS cap", self.fps)
        form.addRow("Preferred device", self.device)
        form.addRow("YOLO model", self.yolo)
        form.addRow("Local OSNet vehicle Re-ID checkpoint (optional)", self.reid_path)
        form.addRow("Database location", self.database_path)
        root.addLayout(form)
        note = QLabel("Changes apply to new photo/video/camera jobs. Stop and restart an active stream to use them.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)
        save = QPushButton("Save settings")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save)
        root.addWidget(save)
        root.addStretch()

    def save(self) -> None:
        settings = self.context.settings
        settings.detection_confidence = self.confidence.value()
        settings.match_threshold = self.threshold.value()
        settings.absence_timeout_seconds = self.timeout.value()
        settings.processing_fps = self.fps.value()
        settings.preferred_device = self.device.currentText()
        settings.yolo_model = self.yolo.text().strip() or "yolo11n.pt"
        settings.reid_model_path = self.reid_path.text().strip()
        settings.database_path = self.database_path.text().strip() or settings.database_path
        settings.save()
        self.saved.emit()
        QMessageBox.information(self, "Settings saved", "Restart an active stream for these settings to take effect.")
