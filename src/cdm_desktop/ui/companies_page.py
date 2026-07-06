from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import SourceRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.ingestion_service import IngestionService
from cdm_desktop.services.ui_query_service import get_company_cards
from cdm_desktop.services.watchlist_service import WatchlistService
from cdm_desktop.ui.company_detail_dialog import CompanyDetailDialog
from cdm_desktop.ui.widgets import (
    EmptyState,
    RemoveWatchlistConfirmDialog,
    SelfSelectedCompanyCard,
    clear_layout,
    info,
    make_scroll_area,
    warn,
)


class CompaniesPage(QWidget):
    page_title = "自选公司"
    primary_action_text = "添加公司"

    def __init__(
        self,
        db: DatabaseManager,
        paths: AppPaths,
        open_company_callback: Callable[[int], None] | None = None,
        open_online_search_callback: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        self.open_company_callback = open_company_callback
        self.open_online_search_callback = open_online_search_callback
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索自选公司")
        self.search.textChanged.connect(self.refresh)
        add_btn = QPushButton("添加公司")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self.add_company)
        controls.addWidget(self.search, 1)
        controls.addWidget(add_btn)
        layout.addLayout(controls)

        self.scroll, _content, self.cards_layout = make_scroll_area()
        layout.addWidget(self.scroll, 1)
        self.refresh()

    def run_primary_action(self) -> None:
        self.add_company()

    def refresh(self) -> None:
        query = self.search.text().strip()
        clear_layout(self.cards_layout)
        with self.db.session() as session:
            cards = get_company_cards(session, query=query)

        if not cards:
            self.cards_layout.addWidget(
                EmptyState(
                    "还没有自选公司",
                    "进入联网搜索，从公开来源结果中选择公司加入自选后，即可集中查看信息。",
                    "打开联网搜索",
                    self.add_company,
                )
            )
            self.cards_layout.addStretch()
            return

        for card in cards:
            self.cards_layout.addWidget(
                SelfSelectedCompanyCard(
                    name=card.name,
                    ticker=card.ticker,
                    exchange=card.exchange,
                    country=card.country,
                    industry=card.industry,
                    risk_priority=card.risk_priority,
                    unread_alerts=card.unread_alerts,
                    new_event_count=card.new_event_count,
                    latest_event_title=card.latest_event_title,
                    last_scanned_text=card.last_scanned_at.strftime("%m-%d %H:%M") if card.last_scanned_at else "未扫描",
                    source_status=card.source_status,
                    on_open=lambda company_id=card.id: self.open_detail(company_id),
                    on_scan=self.scan_now,
                    on_remove=lambda company_id=card.id, name=card.name: self.remove_from_watchlist(company_id, name),
                )
            )
        self.cards_layout.addStretch()

    def add_company(self) -> None:
        if self.open_online_search_callback:
            self.open_online_search_callback(self.search.text().strip())
        else:
            warn(self, "请进入“联网搜索”添加公司。")

    def scan_now(self) -> None:
        with self.db.session() as session:
            if not SourceRepository(session).list(enabled_only=True):
                warn(self, "请先在 设置 → 数据源管理 中添加并启用公告页、RSS 或公司 IR 页面。联网公司搜索只用于发现公司，不等于自动采集公告。")
                return
        result = IngestionService(self.db, self.paths).run_all_enabled_sources()
        self.refresh()
        info(self, f"采集完成，共运行 {len(result)} 个启用数据源")

    def remove_from_watchlist(self, company_id: int, company_name: str) -> None:
        if not RemoveWatchlistConfirmDialog.confirm(self, company_name):
            return
        try:
            with self.db.session() as session:
                WatchlistService(session).remove_from_watchlist(company_id)
        except Exception as exc:
            warn(self, f"删除自选失败：{exc}")
            return
        self.refresh()
        info(self, "已移入回收站，历史事件、告警和文档已保留，可在设置 → 回收站恢复。")

    def open_detail(self, company_id: int) -> None:
        if self.open_company_callback:
            self.open_company_callback(company_id)
        else:
            CompanyDetailDialog(self.db, self.paths, company_id, self).exec()
            self.refresh()


class CompanyDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, values: dict[str, str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加公司")
        values = values or {}
        layout = QFormLayout(self)
        self.name = QLineEdit(values.get("name", ""))
        self.legal_name = QLineEdit(values.get("legal_name", ""))
        self.ticker = QLineEdit(values.get("ticker", ""))
        self.exchange = QLineEdit(values.get("exchange", ""))
        self.country = QLineEdit(values.get("country", ""))
        self.industry = QLineEdit(values.get("industry", ""))
        self.notes = QLineEdit(values.get("notes", ""))
        for label, widget in [
            ("公司名称", self.name),
            ("法定名称", self.legal_name),
            ("股票代码", self.ticker),
            ("交易所", self.exchange),
            ("国家/地区", self.country),
            ("行业", self.industry),
            ("备注", self.notes),
        ]:
            layout.addRow(label, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, str | None]:
        return {
            "name": self.name.text().strip() or "未命名公司",
            "legal_name": self.legal_name.text().strip() or None,
            "ticker": self.ticker.text().strip() or None,
            "exchange": self.exchange.text().strip() or None,
            "country": self.country.text().strip() or None,
            "industry": self.industry.text().strip() or None,
            "notes": self.notes.text().strip() or None,
        }
