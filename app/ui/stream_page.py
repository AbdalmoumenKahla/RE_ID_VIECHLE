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
            root.addWidget(PageHeader("Live camera", "Connect to a local RTSP/IP stream. Processing and attendance stay on this computer."))
            source_row = QFormLayout()
            self.source = QLineEdit(context.settings.camera_url)
            self.source.setPlaceholderText("rtsp://192.168.1.100:554/…")
            self.camera_name = QLineEdit("Parking entrance")
            source_row.addRow("Camera URL", self.source)
            source_row.addRow("Camera name", self.camera_name)
            root.addLayout(source_row)
        else:
            root.addWidget(PageHeader("Video testing", "Run a recorded video locally with detection, temporary tracks, Re-ID matches, and attendance sessions."))
            line = QHBoxLayout()
            self.source = QLineEdit()
            self.source.setReadOnly(True)
            self.source.setPlaceholderText("Choose a recorded video to test…")
            choose = QPushButton("Select video")
            choose.clicked.connect(self.choose_video)
            line.addWidget(self.source, 1)
            line.addWidget(choose)
            root.addLayout(line)
            self.camera_name = QLineEdit("Video testing")
        commands = QHBoxLayout()
        self.start = QPushButton("Connect" if live else "Start")
        self.start.setObjectName("primaryButton")
        self.start.clicked.connect(self.start_stream)
        self.stop = QPushButton("Disconnect" if live else "Stop")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_stream)
        self.photo_test = QPushButton("Recognize photo") if not live else None
        if self.photo_test:
            self.photo_test.clicked.connect(self.recognize_photo)
        commands.addWidget(self.start)
        commands.addWidget(self.stop)
        if self.photo_test:
            commands.addWidget(self.photo_test)
        commands.addStretch()
        self.status = QLabel("Idle")
        self.status.setObjectName("muted")
        commands.addWidget(self.status)
        root.addLayout(commands)
        body = QHBoxLayout()
        self.canvas = VideoCanvas("Connect to a camera" if live else "Select a recorded video")
        body.addWidget(self.canvas, 3)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        self.metrics = QLabel("FPS: —\nDetection: —\nTracking: —\nRe-ID: —\nDevice: —")
        self.metrics.setObjectName("metrics")
        side_layout.addWidget(self.metrics)
        side_layout.addWidget(QLabel("Recognition log"))
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(180)
        side_layout.addWidget(self.log_box, 1)
        body.addWidget(side, 1)
        root.addLayout(body, 1)

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose video", "", "Videos (*.mp4 *.avi *.mov *.mkv);;All files (*)")
        if path:
            self.source_path = path
            self.source.setText(path)
            self.status.setText("Ready to start")

    def start_stream(self) -> None:
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "Source required", "Enter an RTSP URL or select a video first.")
            return
        if self.live:
            self.context.settings.camera_url = source
            self.context.settings.save()
        self.log_box.clear()
        self.status.setText("Connecting and loading local models…")
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
            self.status.setText("Stopping after the current frame…")
            self.worker.stop()
        self.stop.setEnabled(False)

    def on_finished(self, message: str) -> None:
        self.status.setText(message)
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        self.stream_stopped.emit()

    def on_error(self, message: str) -> None:
        self.status.setText("Stream error")
        self.log_box.appendPlainText(f"ERROR: {message}")
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        self.stream_stopped.emit()

    def update_metrics(self, data: dict) -> None:
        extra = f"\nWarning: {data['detector_error']}" if data.get("detector_error") else ""
        self.metrics.setText(
            f"FPS: {data['fps']:.1f}\n"
            f"Detection: {data['detection_ms']:.0f} ms\n"
            f"Tracking: {data['tracking_ms']:.0f} ms\n"
            f"Re-ID: {data['reid_ms']:.0f} ms\n"
            f"Device: {data['device']}\n"
            f"Embedding: {data['reid']}{extra}"
        )

    def recognize_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose photo to recognize", "", "Images (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return
        self.status.setText("Recognizing photo…")
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
            self.log_box.appendPlainText("\n".join(f"Track {track}: {name} — {similarity:.0%}" for track, name, similarity in rows))
        else:
            self.log_box.appendPlainText(detector_error or "No vehicle found in this photo.")
        self.status.setText("Photo recognition complete")
        self.photo_test.setEnabled(True)

    def photo_error(self, message: str) -> None:
        self.status.setText("Photo recognition failed")
        self.log_box.appendPlainText(f"ERROR: {message}")
        self.photo_test.setEnabled(True)

    def close_stream(self) -> None:
        if self.worker:
            self.worker.stop()
