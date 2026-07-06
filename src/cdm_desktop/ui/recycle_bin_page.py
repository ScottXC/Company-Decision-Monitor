from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.services.recycle_bin_service import (
    RECYCLE_TYPE_ALERT,
    RECYCLE_TYPE_EVENT,
    RECYCLE_TYPE_WATCHLIST,
    RecycleBinService,
)
from cdm_desktop.ui.widgets import EmptyState, clear_layout, info, selected_id, set_table_rows

RECYCLE_TYPE_LABELS = {
    RECYCLE_TYPE_EVENT: "事件",
    RECYCLE_TYPE_ALERT: "告警",
    RECYCLE_TYPE_WATCHLIST: "自选公司",
}


class RecycleBinPage(QWidget):
    def __init__(self, db: DatabaseManager, refresh_callback: Callable[[], None]) -> None:
        super().__init__()
        self.db = db
        self.refresh_callback = refresh_callback

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("类型"))
        self.type_filter = QComboBox()
        self.type_filter.addItem("全部", None)
        self.type_filter.addItem("事件", RECYCLE_TYPE_EVENT)
        self.type_filter.addItem("告警", RECYCLE_TYPE_ALERT)
        self.type_filter.addItem("自选公司", RECYCLE_TYPE_WATCHLIST)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        restore_btn = QPushButton("恢复")
        restore_btn.setObjectName("PrimaryButton")
        restore_btn.clicked.connect(self.restore_selected)
        delete_btn = QPushButton("永久删除")
        delete_btn.setObjectName("DangerButton")
        delete_btn.clicked.connect(self.permanently_delete_selected)
        top.addWidget(self.type_filter)
        top.addWidget(restore_btn)
        top.addWidget(delete_btn)
        top.addStretch()
        layout.addLayout(top)

        note = QLabel("回收站保存删除的事件、告警和自选公司。恢复后会回到对应列表；永久删除不可撤销。")
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.empty_container = QVBoxLayout()
        layout.addLayout(self.empty_container)
        self.table = QTableWidget()
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        clear_layout(self.empty_container)
        with self.db.session() as session:
            items = RecycleBinService(session).list_items(item_type=self.type_filter.currentData())
        self.table.setVisible(bool(items))
        if not items:
            self.empty_container.addWidget(EmptyState("回收站为空", "删除的事件、告警或自选公司会显示在这里。"))
            set_table_rows(self.table, ["ID", "类型", "标题", "说明", "删除时间"], [], [])
            return
        set_table_rows(
            self.table,
            ["ID", "类型", "标题", "说明", "删除时间"],
            [
                [
                    item.id,
                    RECYCLE_TYPE_LABELS.get(item.item_type, item.item_type),
                    item.title,
                    item.description,
                    item.deleted_at_text,
                ]
                for item in items
            ],
            [item.id for item in items],
        )

    def restore_selected(self) -> None:
        item_id = selected_id(self.table)
        if item_id is None:
            return
        with self.db.session() as session:
            RecycleBinService(session).restore(item_id)
        self.refresh_callback()
        self.refresh()
        info(self, "已恢复")

    def permanently_delete_selected(self) -> None:
        item_id = selected_id(self.table)
        if item_id is None:
            return
        result = QMessageBox.question(
            self,
            "永久删除",
            "确定永久删除选中的回收站项目吗？该操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        with self.db.session() as session:
            RecycleBinService(session).permanently_delete(item_id)
        self.refresh_callback()
        self.refresh()
        info(self, "已永久删除")
