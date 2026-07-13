from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api import PublicSearchService
from cdm_desktop.public_api.cache import ApiCache
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.ui.components import (
    EmptyState,
    ListRow,
    PageHeader,
    SectionCard,
    StatusBadge,
    scroll_container,
)


class DashboardPage(QWidget):
    route = "/dashboard"
    page_title = "首页"

    def __init__(self, navigate: Callable[[str], None], paths: AppPaths | None = None) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.search_service = PublicSearchService(paths)
        self.watchlist = WatchlistStore(paths)
        self.cache = ApiCache(paths)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        self._clear()
        items = self.watchlist.list_items()
        self.layout.addWidget(PageHeader("公司研究", "搜索公司并集中查看公开资料、相关新闻和自选状态。"))
        self.layout.addWidget(self._search_section())
        self.layout.addWidget(self._watchlist_section(items))
        self.layout.addWidget(self._messages_section())
        self.layout.addWidget(self._data_status())
        self.layout.addStretch()

    def _search_section(self) -> QWidget:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.quick_input = QLineEdit()
        self.quick_input.setObjectName("HeroSearchInput")
        self.quick_input.setPlaceholderText("搜索公司、股票代码或简称")
        self.quick_input.setClearButtonEnabled(True)
        self.quick_input.returnPressed.connect(self._quick_search)
        button = QPushButton("搜索")
        button.setObjectName("PrimaryButton")
        button.clicked.connect(self._quick_search)
        layout.addWidget(self.quick_input, 1)
        layout.addWidget(button)
        return host

    def _watchlist_section(self, items: list) -> SectionCard:
        section = SectionCard("我的自选")
        header = QHBoxLayout()
        count = QLabel(f"{len(items)} 家公司")
        count.setObjectName("MutedText")
        view_all = QPushButton("查看全部")
        view_all.setObjectName("LinkButton")
        view_all.clicked.connect(lambda: self.navigate("/watchlist"))
        header.addWidget(count)
        header.addStretch()
        header.addWidget(view_all)
        section.layout.addLayout(header)
        if not items:
            section.layout.addWidget(
                EmptyState(
                    "暂无自选公司",
                    "搜索公司后添加自选，即可在这里集中跟踪。",
                    action_text="搜索公司",
                    action=lambda: self.navigate("/search"),
                )
            )
            return section
        for company in items[:6]:
            identity = company.symbol or company.lei or company.company_number or "暂无标识"
            market = company.exchange or company.market or company.country or "公开资料"
            row = ListRow(
                company.name or company.display_name or identity,
                f"{identity} · {market}",
                detail=self._refresh_label(company),
            )
            row.activated.connect(lambda c=company: self._open_company(c))
            section.layout.addWidget(row)
        return section

    def _messages_section(self) -> SectionCard:
        section = SectionCard("最近消息")
        section.layout.addWidget(EmptyState("暂无可用消息", "公司新闻只会在进入公司详情后按需加载。"))
        return section

    def _data_status(self) -> QWidget:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 4, 0, 0)
        statuses = self.search_service.provider_statuses()
        local_ok = any(item.provider_id == "symbol_universe" and item.state in {"enabled", "empty"} for item in statuses)
        layout.addWidget(StatusBadge("本地索引可用" if local_ok else "本地索引需检查", "success" if local_ok else "warning"))
        layout.addWidget(StatusBadge("公开数据按需补充", "neutral"))
        layout.addWidget(StatusBadge("缓存已启用", "neutral"))
        layout.addStretch()
        settings = QPushButton("数据源状态")
        settings.setObjectName("LinkButton")
        settings.clicked.connect(lambda: self.navigate("/settings"))
        layout.addWidget(settings)
        return host

    def _quick_search(self) -> None:
        keyword = self.quick_input.text().strip()
        self.navigate("/search")
        parent = self.window()
        page = getattr(parent, "search_page", None)
        if page and hasattr(page, "set_query"):
            page.set_query(keyword)
            if keyword:
                page.run_search()

    def _open_company(self, company: object) -> None:
        opener = getattr(self.window(), "_open_company_detail", None)
        if callable(opener):
            opener(company)

    @staticmethod
    def _refresh_label(company: object) -> str:
        value = getattr(company, "last_refreshed_at", "") or getattr(company, "updated_at", "")
        return f"最近刷新 {value}" if value else "尚未刷新"

    def _clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
