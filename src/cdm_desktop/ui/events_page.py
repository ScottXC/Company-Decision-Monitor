from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import AlertRepository, CompanyRepository, EventRepository
from cdm_desktop.event_engine.taxonomy import EVENT_DEFINITIONS
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.export_service import ExportService
from cdm_desktop.services.recycle_bin_service import RecycleBinService
from cdm_desktop.services.ui_query_service import get_event_cards
from cdm_desktop.ui.company_detail_dialog import CompanyDetailDialog
from cdm_desktop.ui.event_detail_dialog import EventDetailDialog
from cdm_desktop.ui.widgets import (
    EmptyState,
    EventCard,
    EvidenceDialog,
    clear_layout,
    info,
    make_scroll_area,
    warn,
)


class EventsPage(QWidget):
    page_title = "事件动态"
    primary_action_text = "导出 CSV"

    def __init__(self, db: DatabaseManager, paths: AppPaths) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        self.global_query = ""
        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        self.company_filter = QComboBox()
        self.type_filter = QComboBox()
        self.status_filter = QComboBox()
        self.priority_filter = QComboBox()
        self.date_filter = QComboBox()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索事件标题、摘要或类型")

        self.type_filter.addItem("全部类型", "")
        for event_type, definition in EVENT_DEFINITIONS.items():
            self.type_filter.addItem(definition.display_name_zh, event_type)
        self.status_filter.addItem("全部状态", "")
        for status, label in [
            ("rumored", "传闻"),
            ("proposed", "拟议"),
            ("board_approved", "董事会通过"),
            ("shareholder_approved", "股东大会通过"),
            ("announced", "已公告"),
            ("completed", "已完成"),
            ("terminated", "已终止"),
            ("denied", "已否认"),
            ("unknown", "未知"),
        ]:
            self.status_filter.addItem(label, status)
        self.priority_filter.addItem("全部优先级", "")
        for priority, label in [("P0", "严重"), ("P1", "高"), ("P2", "中"), ("P3", "低")]:
            self.priority_filter.addItem(label, priority)
        for label, value in [("全部时间", "all"), ("今天", "today"), ("近 7 天", "7d"), ("近 30 天", "30d")]:
            self.date_filter.addItem(label, value)
        for widget in [self.company_filter, self.type_filter, self.status_filter, self.priority_filter, self.date_filter]:
            widget.currentIndexChanged.connect(self.refresh)
            filters.addWidget(widget)
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 1)
        export_csv_btn = QPushButton("导出 CSV")
        export_xlsx_btn = QPushButton("导出 Excel")
        export_csv_btn.clicked.connect(self.export_csv)
        export_xlsx_btn.clicked.connect(self.export_xlsx)
        filters.addWidget(export_csv_btn)
        filters.addWidget(export_xlsx_btn)
        layout.addLayout(filters)

        self.scroll, _content, self.cards_layout = make_scroll_area()
        layout.addWidget(self.scroll, 1)
        self._refresh_company_filter()
        self.refresh()

    def set_global_query(self, query: str) -> None:
        self.global_query = query.strip()
        self.refresh()

    def run_primary_action(self) -> None:
        self.export_csv()

    def _refresh_company_filter(self) -> None:
        current = self.company_filter.currentData()
        self.company_filter.blockSignals(True)
        self.company_filter.clear()
        self.company_filter.addItem("全部公司", None)
        with self.db.session() as session:
            for company in CompanyRepository(session).list():
                self.company_filter.addItem(company.name, company.id)
        if current:
            index = self.company_filter.findData(current)
            self.company_filter.setCurrentIndex(max(0, index))
        self.company_filter.blockSignals(False)

    def refresh(self) -> None:
        clear_layout(self.cards_layout)
        query = self.global_query or self.search.text().strip()
        with self.db.session() as session:
            cards = get_event_cards(
                session,
                company_id=self.company_filter.currentData(),
                event_type=self.type_filter.currentData() or None,
                status=self.status_filter.currentData() or None,
                priority=self.priority_filter.currentData() or None,
                query=query,
                date_range=self.date_filter.currentData() or "all",
            )
        if not cards:
            self.cards_layout.addWidget(EmptyState("还没有检测到事件", "请先添加公司和数据源，然后点击立即采集。"))
            self.cards_layout.addStretch()
            return
        for card in cards:
            self.cards_layout.addWidget(
                EventCard(
                    company_name=card.company_name,
                    priority=card.priority,
                    title=card.title,
                    event_type=EVENT_DEFINITIONS.get(card.event_type).display_name_zh
                    if card.event_type in EVENT_DEFINITIONS
                    else card.event_type,
                    event_status=card.event_status,
                    confidence_score=card.confidence_score,
                    materiality_score=card.materiality_score,
                    source_label=card.source_label,
                    created_text=card.created_at.strftime("%Y-%m-%d %H:%M"),
                    evidence=card.evidence,
                    on_evidence=lambda event_id=card.id: self.open_evidence(event_id),
                    on_company=lambda company_id=card.company_id: self.open_company(company_id),
                    on_detail=lambda event_id=card.id: EventDetailDialog(self.db, event_id, self).exec(),
                    on_ack=(lambda alert_id=card.alert_id: self.set_alert_status(alert_id)) if card.alert_id else None,
                    on_delete=lambda event_id=card.id, title=card.title: self.delete_event(event_id, title),
                )
            )
        self.cards_layout.addStretch()

    def open_evidence(self, event_id: int) -> None:
        with self.db.session() as session:
            evidence = EventRepository(session).evidence_for_event(event_id)
        EvidenceDialog("事件证据", [item.snippet for item in evidence], self).exec()

    def open_company(self, company_id: int) -> None:
        CompanyDetailDialog(self.db, self.paths, company_id, self).exec()
        self._refresh_company_filter()
        self.refresh()

    def set_alert_status(self, alert_id: int) -> None:
        with self.db.session() as session:
            AlertRepository(session).set_status(alert_id, "acknowledged")
        self.refresh()

    def delete_event(self, event_id: int, title: str) -> None:
        result = QMessageBox.question(
            self,
            "删除事件",
            f"确定删除事件「{title}」吗？\n\n删除后会进入回收站，可在设置 → 回收站恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.db.session() as session:
                RecycleBinService(session).move_event_to_recycle(event_id)
        except Exception as exc:
            warn(self, f"删除失败：{exc}")
            return
        self.refresh()
        info(self, "事件已移入回收站")

    def export_csv(self) -> None:
        path_text, _ = QFileDialog.getSaveFileName(self, "导出事件 CSV", str(self.paths.exports_dir / "events.csv"), "CSV (*.csv)")
        if not path_text:
            return
        with self.db.session() as session:
            result = ExportService(self.paths).export_events_csv(session, Path(path_text))
        info(self, f"已导出 {result.row_count} 条事件：{result.path}")

    def export_xlsx(self) -> None:
        path_text, _ = QFileDialog.getSaveFileName(self, "导出事件 Excel", str(self.paths.exports_dir / "events.xlsx"), "Excel (*.xlsx)")
        if not path_text:
            return
        try:
            with self.db.session() as session:
                result = ExportService(self.paths).export_events_xlsx(session, Path(path_text))
            info(self, f"已导出 {result.row_count} 条事件：{result.path}")
        except RuntimeError as exc:
            warn(self, str(exc))
