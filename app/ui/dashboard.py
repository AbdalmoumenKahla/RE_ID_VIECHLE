from __future__ import annotations

import shutil

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.ui.common import PageHeader, StatCard, iso_display, status_badge


class DashboardPage(QWidget):
    vehicle_requested = Signal(int)
    vehicle_deleted = Signal()

    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 30)
        header_line = QHBoxLayout()
        header_line.addWidget(PageHeader("لوحة الحضور", "عرض مباشر للمركبات المسجّلة وآخر زيارة لكل مركبة."))
        header_line.addStretch()
        refresh = QPushButton("تحديث")
        refresh.clicked.connect(self.refresh)
        header_line.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignTop)
        delete = QPushButton("حذف المركبة المحددة")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self.delete_selected)
        header_line.addWidget(delete, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header_line)
        cards = QHBoxLayout()
        self.cards = {
            "registered": StatCard("المركبات المسجّلة", "blue"),
            "present": StatCard("الموجودة حالياً", "green"),
            "left": StatCard("غادرت اليوم", "purple"),
            "not_seen": StatCard("لم تُر اليوم", "gray"),
            "unknown": StatCard("مركبات غير معروفة", "orange"),
        }
        for card in self.cards.values():
            cards.addWidget(card)
        root.addLayout(cards)
        heading = QLabel("حالة الحضور الحالية")
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["المركبة", "المالك", "وقت الوصول", "وقت المغادرة", "آخر رصد مؤكد", "الحالة"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(52)
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
            self.table.setItem(row_index, 2, QTableWidgetItem(iso_display(row["arrival_time"])))
            self.table.setItem(row_index, 3, QTableWidgetItem(iso_display(row["departure_time"])))
            self.table.setItem(row_index, 4, QTableWidgetItem(iso_display(row["last_seen_time"])))
            self.table.setCellWidget(row_index, 5, status_badge(row["attendance_status"]))

    def delete_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.information(self, "اختر مركبة", "حدد مركبة من الجدول أولاً.")
            return
        row = selection[0].row()
        vehicle_id = int(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        vehicle_name = self.table.item(row, 0).text()
        choice = QMessageBox.question(
            self,
            "تأكيد حذف المركبة",
            f"هل تريد حذف المركبة «{vehicle_name}» وكل صورها وسجل حضورها؟",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        self.context.database.delete_vehicle(vehicle_id)
        shutil.rmtree(self.context.vehicle_dir / str(vehicle_id), ignore_errors=True)
        self.refresh()
        self.vehicle_deleted.emit()
