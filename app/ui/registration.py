from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from app.ui.common import PageHeader
from app.workers import PhotoAnalysisWorker, RegistrationVideoWorker, store_image


class RegistrationPage(QWidget):
    registered = Signal()

    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        self.photo_crop: np.ndarray | None = None
        self.photo_embedding: np.ndarray | None = None
        self.video_candidates: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self.worker: object | None = None
        self.thread: QThread | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        root.addWidget(PageHeader("تسجيل مركبة", "أنشئ هوية ثابتة من صورة أو من مركبة ممثلة واحدة متتبعة في فيديو."))
        self.tabs = QTabWidget()
        self.tabs.addTab(self._photo_tab(), "من صورة")
        self.tabs.addTab(self._video_tab(), "من فيديو")
        root.addWidget(self.tabs, 1)

    def _form(self, register_callback) -> tuple[QWidget, QLineEdit, QLineEdit]:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        form = QFormLayout()
        name, owner = QLineEdit(), QLineEdit()
        name.setPlaceholderText("مثال: المركبة أ / حافلة المدرسة 2")
        owner.setPlaceholderText("مثال: أحمد")
        form.addRow("اسم المركبة *", name)
        form.addRow("المالك", owner)
        layout.addLayout(form)
        register = QPushButton("تسجيل المركبة")
        register.setObjectName("primaryButton")
        register.clicked.connect(register_callback)
        layout.addWidget(register)
        layout.addStretch()
        return panel, name, owner

    def _photo_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        left, self.photo_name, self.photo_owner = self._form(self.register_photo)
        choose = QPushButton("اختيار صورة")
        choose.clicked.connect(self.choose_photo)
        left.layout().insertWidget(0, choose)
        self.photo_status = QLabel("اختر صورة لاكتشاف المركبة واقتصاصها.")
        self.photo_status.setObjectName("muted")
        self.photo_status.setWordWrap(True)
        left.layout().insertWidget(1, self.photo_status)
        self.photo_preview = QLabel("لا توجد صورة مقصوصة للمركبة بعد")
        self.photo_preview.setObjectName("imagePreview")
        self.photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_preview.setMinimumSize(510, 360)
        layout.addWidget(left, 1)
        layout.addWidget(self.photo_preview, 2)
        return tab

    def _video_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        side, self.video_name, self.video_owner = self._form(self.register_video_candidate)
        choose = QPushButton("اختيار فيديو التسجيل")
        choose.clicked.connect(self.choose_video)
        side.layout().insertWidget(0, choose)
        self.video_progress = QProgressBar()
        self.video_progress.setTextVisible(True)
        side.layout().insertWidget(1, self.video_progress)
        self.video_status = QLabel("يُؤخذ من الفيديو عينات ويُكتشف ويُتتبع. كل نتيجة أدناه مسار مؤقت وليست هوية ثابتة.")
        self.video_status.setWordWrap(True)
        self.video_status.setObjectName("muted")
        side.layout().insertWidget(2, self.video_status)
        self.candidates = QListWidget()
        self.candidates.currentItemChanged.connect(self.preview_candidate)
        self.candidates.setMinimumWidth(440)
        preview_holder = QWidget()
        preview_layout = QVBoxLayout(preview_holder)
        preview_layout.addWidget(QLabel("المركبات المتتبعة الفريدة"))
        preview_layout.addWidget(self.candidates, 1)
        self.video_preview = QLabel("اختر مركبة مكتشفة")
        self.video_preview.setObjectName("imagePreview")
        self.video_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_preview.setMinimumSize(350, 260)
        preview_layout.addWidget(self.video_preview)
        layout.addWidget(side, 1)
        layout.addWidget(preview_holder, 2)
        return tab

    def choose_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "اختيار صورة", "", "صور (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return
        self.photo_status.setText("جارٍ اكتشاف المركبة وتجهيز ميزة Re-ID المحلية…")
        self.photo_crop = None
        self._start_photo_worker(path)

    def _start_photo_worker(self, path: str) -> None:
        self.thread = QThread(self)
        self.worker = PhotoAnalysisWorker(path, str(self.context.database.path), self.context.settings)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.photo_ready)
        self.worker.failed.connect(lambda message: self.photo_status.setText(f"خطأ: {message}"))
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def photo_ready(self, crop: object, embedding: object, image, status: str) -> None:
        self.photo_crop = crop
        self.photo_embedding = embedding
        self.photo_preview.setPixmap(QPixmap.fromImage(image).scaled(self.photo_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.photo_status.setText(status)

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "اختيار فيديو التسجيل", "", "فيديوهات (*.mp4 *.avi *.mov *.mkv);;كل الملفات (*)")
        if not path:
            return
        self.video_candidates.clear()
        self.candidates.clear()
        self.video_progress.setValue(0)
        self.video_status.setText("جارٍ تحميل النموذج المحلي وفحص الفيديو…")
        self.thread = QThread(self)
        self.worker = RegistrationVideoWorker(path, str(self.context.database.path), self.context.settings)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.registration_progress)
        self.worker.candidate.connect(self.add_candidate)
        self.worker.finished.connect(self.registration_finished)
        self.worker.failed.connect(lambda message: self.video_status.setText(f"خطأ: {message}"))
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def registration_progress(self, value: int, message: str) -> None:
        self.video_progress.setValue(value)
        self.video_status.setText(message)

    def add_candidate(self, index: int, crop: object, embedding: object, image, label: str) -> None:
        self.video_candidates[index] = (crop, embedding)
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, index)
        item.setIcon(QIcon(QPixmap.fromImage(image).scaled(92, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
        self.candidates.addItem(item)

    def registration_finished(self, message: str) -> None:
        self.video_progress.setValue(100)
        self.video_status.setText(message)

    def preview_candidate(self, current, previous) -> None:
        if not current:
            return
        candidate = self.video_candidates.get(current.data(Qt.ItemDataRole.UserRole))
        if candidate is not None:
            crop, _ = candidate
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            image = QPixmap.fromImage(QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy())
            self.video_preview.setPixmap(image.scaled(self.video_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _register(self, crop: np.ndarray | None, embedding: np.ndarray | None, name: str, owner: str, label: str) -> bool:
        if crop is None or crop.size == 0:
            QMessageBox.information(self, "اختر مركبة", "حلّل صورة أو اختر مركبة متتبعة من الفيديو أولاً.")
            return False
        if not name.strip():
            QMessageBox.information(self, "اسم المركبة مطلوب", "أدخل اسماً واضحاً للمركبة قبل تسجيلها.")
            return False
        try:
            vehicle_id = self.context.database.add_vehicle(name, owner)
        except Exception as exc:
            QMessageBox.warning(self, "تعذّر التسجيل", f"{exc}\nيجب أن تكون أسماء المركبات فريدة.")
            return False
        target = store_image(crop, self.context.vehicle_dir / str(vehicle_id), "reference")
        if embedding is None:
            QMessageBox.warning(self, "الميزة غير متاحة", "تعذّر إنشاء ميزة Re-ID لهذه المركبة.")
            self.context.database.delete_vehicle(vehicle_id)
            return False
        self.context.database.add_reference(vehicle_id, target, embedding, label)
        QMessageBox.information(self, "تم تسجيل المركبة", f"أصبحت {name.strip()} الآن ملف Re-ID محلياً مع صورة مرجعية واحدة.")
        self.registered.emit()
        return True

    def register_photo(self) -> None:
        if self._register(self.photo_crop, self.photo_embedding, self.photo_name.text(), self.photo_owner.text(), "photo registration"):
            self.photo_crop = None
            self.photo_embedding = None
            self.photo_preview.setText("لا توجد صورة مقصوصة للمركبة بعد")
            self.photo_name.clear()
            self.photo_owner.clear()

    def register_video_candidate(self) -> None:
        item = self.candidates.currentItem()
        candidate = self.video_candidates.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        crop, embedding = candidate if candidate else (None, None)
        if self._register(crop, embedding, self.video_name.text(), self.video_owner.text(), "video registration"):
            self.video_name.clear()
            self.video_owner.clear()
