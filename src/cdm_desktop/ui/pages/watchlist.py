from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.public_api.xueqiu_external_link import build_xueqiu_external_link
from cdm_desktop.ui.components import (
    EmptyState,
    ListRow,
    PageHeader,
    SectionCard,
    sanitize_error_message,
    scroll_container,
)
from cdm_desktop.ui.widgets import FunctionWorker


class WatchlistPage(QWidget):
    route = "/watchlist"
    page_title = "自选公司"

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
        self.sort_mode = "added"
        self.thread_pool = QThreadPool.globalInstance()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        self._clear()
        all_items = self.watchlist.list_items()
        self.layout.addWidget(
            PageHeader(
                "自选公司",
                f"{len(all_items)} 家公司 · 自选仅保存在本机",
                primary_text="添加公司",
                primary_action=lambda: self.navigate("/search"),
                secondary_text="刷新全部",
                secondary_action=self._refresh_all,
            )
        )
        self.layout.addWidget(self._toolbar())
        self.layout.addWidget(self._list_section(self._filtered_items(all_items)))
        self.layout.addStretch()

    def _toolbar(self) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索自选")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setText(self.search_text)
        self.search_input.textChanged.connect(self._set_filter)
        self.search_input.returnPressed.connect(self.refresh)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("最近添加", "added")
        self.sort_combo.addItem("最近刷新", "refreshed")
        self.sort_combo.addItem("公司名称", "name")
        self.sort_combo.addItem("股票代码", "symbol")
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(self.sort_mode)))
        self.sort_combo.currentIndexChanged.connect(self._set_sort)
        row.addWidget(self.search_input, 1)
        row.addWidget(self.sort_combo)
        return host

    def _list_section(self, items: list[CompanyResult]) -> SectionCard:
        section = SectionCard("公司列表")
        if not items:
            section.layout.addWidget(
                EmptyState(
                    "暂无自选公司",
                    "搜索公司后添加自选，即可集中跟踪。",
                    action_text="去搜索",
                    action=lambda: self.navigate("/search"),
                )
            )
            return section
        for company in items:
            identity = company.symbol or company.lei or company.company_number or company.registry_number or "暂无标识"
            market = company.exchange or company.market or company.jurisdiction or company.country or self._company_type(company)
            row = ListRow(
                company.name or company.legal_name or identity,
                f"{identity} · {market}",
                detail=self._status_text(company),
                source=self._source_label(company),
                action_tooltip="刷新公司资料",
                action=lambda c=company: self._refresh_company(c),
            )
            row.activated.connect(lambda c=company: self._open_company(c))
            row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            row.customContextMenuRequested.connect(lambda point, r=row, c=company: self._show_menu(r, point, c))
            section.layout.addWidget(row)
        return section

    def _show_menu(self, row: QWidget, point: QPoint, company: CompanyResult) -> None:
        menu = QMenu(row)
        refresh = menu.addAction("刷新")
        remove = menu.addAction("移除自选")
        website = menu.addAction("打开官网") if company.website or company.source_url else None
        xueqiu = build_xueqiu_external_link(
            symbol=company.symbol,
            exchange=company.exchange,
            market=company.market,
            company_name=company.name,
        )
        xueqiu_action = menu.addAction("打开雪球") if xueqiu.url else None
        chosen = menu.exec(row.mapToGlobal(point))
        if chosen == refresh:
            self._refresh_company(company)
        elif chosen == remove:
            self._remove_company(company)
        elif website is not None and chosen == website:
            QDesktopServices.openUrl(QUrl(company.website or company.source_url))
        elif xueqiu_action is not None and chosen == xueqiu_action:
            QDesktopServices.openUrl(QUrl(xueqiu.url))

    def _filtered_items(self, items: list[CompanyResult] | None = None) -> list[CompanyResult]:
        rows = list(items if items is not None else self.watchlist.list_items())
        query = self.search_text.strip().lower()
        if query:
            rows = [
                item
                for item in rows
                if query
                in " ".join(
                    [item.name, item.legal_name, item.symbol, item.exchange, item.market, item.country, item.provider]
                ).lower()
            ]
        if self.sort_mode == "name":
            rows.sort(key=lambda item: (item.name or item.display_name).casefold())
        elif self.sort_mode == "symbol":
            rows.sort(key=lambda item: item.symbol.casefold())
        elif self.sort_mode == "refreshed":
            rows.sort(key=lambda item: item.last_refreshed_at or item.updated_at, reverse=True)
        else:
            rows.sort(key=lambda item: item.added_at, reverse=True)
        return rows

    def _set_filter(self, text: str) -> None:
        self.search_text = text

    def _set_sort(self) -> None:
        self.sort_mode = str(self.sort_combo.currentData() or "added")
        self.refresh()

    def _open_company(self, company: CompanyResult) -> None:
        if self.on_company_selected:
            self.on_company_selected(company)
        else:
            self.navigate("/company/placeholder")

    def _remove_company(self, company: CompanyResult) -> None:
        title = company.name or company.symbol or "该公司"
        result = QMessageBox.question(
            self,
            "移除自选",
            f"确定将“{title}”从自选中移除吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.watchlist.remove(company.dedupe_key())
            self.refresh()

    def _refresh_company(self, company: CompanyResult) -> None:
        worker = FunctionWorker(self.watchlist.refresh_item, company.dedupe_key())
        worker.signals.finished.connect(lambda _result: self.refresh())
        worker.signals.error.connect(lambda message: self._show_refresh_error(message))
        self.thread_pool.start(worker)

    def _refresh_all(self) -> None:
        worker = FunctionWorker(self.watchlist.refresh_all)
        worker.signals.finished.connect(lambda _result: self.refresh())
        worker.signals.error.connect(lambda message: self._show_refresh_error(message))
        self.thread_pool.start(worker)

    def _show_refresh_error(self, message: str) -> None:
        QMessageBox.warning(self, "刷新失败", sanitize_error_message(message))

    @staticmethod
    def _company_type(company: CompanyResult) -> str:
        if company.symbol:
            return "上市公司"
        if company.lei or company.company_number or company.registry_number:
            return "法人实体"
        return "公开资料"

    @staticmethod
    def _status_text(company: CompanyResult) -> str:
        if company.last_status == "refresh_failed":
            return "最近刷新失败，可从右侧重试"
        if company.last_refreshed_at:
            return f"最近刷新 {company.last_refreshed_at}"
        return "尚未刷新"

    @staticmethod
    def _source_label(company: CompanyResult) -> str:
        if company.provider_id == "symbol_universe" or company.raw.get("from_local_index"):
            return "本地索引"
        return "公开来源"

    def _clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
