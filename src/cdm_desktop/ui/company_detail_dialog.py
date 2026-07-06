from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import delete, select

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.models import (
    Alert,
    Company,
    CompanyAlias,
    Document,
    DocumentCompanyMatch,
    Event,
    EventEvidence,
    WatchlistItem,
)
from cdm_desktop.db.repositories import AlertRepository, CompanyRepository, EventRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.company_summary_service import CompanySummaryService
from cdm_desktop.services.export_service import ExportService
from cdm_desktop.services.ingestion_service import IngestionService
from cdm_desktop.services.recycle_bin_service import RecycleBinService
from cdm_desktop.services.ui_query_service import (
    company_related_documents,
    company_related_sources,
    get_alert_cards,
    get_event_cards,
)
from cdm_desktop.services.watchlist_service import WatchlistService
from cdm_desktop.ui.event_detail_dialog import EventDetailDialog
from cdm_desktop.ui.widgets import (
    AlertCard,
    Card,
    CompanySummaryHeader,
    EmptyState,
    EventCard,
    EvidenceDialog,
    MetricCard,
    RemoveWatchlistConfirmDialog,
    TextViewerDialog,
    clear_layout,
    info,
    make_scroll_area,
    selected_id,
    set_table_rows,
    warn,
)


class CompanyDetailDialog(QDialog):
    def __init__(self, db: DatabaseManager, paths: AppPaths, company_id: int, parent: object | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.paths = paths
        self.company_id = company_id
        self.document_ids: list[int] = []
        self.document_urls: dict[int, str] = {}
        self.setWindowTitle("公司详情")
        self.resize(1040, 760)

        layout = QVBoxLayout(self)
        self.header = CompanySummaryHeader()
        action_row = QHBoxLayout()
        for text, callback, primary in [
            ("立即扫描", self.scan_now, True),
            ("添加别名", self.add_alias, False),
            ("删除自选", self.remove_from_watchlist, False),
            ("导出该公司数据", self.export_events, False),
        ]:
            button = QPushButton(text)
            if primary:
                button.setObjectName("PrimaryButton")
            button.clicked.connect(callback)
            action_row.addWidget(button)
        action_row.addStretch()
        self.header.layout.addLayout(action_row)
        layout.addWidget(self.header)

        self.tabs = QTabWidget()
        self.summary_tab = Card("Card")
        self.events_scroll, _events_content, self.events_layout = make_scroll_area()
        self.alerts_scroll, _alerts_content, self.alerts_layout = make_scroll_area()
        self.documents_tab = QWidget()
        self.aliases_tab = QWidget()
        self.sources_table = QTableWidget()
        self.advanced_tab = QWidget()
        self._build_summary_tab()
        self._build_documents_tab()
        self._build_aliases_tab()
        self._build_advanced_tab()
        self.tabs.addTab(self.summary_tab, "概览")
        self.tabs.addTab(self.events_scroll, "事件")
        self.tabs.addTab(self.alerts_scroll, "告警")
        self.tabs.addTab(self.documents_tab, "证据/文档")
        self.tabs.addTab(self.aliases_tab, "别名")
        self.tabs.addTab(self.sources_table, "来源")
        self.tabs.addTab(self.advanced_tab, "高级")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def _build_summary_tab(self) -> None:
        layout = QVBoxLayout(self.summary_tab)
        cards = QHBoxLayout()
        self.recent_events_metric = MetricCard("最近 7 天事件")
        self.unread_alerts_metric = MetricCard("未读告警")
        self.total_events_metric = MetricCard("累计事件")
        self.documents_metric = MetricCard("相关文档")
        for card in [self.recent_events_metric, self.unread_alerts_metric, self.total_events_metric, self.documents_metric]:
            cards.addWidget(card)
        layout.addLayout(cards)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("MutedText")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        layout.addStretch()

    def _build_documents_tab(self) -> None:
        layout = QVBoxLayout(self.documents_tab)
        buttons = QHBoxLayout()
        view_btn = QPushButton("查看文本")
        view_btn.clicked.connect(self.open_selected_document_text)
        url_btn = QPushButton("打开来源 URL")
        url_btn.clicked.connect(self.open_selected_document_url)
        buttons.addWidget(view_btn)
        buttons.addWidget(url_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.documents_table = QTableWidget()
        layout.addWidget(self.documents_table, 1)

    def _build_aliases_tab(self) -> None:
        layout = QVBoxLayout(self.aliases_tab)
        buttons = QHBoxLayout()
        add_btn = QPushButton("添加别名")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self.add_alias)
        edit_btn = QPushButton("编辑别名")
        edit_btn.clicked.connect(self.edit_alias)
        delete_btn = QPushButton("删除别名")
        delete_btn.clicked.connect(self.delete_alias)
        buttons.addWidget(add_btn)
        buttons.addWidget(edit_btn)
        buttons.addWidget(delete_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.aliases_table = QTableWidget()
        layout.addWidget(self.aliases_table, 1)

    def _build_advanced_tab(self) -> None:
        layout = QVBoxLayout(self.advanced_tab)
        warning = QLabel("高级操作会改变本地数据。删除自选不会删除历史事件；彻底删除会移除该公司的事件、告警、匹配和别名。")
        warning.setObjectName("MutedText")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        remove_btn = QPushButton("从自选移除")
        remove_btn.clicked.connect(self.remove_from_watchlist)
        delete_btn = QPushButton("彻底删除公司及相关数据")
        delete_btn.setObjectName("DangerButton")
        delete_btn.clicked.connect(self.permanently_delete_company)
        layout.addWidget(remove_btn)
        layout.addWidget(delete_btn)
        layout.addStretch()

    def refresh(self) -> None:
        with self.db.session() as session:
            company = CompanyRepository(session).get(self.company_id)
            summary = CompanySummaryService(session).get_company_summary(self.company_id)
            aliases = CompanyRepository(session).list_aliases(self.company_id)
            event_cards = get_event_cards(session, company_id=self.company_id, limit=100)
            alert_cards = [card for card in get_alert_cards(session, inbox_filter="all", limit=500) if card.company_id == self.company_id]
            sources = company_related_sources(session, self.company_id)
            documents = company_related_documents(session, self.company_id)

            self.header.set_summary(
                name=summary.name,
                ticker=summary.ticker or "未设置代码",
                exchange=summary.exchange or "未设置交易所",
                risk=summary.highest_priority_label,
                unread_alerts=summary.unread_alert_count,
                events=summary.event_count,
                last_scan=summary.last_scan_at.strftime("%Y-%m-%d %H:%M") if summary.last_scan_at else "未扫描",
            )
            self.recent_events_metric.set_value(summary.recent_event_count)
            self.unread_alerts_metric.set_value(summary.unread_alert_count)
            self.total_events_metric.set_value(summary.event_count)
            self.documents_metric.set_value(summary.document_count)
            self.summary_label.setText(
                f"最新重要事件：{summary.latest_event_title}\n"
                f"来源状态：{summary.source_status}\n"
                f"行业/地区：{company.industry or '未设置'} / {company.country or '未设置'}"
            )

            clear_layout(self.events_layout)
            if not event_cards:
                self.events_layout.addWidget(EmptyState("还没有检测到事件", "采集并解析资料后，事件会显示在这里。"))
            for card in event_cards:
                self.events_layout.addWidget(
                    EventCard(
                        company_name=card.company_name,
                        priority=card.priority,
                        title=card.title,
                        event_type=card.event_type,
                        event_status=card.event_status,
                        confidence_score=card.confidence_score,
                        materiality_score=card.materiality_score,
                        source_label=card.source_label,
                        created_text=card.created_at.strftime("%Y-%m-%d %H:%M"),
                        evidence=card.evidence,
                        on_evidence=lambda event_id=card.id: self.open_evidence(event_id),
                        on_company=None,
                        on_detail=lambda event_id=card.id: EventDetailDialog(self.db, event_id, self).exec(),
                        on_ack=(lambda alert_id=card.alert_id: self.set_alert_status(alert_id, "acknowledged")) if card.alert_id else None,
                        on_delete=lambda event_id=card.id, title=card.title: self.delete_event(event_id, title),
                    )
                )
            self.events_layout.addStretch()

            clear_layout(self.alerts_layout)
            if not alert_cards:
                self.alerts_layout.addWidget(EmptyState("还没有相关告警", "与该公司相关的提醒会集中显示在这里。"))
            for card in alert_cards:
                self.alerts_layout.addWidget(
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
                        on_ack=lambda alert_id=card.id: self.set_alert_status(alert_id, "acknowledged"),
                        on_ignore=lambda alert_id=card.id: self.set_alert_status(alert_id, "ignored"),
                        on_company=None,
                        on_delete=lambda alert_id=card.id, title=card.title: self.delete_alert(alert_id, title),
                    )
                )
            self.alerts_layout.addStretch()

            set_table_rows(
                self.aliases_table,
                ["ID", "别名", "类型", "创建时间"],
                [[alias.id, alias.alias, alias.alias_type, alias.created_at.strftime("%Y-%m-%d %H:%M")] for alias in aliases],
                [alias.id for alias in aliases],
            )
            self.document_ids = [doc.id for doc in documents]
            self.document_urls = {doc.id: doc.url for doc in documents}
            set_table_rows(
                self.documents_table,
                ["ID", "标题", "URL", "解析状态", "抓取时间"],
                [
                    [
                        doc.id,
                        doc.title or "",
                        doc.url,
                        doc.parse_status,
                        doc.fetched_at.strftime("%Y-%m-%d %H:%M"),
                    ]
                    for doc in documents
                ],
                [doc.id for doc in documents],
            )
            set_table_rows(
                self.sources_table,
                ["ID", "名称", "类型", "URL", "启用", "最近运行"],
                [
                    [
                        source.id,
                        source.name,
                        source.source_type,
                        source.url,
                        "是" if source.enabled else "否",
                        source.last_run_at.strftime("%Y-%m-%d %H:%M") if source.last_run_at else "",
                    ]
                    for source in sources
                ],
                [source.id for source in sources],
            )

    def open_evidence(self, event_id: int) -> None:
        with self.db.session() as session:
            evidence = EventRepository(session).evidence_for_event(event_id)
            snippets = [item.snippet for item in evidence]
        EvidenceDialog("事件证据", snippets, self).exec()

    def open_selected_document_text(self) -> None:
        doc_id = selected_id(self.documents_table)
        if doc_id is None:
            return
        with self.db.session() as session:
            document = session.get(Document, doc_id)
            text = document.parsed_text if document else ""
            title = document.title if document else "来源文档"
        TextViewerDialog(title or "来源文档", text or "暂无解析文本", self).exec()

    def open_selected_document_url(self) -> None:
        doc_id = selected_id(self.documents_table)
        if doc_id is None:
            return
        url = self.document_urls.get(doc_id)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def add_alias(self) -> None:
        alias, ok = QInputDialog.getText(self, "添加别名", "别名")
        if not ok or not alias.strip():
            return
        alias_type, ok = QInputDialog.getItem(
            self,
            "别名类型",
            "类型",
            ["legal_name", "ticker", "brand", "subsidiary", "chinese_name", "english_name", "former_name", "other"],
            editable=False,
        )
        if not ok:
            return
        with self.db.session() as session:
            CompanyRepository(session).add_alias(self.company_id, alias, alias_type)
        self.refresh()

    def edit_alias(self) -> None:
        alias_id = selected_id(self.aliases_table)
        if alias_id is None:
            return
        with self.db.session() as session:
            alias = session.get(CompanyAlias, alias_id)
            if alias is None:
                return
            value, ok = QInputDialog.getText(self, "编辑别名", "别名", text=alias.alias)
            if not ok or not value.strip():
                return
            alias.alias = value.strip()
        self.refresh()

    def delete_alias(self) -> None:
        alias_id = selected_id(self.aliases_table)
        if alias_id is None:
            return
        if QMessageBox.question(self, "删除别名", "确定删除该别名？") != QMessageBox.StandardButton.Yes:
            return
        with self.db.session() as session:
            alias = session.get(CompanyAlias, alias_id)
            if alias is not None:
                session.delete(alias)
        self.refresh()

    def set_alert_status(self, alert_id: int | None, status: str) -> None:
        if alert_id is None:
            return
        with self.db.session() as session:
            AlertRepository(session).set_status(alert_id, status)
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

    def scan_now(self) -> None:
        result = IngestionService(self.db, self.paths).run_all_enabled_sources()
        self.refresh()
        info(self, f"采集完成，共运行 {len(result)} 个启用数据源")

    def remove_from_watchlist(self) -> None:
        with self.db.session() as session:
            company = CompanyRepository(session).get(self.company_id)
            company_name = company.name
        if not RemoveWatchlistConfirmDialog.confirm(self, company_name):
            return
        try:
            with self.db.session() as session:
                WatchlistService(session).remove_from_watchlist(self.company_id)
        except Exception as exc:
            warn(self, f"删除自选失败：{exc}")
            return
        info(self, "已移入回收站，历史事件、告警和文档已保留，可在设置 → 回收站恢复。")
        self.accept()

    def permanently_delete_company(self) -> None:
        with self.db.session() as session:
            company = CompanyRepository(session).get(self.company_id)
            company_name = company.name
        text, ok = QInputDialog.getText(
            self,
            "彻底删除公司及相关数据",
            f"该操作会删除「{company_name}」的公司记录、别名、事件、告警和匹配关系。请输入公司名称确认：",
        )
        if not ok or text.strip() != company_name:
            return
        with self.db.session() as session:
            event_ids = list(session.scalars(select(Event.id).where(Event.company_id == self.company_id)))
            if event_ids:
                session.execute(delete(EventEvidence).where(EventEvidence.event_id.in_(event_ids)))
                session.execute(delete(Alert).where(Alert.event_id.in_(event_ids)))
                session.execute(delete(Event).where(Event.id.in_(event_ids)))
            session.execute(delete(DocumentCompanyMatch).where(DocumentCompanyMatch.company_id == self.company_id))
            session.execute(delete(CompanyAlias).where(CompanyAlias.company_id == self.company_id))
            session.execute(delete(WatchlistItem).where(WatchlistItem.company_id == self.company_id))
            session.execute(delete(Company).where(Company.id == self.company_id))
        info(self, "公司及相关本地数据已删除。")
        self.accept()

    def export_events(self) -> None:
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "导出该公司事件 CSV",
            str(self.paths.exports_dir / f"company-{self.company_id}-events.csv"),
            "CSV (*.csv)",
        )
        if not path_text:
            return
        with self.db.session() as session:
            result = ExportService(self.paths).export_events_csv(session, Path(path_text), company_id=self.company_id)
        info(self, f"已导出 {result.row_count} 条事件：{result.path}")
