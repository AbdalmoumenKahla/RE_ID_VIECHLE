from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.ui.common import PageHeader, StatCard, iso_display, status_badge


class DashboardPage(QWidget):
    vehicle_requested = Signal(int)

    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        header_line = QHBoxLayout()
        header_line.addWidget(PageHeader("Vehicle attendance", "A live view of registered vehicles and their latest visit."))
        header_line.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header_line.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header_line)
        cards = QHBoxLayout()
        self.cards = {
            "registered": StatCard("Registered vehicles", "blue"),
            "present": StatCard("Currently present", "green"),
            "left": StatCard("Left today", "purple"),
            "not_seen": StatCard("Not seen today", "gray"),
            "unknown": StatCard("Unknown vehicles", "orange"),
        }
        for card in self.cards.values():
            cards.addWidget(card)
        root.addLayout(cards)
        heading = QLabel("Current attendance")
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Vehicle", "Owner", "Arrival", "Departure", "Last confirmed", "Status"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda row, _: self.vehicle_requested.emit(int(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))))
        root.addWidget(self.table, 1)

    def refresh(self) -> None:
        counts = self.context.database.dashboard_counts()
        for key, card in self.cards.items():
            card.set_value(counts[key])
        rows = self.context.database.dashboard_rows()
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            name = QTableWidgetItem(row["name"])
            name.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.table.setItem(row_index, 0, name)
            self.table.setItem(row_index, 1, QTableWidgetItem(row["owner"] or "—"))
            self.table.setItem(row_index, 2, QTableWidgetItem(iso_display(row["arrival_time"], True)))
            self.table.setItem(row_index, 3, QTableWidgetItem(iso_display(row["departure_time"], True)))
            self.table.setItem(row_index, 4, QTableWidgetItem(iso_display(row["last_seen_time"], True)))
            self.table.setCellWidget(row_index, 5, status_badge(row["attendance_status"]))

