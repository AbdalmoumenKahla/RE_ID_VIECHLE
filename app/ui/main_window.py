from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from app.config import AppSettings, VEHICLE_DIR, ensure_data_directories
from app.database import Database
from app.ui.dashboard import DashboardPage
from app.ui.history import HistoryPage, SettingsPage, UnknownVehiclesPage
from app.ui.registration import RegistrationPage
from app.ui.stream_page import StreamPage
from app.ui.vehicles import VehicleProfileDialog, VehiclesPage
from app.vision.reid import VehicleEmbedder


class AppContext:
    def __init__(self) -> None:
        ensure_data_directories()
        self.settings = AppSettings.load()
        self.database = Database(self.settings.database_path)
        self.vehicle_dir = VEHICLE_DIR

    def make_embedder(self) -> VehicleEmbedder:
        return VehicleEmbedder(self.settings.preferred_device, self.settings.reid_model_path)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.context = AppContext()
        self.setWindowTitle("Vehicle Attendance System")
        self.setMinimumSize(1150, 720)
        self.resize(1440, 900)
        self._build()
        self.refresh_all()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start(2500)

    def _build(self) -> None:
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(244)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 24, 18, 20)
        brand = QLabel("PARKWISE")
        brand.setObjectName("brand")
        sub = QLabel("VEHICLE ATTENDANCE")
        sub.setObjectName("brandSub")
        side.addWidget(brand)
        side.addWidget(sub)
        side.addSpacing(32)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setSpacing(4)
        for title in ("Dashboard", "Vehicles", "Register vehicle", "Live camera", "Video testing", "Attendance history", "Unknown vehicles", "Settings"):
            item = QListWidgetItem(title)
            item.setSizeHint(item.sizeHint().expandedTo(QSize(0, 43)))
            self.navigation.addItem(item)
        self.navigation.currentRowChanged.connect(self.change_page)
        side.addWidget(self.navigation, 1)
        local = QLabel("LOCAL-FIRST\nSQLite · YOLO · Re-ID")
        local.setObjectName("localBadge")
        side.addWidget(local)
        outer_layout.addWidget(sidebar)
        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(self.context)
        self.vehicles = VehiclesPage(self.context)
        self.registration = RegistrationPage(self.context)
        self.live = StreamPage(self.context, live=True)
        self.video = StreamPage(self.context, live=False)
        self.history = HistoryPage(self.context)
        self.unknown = UnknownVehiclesPage(self.context)
        self.settings_page = SettingsPage(self.context)
        self.pages = [self.dashboard, self.vehicles, self.registration, self.live, self.video, self.history, self.unknown, self.settings_page]
        for page in self.pages:
            self.stack.addWidget(page)
        outer_layout.addWidget(self.stack, 1)
        self.setCentralWidget(outer)
        self.navigation.setCurrentRow(0)
        self.dashboard.vehicle_requested.connect(self.open_profile)
        self.vehicles.open_profile.connect(self.open_profile)
        self.registration.registered.connect(self.refresh_all)
        self.unknown.registered.connect(self.refresh_all)
        self.live.stream_stopped.connect(self.refresh_all)
        self.video.stream_stopped.connect(self.refresh_all)

    def change_page(self, index: int) -> None:
        if index >= 0:
            self.stack.setCurrentIndex(index)
            page = self.pages[index]
            if hasattr(page, "refresh"):
                page.refresh()

    def refresh_all(self) -> None:
        self.dashboard.refresh()
        self.vehicles.refresh()
        self.history.refresh()
        self.unknown.refresh()

    def open_profile(self, vehicle_id: int) -> None:
        dialog = VehicleProfileDialog(self.context, vehicle_id, self)
        dialog.exec()
        self.refresh_all()

    def closeEvent(self, event) -> None:
        if self.live.worker or self.video.worker:
            choice = QMessageBox.question(self, "Exit Vehicle Attendance", "A source may still be processing. Stop it and exit?")
            if choice != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.live.close_stream()
            self.video.close_stream()
        event.accept()


APP_STYLE = """
QMainWindow, QWidget { background: #f4f7fb; color: #172033; font-family: 'Segoe UI'; font-size: 13px; }
QFrame#sidebar { background: #10223d; color: #e7eefb; }
QLabel#brand { color: #ffffff; font-size: 21px; font-weight: 800; letter-spacing: 1px; }
QLabel#brandSub { color: #9db3d0; font-size: 10px; font-weight: 700; letter-spacing: 1.4px; }
QListWidget#navigation { border: 0; outline: 0; background: transparent; color: #bdd0ea; font-size: 14px; }
QListWidget#navigation::item { border-radius: 8px; padding: 11px 14px; margin: 1px 0; }
QListWidget#navigation::item:selected { background: #2064d8; color: #ffffff; font-weight: 700; }
QListWidget#navigation::item:hover:!selected { background: #1a3559; color: #ffffff; }
QLabel#localBadge { border: 1px solid #294a73; color: #9db3d0; border-radius: 7px; padding: 10px; font-size: 10px; font-weight: 700; }
QLabel#pageTitle { font-size: 27px; font-weight: 750; color: #13213a; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; color: #172033; margin-top: 12px; }
QLabel#muted { color: #66738a; }
QFrame#statCard { background: #ffffff; border: 1px solid #e1e8f2; border-radius: 11px; min-height: 88px; }
QLabel#statValue { color: #152a4a; font-size: 27px; font-weight: 750; }
QLabel#statLabel { color: #68768d; font-size: 11px; font-weight: 600; }
QPushButton { background: #ffffff; border: 1px solid #d6dfeb; border-radius: 7px; padding: 8px 13px; color: #24334a; font-weight: 600; }
QPushButton:hover { border-color: #6d94d6; background: #f8fbff; }
QPushButton:disabled { color: #9aa8ba; background: #eef2f7; }
QPushButton#primaryButton { background: #2165d8; color: white; border: 0; }
QPushButton#primaryButton:hover { background: #1854b8; }
QPushButton#dangerButton { color: #bc3434; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit { background: #ffffff; border: 1px solid #d8e0ec; border-radius: 6px; padding: 7px 9px; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #2064d8; }
QTableWidget, QListWidget, QPlainTextEdit { background: #ffffff; border: 1px solid #dde5ef; border-radius: 8px; gridline-color: #edf1f6; alternate-background-color: #f9fbfd; }
QTableWidget::item { padding: 8px; }
QHeaderView::section { background: #edf3fa; color: #53627a; border: 0; padding: 9px; font-weight: 700; }
QLabel#videoCanvas, QLabel#imagePreview { background: #101b2d; color: #a9bdd8; border: 1px solid #253a57; border-radius: 10px; }
QLabel#metrics { background: #ffffff; border: 1px solid #dde5ef; border-radius: 8px; padding: 13px; color: #506078; font-family: Consolas; }
QLabel#presentBadge { background: #ddf6e7; color: #177743; border-radius: 9px; padding: 4px 8px; font-size: 11px; font-weight: 700; }
QLabel#leftBadge { background: #eceff4; color: #5f6d7e; border-radius: 9px; padding: 4px 8px; font-size: 11px; font-weight: 700; }
QLabel#neutralBadge { background: #fff2dc; color: #ab6610; border-radius: 9px; padding: 4px 8px; font-size: 11px; font-weight: 700; }
QLabel#dialogTitle { font-size: 21px; font-weight: 700; }
QLabel#profileStatus { background: #e8f6ed; color: #177743; border-radius: 8px; padding: 12px; font-weight: 700; }
QTabBar::tab { padding: 10px 18px; }
QTabBar::tab:selected { color: #1c5dca; font-weight: 700; }
"""


def start_application() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Vehicle Attendance System")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
