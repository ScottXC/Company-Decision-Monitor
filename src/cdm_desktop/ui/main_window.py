from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import PREVIEW_MODE_LABEL, PRODUCT_NAME_ZH
from cdm_desktop.paths import AppPaths
from cdm_desktop.store import PreviewUiState
from cdm_desktop.ui.components import StatusBadge, show_preview_message
from cdm_desktop.ui.pages import (
    AiSummaryPage,
    CompanyDetailPage,
    DashboardPage,
    HotCompaniesPage,
    RiskMonitorPage,
    SearchPage,
    SettingsPage,
    WatchlistPage,
)


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.state = PreviewUiState()
        self.setWindowTitle(PRODUCT_NAME_ZH)
        self.resize(1360, 820)
        self.setMinimumSize(QSize(1180, 720))

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        root_layout.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 18)
        content_layout.setSpacing(14)
        root_layout.addWidget(content, 1)

        header = QHBoxLayout()
        self.page_title = QLabel("首页 Dashboard")
        self.page_title.setObjectName("PageTitle")
        header.addWidget(self.page_title)
        header.addStretch()
        self.global_search = QLineEdit()
        self.global_search.setPlaceholderText("搜索公司、行业、关键词...")
        self.global_search.setMinimumWidth(360)
        self.global_search.returnPressed.connect(self._submit_global_search)
        header.addWidget(self.global_search, 1)
        header.addWidget(StatusBadge(PREVIEW_MODE_LABEL, "info"))
        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(lambda: self.navigate("/settings"))
        header.addWidget(settings_btn)
        content_layout.addLayout(header)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.routes: list[tuple[str, str, QWidget]] = [
            ("/dashboard", "首页", DashboardPage(self.navigate)),
            ("/search", "公司搜索", SearchPage(self.navigate)),
            ("/company/placeholder", "公司详情", CompanyDetailPage(self.navigate)),
            ("/watchlist", "自选公司", WatchlistPage(self.navigate)),
            ("/hot-companies", "热门公司", HotCompaniesPage(self.navigate)),
            ("/risk-monitor", "风险监控", RiskMonitorPage(self.navigate)),
            ("/ai-summary", "AI 总结", AiSummaryPage(self.navigate)),
            ("/settings", "设置", SettingsPage(self.navigate, paths)),
        ]
        self.route_index = {route: index for index, (route, _label, _page) in enumerate(self.routes)}
        for _route, label, page in self.routes:
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
            self.sidebar.addItem(item)
            self.stack.addWidget(page)
        self.sidebar.currentRowChanged.connect(self._show_index)
        self.sidebar.setCurrentRow(0)

    def navigate(self, route: str) -> None:
        index = self.route_index.get(route)
        if index is None:
            if route.startswith("/company/"):
                index = self.route_index["/company/placeholder"]
            else:
                index = self.route_index["/dashboard"]
        self.sidebar.setCurrentRow(index)

    def _show_index(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        route, _label, page = self.routes[index]
        self.state.current_route = route
        self.page_title.setText(getattr(page, "page_title", _label))

    def _submit_global_search(self) -> None:
        keyword = self.global_search.text().strip()
        self.state.search_keyword = keyword
        self.navigate("/search")
        page = self.stack.currentWidget()
        set_query: Callable[[str], None] | None = getattr(page, "set_query", None)
        if callable(set_query):
            set_query(keyword)
        if not keyword:
            show_preview_message(self, "全局搜索")
