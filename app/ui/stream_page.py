from __future__ import annotations

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget)

from app.ui.common import PageHeader, VideoCanvas
from app.workers import PhotoRecognitionWorker, StreamWorker


class StreamPage(QWidget):
    stream_stopped = Signal()

    def __init__(self, context, live: bool = False) -> None:
        super().__init__()
        self.context, self.live = context, live
        self.thread: QThread | None = None
        self.worker: StreamWorker | None = None
        self.photo_thread: QThread | None = None
        self.photo_worker: PhotoRecognitionWorker | None = None
        self.source_path = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        if live:
            root.addWidget(PageHeader("الكاميرا المباشرة", "اتصل ببث RTSP/IP محلي. تتم المعالجة وتسجيل الحضور على هذا الحاسوب."))
            source_row = QFormLayout()
            self.source = QLineEdit(context.settings.camera_url)
            self.source.setPlaceholderText("rtsp://192.168.1.100:554/…")
            self.camera_name = QLineEdit("مدخل الموقف")
            source_row.addRow("رابط الكاميرا", self.source)
            source_row.addRow("اسم الكاميرا", self.camera_name)
            root.addLayout(source_row)
        else:
            root.addWidget(PageHeader("اختبار الفيديو", "شغّل فيديو مسجلاً محلياً مع الكشف والمسارات المؤقتة ومطابقات Re-ID وجلسات الحضور."))
            line = QHBoxLayout()
            self.source = QLineEdit()
            self.source.setReadOnly(True)
            self.source.setPlaceholderText("اختر فيديو مسجلاً للاختبار…")
            choose = QPushButton("اختيار فيديو")
            choose.clicked.connect(self.choose_video)
            line.addWidget(self.source, 1)
            line.addWidget(choose)
            root.addLayout(line)
            self.camera_name = QLineEdit("اختبار الفيديو")
        commands = QHBoxLayout()
        self.start = QPushButton("اتصال" if live else "بدء")
        self.start.setObjectName("primaryButton")
        self.start.clicked.connect(self.start_stream)
        self.stop = QPushButton("قطع الاتصال" if live else "إيقاف")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_stream)
        self.photo_test = QPushButton("التعرّف على صورة") if not live else None
        if self.photo_test:
            self.photo_test.clicked.connect(self.recognize_photo)
        commands.addWidget(self.start)
        commands.addWidget(self.stop)
        if self.photo_test:
            commands.addWidget(self.photo_test)
        commands.addStretch()
        self.status = QLabel("جاهز")
        self.status.setObjectName("muted")
        commands.addWidget(self.status)
        root.addLayout(commands)
        body = QHBoxLayout()
        self.canvas = VideoCanvas("اتصل بكاميرا" if live else "اختر فيديو مسجلاً")
        body.addWidget(self.canvas, 3)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        self.metrics = QLabel("الإطارات/ث: —\nالكشف: —\nالتتبع: —\nRe-ID: —\nالجهاز: —")
        self.metrics.setObjectName("metrics")
        side_layout.addWidget(self.metrics)
        side_layout.addWidget(QLabel("سجل التعرّف"))
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(180)
        side_layout.addWidget(self.log_box, 1)
        body.addWidget(side, 1)
        root.addLayout(body, 1)

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "اختيار فيديو", "", "فيديوهات (*.mp4 *.avi *.mov *.mkv);;كل الملفات (*)")
        if path:
            self.source_path = path
            self.source.setText(path)
            self.status.setText("جاهز للبدء")

    def start_stream(self) -> None:
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "المصدر مطلوب", "أدخل رابط RTSP أو اختر فيديو أولاً.")
            return
        if self.live:
            self.context.settings.camera_url = source
            self.context.settings.save()
        self.log_box.clear()
        self.status.setText("جارٍ الاتصال وتحميل النماذج المحلية…")
        self.start.setEnabled(False)
        self.stop.setEnabled(True)
        self.thread = QThread(self)
        self.worker = StreamWorker(source, "Live camera" if self.live else "Video test", str(self.context.database.path), self.context.settings, self.camera_name.text().strip())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.frame_ready.connect(self.canvas.set_image)
        self.worker.telemetry.connect(self.update_metrics)
        self.worker.log.connect(self.log_box.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def stop_stream(self) -> None:
        if self.worker:
            self.status.setText("سيتوقف بعد الإطار الحالي…")
            self.worker.stop()
        self.stop.setEnabled(False)

    def on_finished(self, message: str) -> None:
        self.status.setText(message)
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        self.stream_stopped.emit()

    def on_error(self, message: str) -> None:
        self.status.setText("خطأ في البث")
        self.log_box.appendPlainText(f"خطأ: {message}")
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        self.stream_stopped.emit()

    def update_metrics(self, data: dict) -> None:
        extra = f"\nتحذير: {data['detector_error']}" if data.get("detector_error") else ""
        self.metrics.setText(
            f"الإطارات/ث: {data['fps']:.1f}\n"
            f"الكشف: {data['detection_ms']:.0f} مللي ثانية\n"
            f"التتبع: {data['tracking_ms']:.0f} مللي ثانية\n"
            f"Re-ID: {data['reid_ms']:.0f} مللي ثانية\n"
            f"الجهاز: {data['device']}\n"
            f"التضمين: {data['reid']}{extra}"
        )

    def recognize_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "اختيار صورة للتعرّف عليها", "", "صور (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return
        self.status.setText("جارٍ التعرّف على الصورة…")
        self.photo_test.setEnabled(False)
        self.photo_thread = QThread(self)
        self.photo_worker = PhotoRecognitionWorker(path, str(self.context.database.path), self.context.settings)
        self.photo_worker.moveToThread(self.photo_thread)
        self.photo_thread.started.connect(self.photo_worker.run)
        self.photo_worker.finished.connect(self.photo_recognized)
        self.photo_worker.failed.connect(self.photo_error)
        self.photo_worker.finished.connect(self.photo_thread.quit)
        self.photo_worker.failed.connect(self.photo_thread.quit)
        self.photo_thread.finished.connect(self.photo_worker.deleteLater)
        self.photo_thread.finished.connect(self.photo_thread.deleteLater)
        self.photo_thread.start()

    def photo_recognized(self, image, rows: object, timings: dict, detector_error: str) -> None:
        self.canvas.set_image(image)
        if rows:
            self.log_box.appendPlainText("\n".join(f"المسار {track}: {name} — {similarity:.0%}" for track, name, similarity in rows))
        else:
            self.log_box.appendPlainText(detector_error or "لم يتم العثور على مركبة في هذه الصورة.")
        self.status.setText("اكتمل التعرّف على الصورة")
        self.photo_test.setEnabled(True)

    def photo_error(self, message: str) -> None:
        self.status.setText("فشل التعرّف على الصورة")
        self.log_box.appendPlainText(f"خطأ: {message}")
        self.photo_test.setEnabled(True)

    def close_stream(self) -> None:
        if self.worker:
            self.worker.stop()
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(5000)
        if self.photo_thread and self.photo_thread.isRunning():
            self.photo_thread.quit()
            self.photo_thread.wait(5000)
