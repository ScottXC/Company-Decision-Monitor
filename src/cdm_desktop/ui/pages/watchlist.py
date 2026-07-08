from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.ui.components import (
    EmptyState,
    PageHeader,
    SectionCard,
    StatusBadge,
    sanitize_error_message,
    scroll_container,
)
from cdm_desktop.ui.widgets import FunctionWorker


class WatchlistPage(QWidget):
    route = "/watchlist"
    page_title = "自选清单"

    def __init__(
        self,
        navigate: Callable[[str], None],
        paths: AppPaths | None = None,
        *,
        on_company_selected: Callable[[CompanyResult], None] | None = None,
    ) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.on_company_selected = on_company_selected
        self.watchlist = WatchlistStore(paths)
        self.search_text = ""
        self.thread_pool = QThreadPool.globalInstance()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        self._clear()
        self.layout.addWidget(
            PageHeader(
                "自选公司",
                "像自选股列表一样集中查看已保存公司；自选数据只保存在本机。",
                primary_text="添加公司",
                primary_action=lambda: self.navigate("/search"),
                secondary_text="刷新全部",
                secondary_action=self._refresh_all,
            )
        )
        self.layout.addWidget(self._toolbar())
        items = self._filtered_items()
        self.layout.addWidget(self._list_card(items))
        self.layout.addStretch()

    def _toolbar(self) -> SectionCard:
        card = SectionCard("自选筛选", "只筛选本机已保存的自选公司，不会触发联网搜索。")
        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索自选公司、标识、市场或来源")
        self.search_input.setText(self.search_text)
        self.search_input.textChanged.connect(self._set_filter)
        search_btn = QPushButton("筛选")
        search_btn.clicked.connect(self.refresh)
        add_btn = QPushButton("去搜索添加")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(lambda: self.navigate("/search"))
        row.addWidget(self.search_input, 1)
        row.addWidget(search_btn)
        row.addWidget(add_btn)
        card.layout.addLayout(row)
        return card

    def _list_card(self, items: list[CompanyResult]) -> SectionCard:
        card = SectionCard("自选公司", f"共 {len(items)} 家 · 点击详情进入公司档案")
        if not items:
            card.layout.addWidget(
                EmptyState(
                    "暂无自选公司",
                    "搜索公司后，点击“添加自选”即可集中跟踪。",
                    action_text="去搜索公司",
                    action=lambda: self.navigate("/search"),
                )
            )
            return card
        card.layout.addWidget(self._list_header())
        for company in items:
            card.layout.addWidget(self._company_row(company))
        return card

    def _list_header(self) -> QWidget:
        header = QWidget()
        layout = QGridLayout(header)
        layout.setContentsMargins(12, 4, 12, 4)
        headers = ["公司", "标识", "市场 / 地区", "状态", "操作"]
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("FieldLabel")
            layout.addWidget(label, 0, column)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 2)
        layout.setColumnStretch(3, 2)
        layout.setColumnStretch(4, 2)
        return header

    def _company_row(self, company: CompanyResult) -> SectionCard:
        row = SectionCard()
        row.setObjectName("WatchlistRow")
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)

        title_box = QVBoxLayout()
        name = QLabel(company.name or company.legal_name or company.symbol or "未命名公司")
        name.setObjectName("SectionTitle")
        meta = QLabel(self._company_type(company))
        meta.setObjectName("MutedText")
        title_box.addWidget(name)
        title_box.addWidget(meta)
        layout.addLayout(title_box, 0, 0)

        identity = company.symbol or company.lei or company.company_number or company.registry_number or "暂无标识"
        layout.addWidget(StatusBadge(identity, "neutral"), 0, 1)

        market = company.exchange or company.market or company.jurisdiction or company.country or "暂无数据"
        market_label = QLabel(market)
        market_label.setObjectName("MutedText")
        market_label.setWordWrap(True)
        layout.addWidget(market_label, 0, 2)

        status_text = company.last_status or company.provider or "公开来源"
        layout.addWidget(StatusBadge(status_text[:24], "info" if company.last_status != "refresh_failed" else "warning"), 0, 3)

        actions = QHBoxLayout()
        detail_btn = QPushButton("详情")
        detail_btn.setObjectName("PrimaryButton")
        detail_btn.clicked.connect(lambda _checked=False, c=company: self._open_company(c))
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(lambda _checked=False, c=company: self._refresh_company(c))
        remove_btn = QPushButton("删除")
        remove_btn.setObjectName("DangerButton")
        remove_btn.clicked.connect(lambda _checked=False, c=company: self._remove_company(c))
        actions.addWidget(detail_btn)
        actions.addWidget(refresh_btn)
        if company.source_url:
            source_btn = QPushButton("来源")
            source_btn.clicked.connect(lambda _checked=False, url=company.source_url: QDesktopServices.openUrl(QUrl(url)))
            actions.addWidget(source_btn)
        actions.addWidget(remove_btn)
        layout.addLayout(actions, 0, 4)

        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 2)
        layout.setColumnStretch(3, 2)
        layout.setColumnStretch(4, 2)
        row.layout.addLayout(layout)
        return row

    def _filtered_items(self) -> list[CompanyResult]:
        query = self.search_text.strip().lower()
        items = self.watchlist.list_items()
        if not query:
            return items
        filtered: list[CompanyResult] = []
        for item in items:
            haystack = " ".join(
                [
                    item.name,
                    item.legal_name,
                    item.symbol,
                    item.exchange,
                    item.market,
                    item.country,
                    item.jurisdiction,
                    item.provider,
                ]
            ).lower()
            if query in haystack:
                filtered.append(item)
        return filtered

    def _set_filter(self, text: str) -> None:
        self.search_text = text

    def _open_company(self, company: CompanyResult) -> None:
        if self.on_company_selected:
            self.on_company_selected(company)
        else:
            self.navigate("/company/placeholder")

    def _remove_company(self, company: CompanyResult) -> None:
        title = company.name or company.symbol or "该公司"
        result = QMessageBox.question(
            self,
            "删除自选",
            f"确定将“{title}”从自选清单移除吗？\n\n这只会删除本机自选记录，不会删除缓存、搜索结果或历史数据。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.watchlist.remove(company.dedupe_key())
        self.refresh()

    def _refresh_company(self, company: CompanyResult) -> None:
        worker = FunctionWorker(self.watchlist.refresh_item, company.dedupe_key())
        worker.signals.finished.connect(lambda _result: self.refresh())
        worker.signals.error.connect(lambda message: QMessageBox.warning(self, "刷新失败", sanitize_error_message(message)))
        self.thread_pool.start(worker)

    def _refresh_all(self) -> None:
        worker = FunctionWorker(self.watchlist.refresh_all)
        worker.signals.finished.connect(lambda _result: self.refresh())
        worker.signals.error.connect(lambda message: QMessageBox.warning(self, "刷新失败", sanitize_error_message(message)))
        self.thread_pool.start(worker)

    def _company_type(self, company: CompanyResult) -> str:
        if company.symbol or company.exchange or company.market:
            return "上市公司"
        if company.lei or company.company_number or company.registry_number:
            return "法人实体"
        return "公开资料"

    def _clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
