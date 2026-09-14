from __future__ import annotations

import csv
import os

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
        root.addWidget(PageHeader("سجل الحضور", "صفِّ جلسات الزيارة المحلية وصدّرها إلى ملف CSV يمكن فتحه في Microsoft Excel."))
        filters = QHBoxLayout()
        self.date, self.vehicle, self.owner, self.camera = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.date.setPlaceholderText("التاريخ: YYYY-MM-DD")
        self.vehicle.setPlaceholderText("المركبة")
        self.owner.setPlaceholderText("المالك")
        self.camera.setPlaceholderText("الكاميرا")
        self.status = QComboBox()
        self.status.addItems(["الكل", "موجود", "غادر"])
        for widget in (self.date, self.vehicle, self.owner, self.camera):
            widget.returnPressed.connect(self.refresh)
        apply = QPushButton("تطبيق الفلاتر")
        apply.clicked.connect(self.refresh)
        export = QPushButton("تصدير CSV")
        export.clicked.connect(self.export_csv)
        for widget in (self.date, self.vehicle, self.owner, self.camera, self.status, apply, export):
            filters.addWidget(widget)
        root.addLayout(filters)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["المركبة", "المالك", "التاريخ", "الوصول", "المغادرة", "المدة", "الحالة"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

    def rows(self):
        status = {"الكل": "All", "موجود": "PRESENT", "غادر": "LEFT"}[self.status.currentText()]
        return self.context.database.history(self.date.text().strip(), self.vehicle.text().strip(), self.owner.text().strip(), status, self.camera.text().strip())

    def refresh(self) -> None:
        rows = self.rows()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row["name"], row["owner"] or "—", iso_display(row["arrival_time"])[:11], iso_display(row["arrival_time"], True), iso_display(row["departure_time"], True), duration(row["arrival_time"], row["departure_time"]), row["status"])
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "تصدير سجل الحضور CSV", "attendance_history.csv", "ملفات CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["المركبة", "المالك", "الوصول", "المغادرة", "المدة", "الحالة", "الكاميرا"])
                for row in self.rows():
                    writer.writerow([row["name"], row["owner"], row["arrival_time"], row["departure_time"] or "", duration(row["arrival_time"], row["departure_time"]), row["status"], row["camera_name"] or ""])
            QMessageBox.information(self, "اكتمل التصدير", f"تم حفظ {len(self.rows())} زيارة في:\n{path}")
        except OSError as exc:
            QMessageBox.warning(self, "فشل التصدير", str(exc))


class UnknownVehiclesPage(QWidget):
    registered = Signal()
    deleted = Signal()

    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        root.addWidget(PageHeader("مركبات غير معروفة", "راجع الرصد منخفض الثقة أو غير المطابق، وحوّل أحدها إلى ملف مسجّل دائم."))
        bar = QHBoxLayout()
        refresh = QPushButton("تحديث")
        refresh.clicked.connect(self.refresh)
        register = QPushButton("تسجيل المركبة المحددة")
        register.setObjectName("primaryButton")
        register.clicked.connect(self.register_selected)
        bar.addWidget(refresh)
        bar.addWidget(register)
        delete = QPushButton("حذف المركبة المحددة")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self.delete_selected)
        bar.addWidget(delete)
        delete_all = QPushButton("حذف جميع غير المعروفة")
        delete_all.setObjectName("dangerButton")
        delete_all.clicked.connect(self.delete_all)
        bar.addWidget(delete_all)
        bar.addStretch()
        root.addLayout(bar)
        content = QHBoxLayout()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["المعرّف", "أول رصد", "آخر رصد", "المصدر", "أفضل تطابق"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.show_selected)
        content.addWidget(self.table, 2)
        self.preview = QLabel("اختر رصداً")
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
            QMessageBox.information(self, "اختر رصداً", "اختر مركبة غير معروفة أولاً.")
            return
        unknown = self.context.database.get_unknown(int(self.table.item(selected[0].row(), 0).text()))
        if not unknown:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("تسجيل مركبة غير معروفة")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("استخدم الصورة المحددة كأول صورة مرجعية."))
        name, owner = QLineEdit(), QLineEdit()
        name.setPlaceholderText("اسم المركبة")
        owner.setPlaceholderText("المالك")
        form = QFormLayout()
        form.addRow("اسم المركبة *", name)
        form.addRow("المالك", owner)
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
            QMessageBox.warning(self, "فشل التسجيل", str(exc))

    def delete_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "اختر مركبة", "حدد مركبة غير معروفة من الجدول أولاً.")
            return
        row = selected[0].row()
        unknown_id = int(self.table.item(row, 0).text())
        unknown = self.context.database.get_unknown(unknown_id)
        if not unknown:
            return
        choice = QMessageBox.question(
            self,
            "تأكيد حذف المركبة",
            "هل تريد حذف هذا الرصد والصورة المحفوظة؟",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        self.context.database.delete_unknown(unknown_id)
        try:
            os.remove(unknown["image_path"])
        except OSError:
            pass
        self.refresh()
        self.preview.clear()
        self.deleted.emit()

    def delete_all(self) -> None:
        count = len(self.context.database.list_unknown())
        if not count:
            QMessageBox.information(self, "لا توجد مركبات", "لا توجد مركبات غير معروفة لحذفها.")
            return
        choice = QMessageBox.question(
            self,
            "تأكيد حذف الكل",
            f"هل تريد حذف جميع المركبات غير المعروفة ({count}) وصورها المحفوظة؟",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        for image_path in self.context.database.delete_all_unknown():
            try:
                os.remove(image_path)
            except OSError:
                pass
        self.refresh()
        self.preview.clear()
        self.deleted.emit()


class SettingsPage(QWidget):
    saved = Signal()

    def __init__(self, context) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
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
        settings.yolo_model = self.yolo.text().strip() or "yolo26m.pt"
        settings.reid_model_path = self.reid_path.text().strip()
        settings.database_path = self.database_path.text().strip() or settings.database_path
        settings.save()
        self.saved.emit()
        QMessageBox.information(self, "Settings saved", "Restart an active stream for these settings to take effect.")
