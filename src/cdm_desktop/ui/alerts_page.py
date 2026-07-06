from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import AlertRepository, EventRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.export_service import ExportService
from cdm_desktop.services.recycle_bin_service import RecycleBinService
from cdm_desktop.services.ui_query_service import get_alert_cards, get_home_summary
from cdm_desktop.ui.company_detail_dialog import CompanyDetailDialog
from cdm_desktop.ui.widgets import (
    AlertCard,
    EmptyState,
    EvidenceDialog,
    MetricCard,
    clear_layout,
    info,
    make_scroll_area,
    warn,
)


class AlertsPage(QWidget):
    page_title = "告警中心"
    primary_action_text = "全部标记已读"

    def __init__(self, db: DatabaseManager, paths: AppPaths) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        self.global_query = ""
        layout = QVBoxLayout(self)

        summary = QHBoxLayout()
        self.unread_metric = MetricCard("未读告警")
        self.high_metric = MetricCard("P0/P1")
        self.last_scan_metric = MetricCard("最近采集")
        for card in [self.unread_metric, self.high_metric, self.last_scan_metric]:
            summary.addWidget(card)
        layout.addLayout(summary)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("收件箱"))
        self.filter = QComboBox()
        for label, value in [("未读", "unread"), ("高优先级", "high"), ("已处理", "processed"), ("已忽略", "ignored"), ("全部", "all")]:
            self.filter.addItem(label, value)
        self.filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.filter)
        export_csv_btn = QPushButton("导出 CSV")
        export_xlsx_btn = QPushButton("导出 Excel")
        export_csv_btn.clicked.connect(self.export_csv)
        export_xlsx_btn.clicked.connect(self.export_xlsx)
        filters.addWidget(export_csv_btn)
        filters.addWidget(export_xlsx_btn)
        filters.addStretch()
        layout.addLayout(filters)

        self.scroll, _content, self.cards_layout = make_scroll_area()
        layout.addWidget(self.scroll, 1)
        self.refresh()

    def set_global_query(self, query: str) -> None:
        self.global_query = query.strip()
        self.refresh()

    def run_primary_action(self) -> None:
        self.mark_all_read()

    def refresh(self) -> None:
        clear_layout(self.cards_layout)
        with self.db.session() as session:
            summary = get_home_summary(session)
            cards = get_alert_cards(
                session,
                inbox_filter=self.filter.currentData() or "unread",
                query=self.global_query,
            )
        self.unread_metric.set_value(summary.unread_alerts)
        self.high_metric.set_value(summary.high_priority_alerts)
        self.last_scan_metric.set_value(summary.last_scan_at.strftime("%m-%d %H:%M") if summary.last_scan_at else "未采集")

        if not cards:
            self.cards_layout.addWidget(EmptyState("还没有未读告警", "需要处理的告警会出现在这里。"))
            self.cards_layout.addStretch()
            return
        for card in cards:
            self.cards_layout.addWidget(
                AlertCard(
                    company_name=card.company_name,
                    priority=card.priority,
                    title=card.title,
                    message=card.message,
                    status=card.status,
                    confidence_score=card.confidence_score,
                    materiality_score=card.materiality_score,
                    created_text=card.created_at.strftime("%Y-%m-%d %H:%M"),
                    evidence=card.evidence,
                    on_evidence=lambda event_id=card.event_id: self.open_evidence(event_id),
                    on_ack=lambda alert_id=card.id: self.set_status(alert_id, "acknowledged"),
                    on_ignore=lambda alert_id=card.id: self.set_status(alert_id, "ignored"),
                    on_company=lambda company_id=card.company_id: self.open_company(company_id),
                    on_delete=lambda alert_id=card.id, title=card.title: self.delete_alert(alert_id, title),
                )
            )
        self.cards_layout.addStretch()

    def set_status(self, alert_id: int, status: str) -> None:
        with self.db.session() as session:
            AlertRepository(session).set_status(alert_id, status)
        self.refresh()

    def delete_alert(self, alert_id: int, title: str) -> None:
        result = QMessageBox.question(
            self,
            "删除告警",
            f"确定删除告警「{title}」吗？\n\n删除后会进入回收站，可在设置 → 回收站恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.db.session() as session:
                RecycleBinService(session).move_alert_to_recycle(alert_id)
        except Exception as exc:
            warn(self, f"删除失败：{exc}")
            return
        self.refresh()
        info(self, "告警已移入回收站")

    def mark_all_read(self) -> None:
        with self.db.session() as session:
            alerts = AlertRepository(session).list(status="unread", limit=10_000)
            repo = AlertRepository(session)
            for alert in alerts:
                repo.set_status(alert.id, "acknowledged")
        self.refresh()

    def export_csv(self) -> None:
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "导出告警 CSV",
            str(self.paths.exports_dir / "alerts.csv"),
            "CSV (*.csv)",
        )
        if not path_text:
            return
        with self.db.session() as session:
            result = ExportService(self.paths).export_alerts_csv(session, Path(path_text))
        info(self, f"已导出 {result.row_count} 条告警：{result.path}")

    def export_xlsx(self) -> None:
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "导出告警 Excel",
            str(self.paths.exports_dir / "alerts.xlsx"),
            "Excel (*.xlsx)",
        )
        if not path_text:
            return
        try:
            with self.db.session() as session:
                result = ExportService(self.paths).export_alerts_xlsx(session, Path(path_text))
            info(self, f"已导出 {result.row_count} 条告警：{result.path}")
        except RuntimeError as exc:
            warn(self, str(exc))

    def open_evidence(self, event_id: int) -> None:
        with self.db.session() as session:
            evidence = EventRepository(session).evidence_for_event(event_id)
        EvidenceDialog("告警证据", [item.snippet for item in evidence], self).exec()

    def open_company(self, company_id: int) -> None:
        CompanyDetailDialog(self.db, self.paths, company_id, self).exec()
        self.refresh()
