from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


def iso_display(value: str | None, short: bool = False) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%H:%M:%S") if short else parsed.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return value


def duration(arrival: str | None, departure: str | None = None) -> str:
    if not arrival:
        return "—"
    try:
        start = datetime.fromisoformat(arrival)
        end = datetime.fromisoformat(departure) if departure else datetime.now().astimezone()
        seconds = max(0, int((end - start).total_seconds()))
        hours, seconds = divmod(seconds, 3600)
        minutes = seconds // 60
        return f"{hours}h {minutes:02d}m"
    except ValueError:
        return "—"


class StatCard(QFrame):
    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setProperty("accent", accent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        self.value = QLabel("0")
        self.value.setObjectName("statValue")
        label = QLabel(title)
        label.setObjectName("statLabel")
        layout.addWidget(self.value)
        layout.addWidget(label)

    def set_value(self, value: int | str) -> None:
        self.value.setText(str(value))


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        if subtitle:
            text = QLabel(subtitle)
            text.setObjectName("muted")
            text.setWordWrap(True)
            layout.addWidget(text)


class VideoCanvas(QLabel):
    def __init__(self, text: str = "No video source selected") -> None:
        super().__init__(text)
        self.setObjectName("videoCanvas")
        self.setMinimumSize(640, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWordWrap(True)

    def set_image(self, image) -> None:
        pixmap = QPixmap.fromImage(image)
        self.setPixmap(pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        if self.pixmap() and not self.pixmap().isNull():
            self.setPixmap(self.pixmap().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        super().resizeEvent(event)


def status_badge(status: str) -> QLabel:
    label = QLabel(status)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setObjectName("presentBadge" if status == "PRESENT" else "leftBadge" if status == "LEFT" else "neutralBadge")
    return label

