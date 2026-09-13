from __future__ import annotations

from pathlib import Path

import cv2
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.ui.common import PageHeader, duration, iso_display, status_badge
from app.workers import store_image


class VehicleProfileDialog(QDialog):
    def __init__(self, context, vehicle_id: int, parent=None) -> None:
        super().__init__(parent)
        self.context, self.vehicle_id = context, vehicle_id
        self.setWindowTitle("Vehicle profile")
        self.resize(900, 650)
        root = QVBoxLayout(self)
        self.header = QLabel()
        self.header.setObjectName("dialogTitle")
        root.addWidget(self.header)
        splitter = QSplitter()
        left, right = QWidget(), QWidget()
        left_layout, right_layout = QVBoxLayout(left), QVBoxLayout(right)
        self.status = QLabel()
        self.status.setObjectName("profileStatus")
        left_layout.addWidget(self.status)
        self.references = QListWidget()
        self.references.setMinimumWidth(330)
        self.references.currentItemChanged.connect(self.show_reference)
        left_layout.addWidget(QLabel("Reference images"))
        left_layout.addWidget(self.references, 1)
        buttons = QHBoxLayout()
        add = QPushButton("Add reference image")
        add.clicked.connect(self.add_reference)
        remove = QPushButton("Remove selected")
        remove.setObjectName("dangerButton")
        remove.clicked.connect(self.remove_reference)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        left_layout.addLayout(buttons)
        self.preview = QLabel("Choose a reference image")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(390, 270)
        self.preview.setObjectName("imagePreview")
        right_layout.addWidget(self.preview)
        right_layout.addWidget(QLabel("Attendance history"))
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["Date", "Arrival", "Departure", "Duration"])
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.verticalHeader().hide()
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.history, 1)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([360, 540])
        root.addWidget(splitter, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        root.addWidget(close)
        self.refresh()

    def refresh(self) -> None:
        vehicle = self.context.database.get_vehicle(self.vehicle_id)
        if vehicle is None:
            self.reject()
            return
        sessions = self.context.database.vehicle_history(self.vehicle_id)
        latest = sessions[0] if sessions else None
        self.header.setText(f"{vehicle['name']}  ·  {vehicle['owner'] or 'No owner'}")
        if latest and latest["status"] == "PRESENT":
            self.status.setText(f"PRESENT\nArrived {iso_display(latest['arrival_time'])}  ·  {duration(latest['arrival_time'])}")
        else:
            self.status.setText("NOT CURRENTLY PRESENT")
        refs = self.context.database.reference_images(self.vehicle_id)
        self.references.clear()
        for ref in refs:
            item = QListWidgetItem(ref["label"] or Path(ref["image_path"]).name)
            item.setData(Qt.ItemDataRole.UserRole, dict(ref))
            self.references.addItem(item)
        self.history.setRowCount(len(sessions))
        for index, session in enumerate(sessions):
            self.history.setItem(index, 0, QTableWidgetItem(iso_display(session["arrival_time"])[:11]))
            self.history.setItem(index, 1, QTableWidgetItem(iso_display(session["arrival_time"], True)))
            self.history.setItem(index, 2, QTableWidgetItem(iso_display(session["departure_time"], True)))
            self.history.setItem(index, 3, QTableWidgetItem(duration(session["arrival_time"], session["departure_time"])))

    def show_reference(self, item, previous) -> None:
        if not item:
            return
        reference = item.data(Qt.ItemDataRole.UserRole)
        pixmap = QPixmap(reference["image_path"])
        self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def add_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose vehicle reference", "", "Images (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return
        image = cv2.imread(path)
        if image is None:
            QMessageBox.warning(self, "Invalid image", "The selected image could not be opened.")
            return
        # Adding a reference is intentionally crop-preserving: it lets staff
        # include front/side/rear viewpoints that YOLO may crop differently.
        embedder = self.context.make_embedder()
        target = store_image(image, self.context.vehicle_dir / str(self.vehicle_id), "reference")
        self.context.database.add_reference(self.vehicle_id, target, embedder.embed(image), Path(path).stem)
        self.refresh()

    def remove_reference(self) -> None:
        item = self.references.currentItem()
        if not item:
            return
        reference = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Remove reference", "Remove this visual reference and its embedding?") == QMessageBox.StandardButton.Yes:
            self.context.database.remove_reference(reference["id"])
            self.preview.clear()
            self.refresh()


class VehiclesPage(QWidget):
    open_profile = Signal(int)

    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        root.addWidget(PageHeader("Vehicles", "Manage identity profiles and add reference images from different views."))
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search vehicle or owner…")
        self.search.textChanged.connect(self.refresh)
        tools.addWidget(self.search, 1)
        profile = QPushButton("Open profile")
        profile.clicked.connect(self.open_selected)
        tools.addWidget(profile)
        root.addLayout(tools)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Vehicle", "Owner", "References", "Created", "Vehicle ID"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setColumnHidden(4, True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_selected())
        root.addWidget(self.table, 1)

    def refresh(self) -> None:
        rows = self.context.database.list_vehicles(self.search.text())
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.table.setItem(index, 0, QTableWidgetItem(row["name"]))
            self.table.setItem(index, 1, QTableWidgetItem(row["owner"] or "—"))
            self.table.setItem(index, 2, QTableWidgetItem(str(len(self.context.database.reference_images(row["id"])))))
            self.table.setItem(index, 3, QTableWidgetItem(iso_display(row["created_at"])))
            self.table.setItem(index, 4, QTableWidgetItem(str(row["id"])))

    def open_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        if selection:
            self.open_profile.emit(int(self.table.item(selection[0].row(), 4).text()))

